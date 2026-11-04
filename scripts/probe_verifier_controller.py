"""Operator-only canary integration fixtures on the existing deployed worker."""

import json
import sys
from pathlib import Path
from uuid import UUID

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.append("/opt/proofflow-control/lib")

from contracts.codec import canonical_bytes, parse_object  # noqa: E402
from orchestrator.verification_run import VerificationRun  # noqa: E402
from orchestrator.worker_client import WorkerClient  # noqa: E402
from verifier.protocol import decode  # noqa: E402
from worker.host import sync_directory, synced_write  # noqa: E402
from worker.wire import tls_context  # noqa: E402


def main():
    raw = sys.stdin.buffer.read(32769)
    message = parse_object(raw)
    if (set(message) != {"execution", "job", "fixture", "case", "contract"}
            or message["fixture"] not in ("canary_correct", "wrong_owner")
            or message["case"] not in ("ownership", "quarantine")):
        raise RuntimeError("INVALID_CANARY_PROBE")
    config = json.loads((HERE / "deployment.json").read_bytes())
    control = Path("/opt/proofflow-control")
    worker = json.loads((control / "worker.json").read_bytes())
    if Path("/etc/machine-id").read_text().strip() != worker["control_machine_id"]:
        raise RuntimeError("DESIGNATED_CONTROL_REQUIRED")
    context = tls_context(control / "tls/ca.pem", control / "tls/controller.pem",
                          control / "tls/controller.key", server=False)
    client = WorkerClient(worker["worker_address"], context, worker["worker_certificate_sha256"],
                          worker["runtime_sha256"])
    journal = Path("/var/lib/proofflow-control/verification-probes")
    journal.mkdir(mode=0o700, exist_ok=True)
    runner = VerificationRun(client, HERE / "rootfs.squashfs", config["rootfs_sha256"], journal)
    contract = decode(message["contract"], 32768)
    canary = runner.canary(contract, message["case"])
    generated = canary["report"]["result"]
    execution = UUID(message["execution"])
    result = runner.execute(execution=execution, job=UUID(message["job"]), generation=1,
        pipeline=(HERE / (message["fixture"] + ".py.txt")).read_bytes(), contract=contract,
        transactions=decode(generated["transactions_csv"], 5242880),
        customers=decode(generated["customers_csv"], 5242880), purpose="canary_" + message["case"])
    directory = journal / execution.hex
    synced_write(directory / "generation.json", canonical_bytes(canary, max_bytes=131072))
    sync_directory(directory)
    # Raw sources remain private. External report binds generation/result and code.
    print(json.dumps({"fixture": message["fixture"], "case": message["case"],
                      "generation_report_sha256": canary["report_sha256"],
                      "seed_sha256": generated["seed_sha256"], "result": result}, sort_keys=True))


if __name__ == "__main__":
    main()
