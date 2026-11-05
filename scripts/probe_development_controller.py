"""Fixed development fixture execution on the designated isolated worker only."""

import hashlib
import json
import re
import sys
from pathlib import Path
from uuid import UUID

HERE = Path(__file__).resolve().parent
settings = json.loads((HERE / "settings.json").read_bytes())
target = settings["verifier_path"]
if re.fullmatch(r"/opt/proofflow-verifier/[a-f0-9]{64}", target) is None:
    raise RuntimeError("EVALUATION_VERIFIER_PATH_INVALID")
sys.path.insert(0, target)
sys.path.append("/opt/proofflow-control/lib")

from contracts.codec import parse_object  # noqa: E402
from orchestrator.verification_run import VerificationRun  # noqa: E402
from orchestrator.worker_client import WorkerClient  # noqa: E402
from worker.wire import tls_context  # noqa: E402


def main():
    message = parse_object(sys.stdin.buffer.read(4097), max_bytes=4096)
    if (set(message) != {"case", "variant", "execution", "job"}
            or message["case"] not in settings["cases"]
            or message["variant"] not in ("fault", "reference")):
        raise RuntimeError("EVALUATION_DEVELOPMENT_REQUEST_INVALID")
    control = Path("/opt/proofflow-control")
    worker = json.loads((control / "worker.json").read_bytes())
    if Path("/etc/machine-id").read_text().strip() != worker["control_machine_id"]:
        raise RuntimeError("DESIGNATED_CONTROL_REQUIRED")
    descriptor = settings["cases"][message["case"]]
    files = {}
    for name in ("pipeline.py.txt", "contract.json", "transactions.csv", "customers.csv"):
        raw = (HERE / message["case"] / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != descriptor["file_hashes"][name]:
            raise RuntimeError("EVALUATION_FIXTURE_CHANGED")
        files[name] = raw
    if message["variant"] == "reference":
        raw = (HERE / "reference.py.txt").read_bytes()
        if hashlib.sha256(raw).hexdigest() != settings["reference_sha256"]:
            raise RuntimeError("EVALUATION_REFERENCE_CHANGED")
        files["pipeline.py.txt"] = raw
    context = tls_context(control / "tls/ca.pem", control / "tls/controller.pem",
                          control / "tls/controller.key", server=False)
    client = WorkerClient(worker["worker_address"], context, worker["worker_certificate_sha256"],
                          worker["runtime_sha256"])
    journal = Path("/var/lib/proofflow-control/evaluation-development-20261105")
    journal.mkdir(mode=0o700, exist_ok=True)
    runner = VerificationRun(client, Path(target) / "rootfs.squashfs",
                             settings["verifier_sha256"], journal)
    result = runner.execute(execution=UUID(message["execution"]), job=UUID(message["job"]),
        generation=1, pipeline=files["pipeline.py.txt"], contract=files["contract.json"],
        transactions=files["transactions.csv"], customers=files["customers.csv"],
        purpose="original")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
