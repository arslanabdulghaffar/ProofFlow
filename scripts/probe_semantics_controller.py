"""Trusted control transport only; fixture source runs solely on the worker.

The independent semantic comparison is performed by the operator-side trusted
test harness. This does not deploy the final bounded verifier or product API.
"""

import base64
import json
import os
import sys
from pathlib import Path
from uuid import UUID

ROOT = Path("/opt/proofflow-control")
sys.path.insert(0, str(ROOT / "lib"))
from orchestrator.worker_client import WorkerClient  # noqa: E402
from worker.protocol import ExecutionRequest  # noqa: E402
from worker.wire import strict_json, tls_context  # noqa: E402


def main():
    os.umask(0o077)
    config = json.loads((ROOT / "worker.json").read_bytes())
    if Path("/etc/machine-id").read_text().strip() != config["control_machine_id"]:
        raise RuntimeError("DESIGNATED_CONTROL_REQUIRED")
    raw = sys.stdin.buffer.read(131073)
    if len(raw) > 131072:
        raise RuntimeError("SYNTHETIC_PROBE_ENVELOPE_LIMIT")
    message = strict_json(raw)
    if (set(message) != {"execution", "job", "name", "pipeline", "transactions", "customers",
                         "requirements", "manifest"}
            or message["name"] not in ("wrong_owner", "wrong_filter", "correct_held")):
        raise RuntimeError("SYNTHETIC_PROBE_FIELDS_INVALID")
    request = ExecutionRequest(UUID(message["execution"]), UUID(message["job"]), 1,
                               *(base64.b64decode(message[key], validate=True) for key in
                                 ("pipeline", "transactions", "customers", "requirements")))
    if request.manifest_hash() != message["manifest"]:
        raise RuntimeError("SYNTHETIC_PROBE_MANIFEST_CHANGED")
    directory = Path("/var/lib/proofflow-control/probes")
    with (directory / (request.execution_id.hex + ".semantic-intent.json")).open("xb") as file:
        file.write(raw)
        file.flush()
        os.fsync(file.fileno())
    directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    context = tls_context(ROOT / "tls/ca.pem", ROOT / "tls/controller.pem",
                          ROOT / "tls/controller.key", server=False)
    client = WorkerClient(config["worker_address"], context, config["worker_certificate_sha256"],
                          config["runtime_sha256"])
    receipt = client.create(request)
    report = {"name": message["name"], "execution": request.execution_id.hex,
              "manifest": request.manifest_hash(), "receipt": receipt, "files": {},
              "runtime_identity_sha256": config["runtime_sha256"]}
    if (receipt.get("collected") is True and receipt.get("cleanup") == "confirmed"
            and type(receipt.get("runtime_client_exit_code")) is int
            and receipt.get("runtime_client_exit_code") == 0
            and receipt.get("unit_result") == "success"):
        captures = directory / "captures"
        captures.mkdir(mode=0o700, exist_ok=True)
        path = client.capture_to(captures, request.execution_id, request.job_id, 1,
                                 request.manifest_hash())
        for name in ("ledger.jsonl", "unresolved.jsonl"):
            data = (path / name).read_bytes()
            if len(data) > 16384:
                raise RuntimeError("SYNTHETIC_PROBE_OUTPUT_LIMIT")
            report["files"][name] = base64.b64encode(data).decode("ascii")
    with (directory / (request.execution_id.hex + ".semantic-receipt.json")).open("x") as file:
        json.dump(report, file, sort_keys=True)
        file.flush()
        os.fsync(file.fileno())
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
