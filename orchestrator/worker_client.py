"""Fixed private mTLS worker transport. Unknown delivery never triggers automatic retry."""

import base64
import hashlib
import json
import os
import socket
import ssl
import stat
from pathlib import Path
from uuid import UUID

from worker.protocol import ExecutionRequest, SupervisorError, runtime_identity_digest
from worker.service import decode_input
from worker.wire import (
    authenticate,
    check_context,
    digest,
    keys,
    private_address,
    receive,
    send,
    strict_json,
)


def _private_directory(path: Path) -> None:
    info = path.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
            or info.st_mode & 0o077):
        raise SupervisorError("UNSAFE_CAPTURE_DESTINATION")


def _read_saved(path: Path, limit: int) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as source:
        info = os.fstat(source.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > limit
                or info.st_uid != os.geteuid() or info.st_mode & 0o077):
            raise SupervisorError("CAPTURE_DESTINATION_CONFLICT")
        data = source.read(limit + 1)
        if len(data) != info.st_size:
            raise SupervisorError("CAPTURE_DESTINATION_CONFLICT")
        os.fsync(source.fileno())
        return data


class WorkerClient:
    def __init__(self, address: str, context: ssl.SSLContext, certificate_sha256: str,
                 runtime_sha256: str):
        self.address = private_address(address)
        self.context = context
        self.pin = digest(certificate_sha256)
        self.runtime_digest = digest(runtime_sha256)

    def call(self, message: dict) -> dict:
        check_context(self.context, server=False)
        try:
            with socket.create_connection((self.address, 9443), timeout=5) as raw:
                with self.context.wrap_socket(
                        raw, server_hostname="worker.proofflow.internal") as tls:
                    authenticate(tls, self.pin)
                    send(tls, message)
                    response = receive(tls, seconds=45)
            if response.get("ok") is True:
                keys(response, {"ok", "result"})
                if type(response["result"]) is not dict:
                    raise SupervisorError("INVALID_WORKER_RESPONSE")
                return response["result"]
            raise SupervisorError("WORKER_REQUEST_FAILED")
        except (OSError, ValueError):
            raise SupervisorError("WORKER_DELIVERY_UNKNOWN") from None

    def create(self, request: ExecutionRequest) -> dict:
        return self.call({"v": 1, "op": "create", "execution": request.execution_id.hex,
                          "job": request.job_id.hex, "generation": request.generation,
                          "rollups": request.include_rollups, "manifest": request.manifest_hash(),
                          "runtime": self.runtime_digest,
                          "inputs": {name: base64.b64encode(data).decode() for name, data in zip(
                              ("pipeline", "transactions", "customers", "requirements"),
                              request.inputs(), strict=True)}})

    def capture_to(self, root: Path, execution: UUID, job: UUID, generation: int,
                   manifest: str) -> Path:
        message = {"v": 1, "op": "capture", "execution": execution.hex, "job": job.hex,
                   "generation": generation, "manifest": digest(manifest)}
        from worker.host import sync_directory, synced_write
        _private_directory(root)
        target = root / execution.hex
        if target.exists() or target.is_symlink():
            # Reconcile lost ACK using independently rechecked durable local bytes;
            # worker may already have deleted its copy. Never rerun the execution.
            _private_directory(target)
            receipt = strict_json(_read_saved(target / "receipt.json", 65536))
            names = set(os.listdir(target)) - {"receipt.json"}
            allowed = {"ledger.jsonl", "unresolved.jsonl", "rollups.jsonl",
                       "stdout.bin", "stderr.bin"}
            if not names <= allowed:
                raise SupervisorError("CAPTURE_DESTINATION_CONFLICT")
            encoded = {}
            total = 0
            for name in names:
                data = _read_saved(target / name, 102400 if name.endswith(".bin") else 10485760)
                total += len(data)
                if total > 10485760 + 102400:
                    raise SupervisorError("CAPTURE_DESTINATION_CONFLICT")
                encoded[name] = base64.b64encode(data).decode()
            validate_capture({"receipt": receipt, "files": encoded}, execution, job,
                             generation, manifest, expected_runtime=self.runtime_digest)
        else:
            result = self.call(message)
            files = validate_capture(result, execution, job, generation, manifest,
                                     expected_runtime=self.runtime_digest)
            target.mkdir(mode=0o700)
            sync_directory(root)
            for name, data in files.items():
                synced_write(target / name, data)
            synced_write(target / "receipt.json", json.dumps(result["receipt"], sort_keys=True,
                         separators=(",", ":")).encode())
        sync_directory(target)
        sync_directory(root)
        self.call(dict(message, op="ack"))  # Only after local durable verified bytes.
        return target


def validate_capture(result: dict, execution: UUID, job: UUID, generation: int,
                     manifest: str, *, expected_runtime: str | None = None) -> dict[str, bytes]:
    keys(result, {"receipt", "files"})
    receipt, encoded = result["receipt"], result["files"]
    if type(receipt) is not dict or type(encoded) is not dict:
        raise SupervisorError("INVALID_CAPTURE_RESPONSE")
    if (receipt.get("execution") != execution.hex or receipt.get("job") != job.hex
            or type(receipt.get("generation")) is not int or receipt["generation"] != generation
            or receipt.get("manifest") != manifest
            or receipt.get("cleanup") != "confirmed" or receipt.get("collected") is not True
            or receipt.get("verification") != "NOT_PERFORMED"):
        raise SupervisorError("CAPTURE_IDENTITY_MISMATCH")
    if expected_runtime is not None and (type(receipt.get("runtime")) is not dict
            or runtime_identity_digest(receipt["runtime"]) != expected_runtime):
        raise SupervisorError("CAPTURE_RUNTIME_MISMATCH")
    try:
        if (type(receipt["files"]) is not list or len(receipt["files"]) > 3
                or type(receipt["logs"]) is not list or len(receipt["logs"]) > 2):
            raise ValueError("count")
        expected = [(f["name"], f["bytes"], f["sha256"], 10485760) for f in receipt["files"]]
        expected += [(f["stream"] + ".bin", f["retained"], f["sha256"], 102400)
                     for f in receipt["logs"]]
        names = {name for name, _, _, _ in expected}
        allowed = {"ledger.jsonl", "unresolved.jsonl", "rollups.jsonl", "stdout.bin", "stderr.bin"}
        if (not {"ledger.jsonl", "unresolved.jsonl"} <= names or len(names) != len(expected)
                or names != set(encoded) or not names <= allowed):
            raise ValueError("names")
        files = {}
        totals = {10485760: 0, 102400: 0}
        for name, size, sha, limit in expected:
            if type(size) is not int or not 0 <= size <= limit:
                raise ValueError("size")
            data = decode_input(encoded[name], limit)
            if len(data) != size or hashlib.sha256(data).hexdigest() != digest(sha):
                raise ValueError("hash")
            totals[limit] += size
            if totals[limit] > limit:
                raise ValueError("aggregate")
            files[name] = data
        return files
    except (KeyError, TypeError, ValueError):
        raise SupervisorError("CAPTURE_INTEGRITY_FAILURE") from None
