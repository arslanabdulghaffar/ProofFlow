"""Trusted original/canary orchestration, with immutable intent before worker I/O.

This primitive does not grant product approvals or mutate job state. A durable
queue dispatcher must authorize/fence each invocation. It never executes code.
"""

import fcntl
import hashlib
import json
import os
import secrets
import stat
from pathlib import Path
from uuid import UUID

from contracts.codec import canonical_bytes
from orchestrator.worker_client import WorkerClient
from verifier.host import run
from verifier.protocol import MAX_REQUEST, decode, encode, sha
from worker.host import sync_directory, synced_write
from worker.journal import private_directory
from worker.protocol import ExecutionRequest, SupervisorError, runtime_identity_digest


def retained_receipt(receipt):
    """Do not extend the worker's brief failure preview lifetime into product history."""
    value = dict(receipt)
    if "failure_log_preview" in value:
        preview = value.pop("failure_log_preview")
        value["failure_log_preview_sha256"] = hashlib.sha256(
            json.dumps(preview, sort_keys=True).encode()).hexdigest()
        value["failure_log_preview_retired"] = True
    return value


def repairable_failure(worker, intent):
    """Only bound normal exits; no timeout/OOM/cancel/unknown infrastructure recovery."""
    code = worker.get("runtime_client_exit_code")
    observed = worker.get("resource_observation") or {}
    return (
        worker.get("cleanup") == "confirmed"
        and worker.get("execution") == intent["execution"]
        and worker.get("job") == intent["job"]
        and type(worker.get("generation")) is int
        and worker["generation"] == intent["generation"]
        and worker.get("manifest") == intent["manifest_sha256"]
        and runtime_identity_digest(worker.get("runtime", {})) == intent["runtime_sha256"]
        and worker.get("outcome") in ("exited", "output_rejected")
        and observed.get("source") == "host_cgroup_v2"
        and type(observed.get("samples")) is int and observed["samples"] > 0
        and observed.get("limits") == {"cpu_cores": 1, "memory_bytes": 805306368,
                                       "swap_bytes": 0, "host_tasks": 128}
        and type(code) is int and 0 <= code <= 125
        and worker.get("runtime_exit_code") == str(code)
        and ((code > 0 and worker.get("unit_result") == "exit-code"
              and worker.get("runtime_exit_kind") == "1")
             or (code == 0 and worker.get("unit_result") == "success"
                 and worker.get("runtime_exit_kind") in ("0", "1")
                 and worker.get("outcome") == "output_rejected"))
    )


class VerificationRun:
    def __init__(self, client: WorkerClient, image: Path, image_sha256: str, journal: Path,
                 verifier=None, before_dispatch=None, after_capture=None):
        self.client, self.image = client, image
        self.image_sha256, self.journal = image_sha256, journal
        self.verifier = verifier
        self.before_dispatch, self.after_capture = before_dispatch, after_capture
        private_directory(journal)

    def bounded(self, message):
        raw = canonical_bytes(message, max_bytes=MAX_REQUEST)
        receipt = (self.verifier(raw) if self.verifier is not None
                   else run(raw, image=self.image, image_sha256=self.image_sha256))
        if receipt["cleanup_confirmed"] is not True:
            raise SupervisorError("VERIFIER_CLEANUP_UNCERTAIN")
        return receipt

    def canary(self, contract: bytes, case: str):
        # Seed is never taken from an API, candidate or model. Persist the generated
        # CSV/manifest in the execution intent for exact replay, not in prompts.
        result = self.bounded({"operation": "canary", "contract": encode(contract),
                               "seed": secrets.token_hex(32), "case": case})
        if result["report"]["status"] != "processed":
            raise SupervisorError("CANARY_GENERATION_REJECTED")
        return result

    def execute(self, *, execution: UUID, job: UUID, generation: int, pipeline: bytes,
                contract: bytes, transactions: bytes, customers: bytes, purpose: str):
        fd = os.open(self.journal, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
            deleted = self.journal / (".deleted-" + job.hex)
            if deleted.exists() or deleted.is_symlink():
                raise SupervisorError("VERIFICATION_JOB_DELETED")
            return self._execute(execution=execution, job=job, generation=generation,
                pipeline=pipeline, contract=contract, transactions=transactions,
                customers=customers, purpose=purpose)
        finally:
            os.close(fd)

    def _execute(self, *, execution: UUID, job: UUID, generation: int, pipeline: bytes,
                 contract: bytes, transactions: bytes, customers: bytes, purpose: str):
        if purpose not in ("original", "candidate", "canary_ownership", "canary_quarantine"):
            raise SupervisorError("VERIFICATION_PURPOSE_INVALID")
        prepared = self.bounded({"operation": "prepare", "contract": encode(contract),
                                 "transactions": encode(transactions),
                                 "customers": encode(customers)})
        if prepared["report"]["status"] != "processed":
            raise SupervisorError("SOURCE_PREPARATION_REJECTED")
        data = prepared["report"]["result"]
        request = ExecutionRequest(execution, job, generation, pipeline,
                                   decode(data["transactions_jsonl"], 10 * 1024 * 1024),
                                   decode(data["customers_jsonl"], 10 * 1024 * 1024),
                                   decode(data["requirements"], 32768), data["include_rollups"])
        manifest = request.manifest_hash()
        intent = {"execution": execution.hex, "job": job.hex, "generation": generation,
                  "purpose": purpose, "manifest_sha256": manifest, "pipeline_sha256": sha(pipeline),
                  "contract_raw_sha256": sha(contract), "contract_sha256": data["contract_sha256"],
                  "transactions_sha256": sha(transactions), "customers_sha256": sha(customers),
                  "runtime_sha256": self.client.runtime_digest,
                  "verifier_rootfs": self.image_sha256}
        # The intent and exact sources survive uncertain delivery. Existing IDs are
        # never retried here: recovery must reconcile worker state explicitly.
        directory = self.journal / execution.hex
        fd = os.open(self.journal / "lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_nlink != 1):
                raise SupervisorError("VERIFICATION_JOURNAL_LOCK_INVALID")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # Includes failed/uncertain intents. No eviction or hidden retry to
            # reclaim capacity; later retention must reconcile worker ownership.
            if sum(p.is_dir() for p in self.journal.iterdir()) >= 64:
                raise SupervisorError("VERIFICATION_JOURNAL_CAPACITY")
            directory.mkdir(mode=0o700)
            sync_directory(self.journal)
        finally:
            os.close(fd)
        synced_write(directory / "intent.json", canonical_bytes(intent))
        for name, raw in (("transactions.csv", transactions), ("customers.csv", customers),
                          ("contract.json", contract), ("pipeline.py.txt", pipeline)):
            synced_write(directory / name, raw)
        sync_directory(directory)
        sync_directory(self.journal)
        if self.before_dispatch is not None:
            self.before_dispatch(request, intent)
        worker = retained_receipt(self.client.create(request))
        synced_write(directory / "worker.json", canonical_bytes(worker, max_bytes=65536))
        sync_directory(directory)
        good = (worker.get("collected") is True and worker.get("cleanup") == "confirmed"
                and type(worker.get("runtime_client_exit_code")) is int
                and worker.get("runtime_client_exit_code") == 0
                and worker.get("unit_result") == "success")
        result = {"intent": intent, "worker": worker, "semantic": None}
        if not good and purpose == "original" and repairable_failure(worker, intent):
            result["source"] = self.bounded({"operation": "source", "contract": encode(contract),
                "transactions": encode(transactions), "customers": encode(customers)})
        if good:
            captures = directory / "captures"
            captures.mkdir(mode=0o700)
            captured = self.client.capture_to(captures, execution, job, generation, manifest)
            names = ["ledger.jsonl", "unresolved.jsonl"]
            if request.include_rollups:
                names.append("rollups.jsonl")
            files = {}
            for name in names:
                with (captured / name).open("rb") as source:
                    raw = source.read(10 * 1024 * 1024 + 1)
                if len(raw) > 10 * 1024 * 1024:
                    raise SupervisorError("VERIFICATION_OUTPUT_LIMIT")
                files[name] = raw
            if sum(map(len, files.values())) > 10 * 1024 * 1024:
                raise SupervisorError("VERIFICATION_OUTPUT_LIMIT")
            if self.after_capture is not None:
                self.after_capture(request, worker)
            result["semantic"] = self.bounded({"operation": "verify", "contract": encode(contract),
                "transactions": encode(transactions), "customers": encode(customers),
                "outputs": {name: encode(raw) for name, raw in files.items()}})
        synced_write(directory / "result.json", canonical_bytes(result, max_bytes=131072))
        sync_directory(directory)
        return result
