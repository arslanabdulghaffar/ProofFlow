"""Read provider source as data, execute only through the isolated worker RPC.

This is a synthetic infrastructure probe, not the Phase 2 business verifier.
"""

import base64
import hashlib
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path("/opt/proofflow-control")
sys.path.insert(0, str(ROOT / "lib"))
from orchestrator.probe_response import strict_json_object  # noqa: E402
from orchestrator.worker_client import WorkerClient  # noqa: E402
from worker.protocol import ExecutionRequest  # noqa: E402
from worker.wire import tls_context  # noqa: E402

if len(sys.argv) != 2 or sys.argv[1] not in ("dense-coding-extended", "flash-coding-extended"):
    raise SystemExit("FIXED_RECORDED_PROVIDER_PROBE_REQUIRED")
os.umask(0o077)
name = sys.argv[1]
config = json.loads((ROOT / "worker.json").read_bytes())
if Path("/etc/machine-id").read_text().strip() != config["control_machine_id"]:
    raise SystemExit("DESIGNATED_CONTROL_REQUIRED")
results = Path("/var/lib/proofflow-provider-probe/results")
provider = json.loads((results / (name + ".json")).read_bytes())
content = (results / (name + ".content")).read_bytes()
if (hashlib.sha256(content).hexdigest() != provider["content_sha256"]
        or strict_json_object(content, max_bytes=65536) != provider["content"]):
    raise RuntimeError("RECORDED_MODEL_CONTENT_CHANGED")
code = provider["content"]["code"].encode()
if not 0 < len(code) <= 16384:
    raise RuntimeError("GENERATED_CODE_LIMIT")
records = [{"merchant": merchant, "amount_cents": amount} for merchant, amount in
           (("B", 900), ("A", 125), ("B", -100), ("C", 0), ("A", -25),
            ("D", 9007199254740993))]
transactions = b"".join(json.dumps(row, sort_keys=True).encode() + b"\n" for row in records)
request = ExecutionRequest(uuid4(), uuid4(), 1, code, transactions, b"", b"{}")
directory = Path("/var/lib/proofflow-control/probes")
intent = {"provider_response_sha256": provider["response_sha256"],
          "pipeline_sha256": hashlib.sha256(code).hexdigest(),
          "pipeline_base64": base64.b64encode(code).decode(),
          "manifest": request.manifest_hash(), "execution": request.execution_id.hex,
          "job": request.job_id.hex, "transactions_base64": base64.b64encode(transactions).decode()}
with (directory / (request.execution_id.hex + ".intent.json")).open("x") as file:
    json.dump(intent, file, sort_keys=True)
    file.flush()
    os.fsync(file.fileno())
context = tls_context(ROOT / "tls/ca.pem", ROOT / "tls/controller.pem",
                      ROOT / "tls/controller.key", server=False)
client = WorkerClient(config["worker_address"], context, config["worker_certificate_sha256"],
                      config["runtime_sha256"])
receipt = client.create(request)
report = {"scope": "synthetic_infrastructure_not_business_verification", "probe": name,
          "execution": request.execution_id.hex, "receipt": receipt,
          "pipeline_sha256": intent["pipeline_sha256"],
          "provider_response_sha256": provider["response_sha256"],
          "independent_expected_check": False}
if (receipt.get("collected") and receipt.get("cleanup") == "confirmed"
        and receipt.get("runtime_client_exit_code") == 0
        and receipt.get("unit_result") == "success"):
    captures = directory / "captures"
    captures.mkdir(mode=0o700, exist_ok=True)
    path = client.capture_to(captures, request.execution_id, request.job_id, 1,
                             request.manifest_hash())
    raw = (path / "ledger.jsonl").read_bytes()
    actual = [strict_json_object(line, max_bytes=4096) for line in raw.splitlines()]
    sums = {}
    for row in records:
        sums[row["merchant"]] = sums.get(row["merchant"], 0) + row["amount_cents"]
    expected = [{"merchant": merchant, "total_cents": sums[merchant]} for merchant in sorted(sums)]
    report["observed"] = actual
    report["expected"] = expected
    report["independent_expected_check"] = (actual == expected
        and all(type(row.get("total_cents")) is int for row in actual)
        and (path / "unresolved.jsonl").read_bytes() == b"")
with (directory / (request.execution_id.hex + ".generated.json")).open("x") as file:
    json.dump(report, file, sort_keys=True)
    file.flush()
    os.fsync(file.fileno())
print(json.dumps(report, sort_keys=True))
if not report["independent_expected_check"]:
    raise SystemExit("GENERATED_SYNTHETIC_RESULT_REJECTED")
