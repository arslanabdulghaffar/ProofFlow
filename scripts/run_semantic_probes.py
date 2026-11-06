"""Three labeled worker-only fixtures with trusted local semantic comparison.

No inference, new cloud resource, candidate import/exec or product-state update.
Any runtime/cleanup/semantic expectation failure stops the probe sequence.
"""

import base64
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vultr_credit_guard import run as credit_guard  # noqa: E402
from vultr_phase1 import PRIVATE, ROOT, Admin  # noqa: E402

from contracts.policy import parse_contract  # noqa: E402
from contracts.source import parse_sources  # noqa: E402
from verifier.compare import compare_bytes  # noqa: E402
from worker.protocol import ExecutionRequest, authority_id  # noqa: E402


def main():
    admin = Admin()
    try:
        guard = credit_guard(admin, datetime.now(UTC))
        if guard.get("credit_guard") != "within_early_cutoff":
            raise RuntimeError("CREDIT_GUARD_NOT_ADMITTING")
        controller = (ROOT / "scripts/probe_semantics_controller.py").read_bytes()
        remote = "/opt/proofflow-control/probe_semantics_controller.py"
        result = admin.host("control", "umask 077; cat > " + remote, stdin=controller)
        if result.returncode:
            raise RuntimeError("SEMANTIC_PROBE_UPLOAD_FAILED")
        result = admin.host("control", "sha256sum " + remote)
        if (result.returncode or result.stdout.decode().split()[0]
                != hashlib.sha256(controller).hexdigest()):
            raise RuntimeError("SEMANTIC_PROBE_CONTROLLER_HASH_MISMATCH")
        evidence = PRIVATE / "evidence"
        evidence.mkdir(exist_ok=True)
        summaries = []
        header = "merchant_id,transaction_id,customer_id,amount,currency,occurred_at\n"
        for name in ("wrong_owner", "wrong_filter", "correct_held"):
            config = json.loads((ROOT / "contracts/examples/synthetic-v1.1.json").read_bytes())
            if name == "wrong_owner":
                transactions = (header + "A,T1,C,1.00,USD,2026-11-04T00:00:00Z\n"
                                + "B,T2,C,2.00,USD,2026-11-04T00:00:00Z\n").encode()
                customers = (b"merchant_id,customer_id,canonical_customer_id\n"
                             b"A,C,ownerA\nB,C,ownerB\n")
            else:
                transactions = (header + "A,T1,C,10.00,USD,2026-11-04T00:00:00Z\n" * 2).encode()
                customers = (b"merchant_id,customer_id,canonical_customer_id,segment\n"
                             b"A,C,ownerA,\n")
                config["downstream"].update(customer_attributes=["segment"],
                    occurred_at_from_utc="2026-11-05T00:00:00.000000Z",
                    occurred_at_before_utc="2026-11-06T00:00:00.000000Z")
            contract_bytes = json.dumps(config).encode()
            contract = parse_contract(contract_bytes)
            tx, cs = parse_sources(transactions, customers, aliases=dict(contract.aliases),
                                   customer_attributes=contract.attributes)
            pipeline = (ROOT / "tests/fixtures/phase2" / (name + ".py.txt")).read_bytes()
            request = ExecutionRequest(authority_id(), authority_id(), 1,
                                       pipeline, tx.worker_jsonl(),
                                       cs.worker_jsonl(), contract.canonical)
            message = {"name": name, "execution": request.execution_id.hex,
                       "job": request.job_id.hex, "manifest": request.manifest_hash()}
            for key, data in zip(("pipeline", "transactions", "customers", "requirements"),
                                 request.inputs(), strict=True):
                message[key] = base64.b64encode(data).decode("ascii")
            raw = json.dumps(message, sort_keys=True).encode()
            intent_path = evidence / (request.execution_id.hex + ".semantic-intent.json")
            with intent_path.open("xb") as file:
                file.write(raw)
                file.flush()
                os.fsync(file.fileno())
            result = admin.host("control", "/usr/bin/python3 -I -B " + remote,
                                stdin=raw, timeout=90)
            if result.returncode:
                raise RuntimeError("SEMANTIC_PROBE_OUTCOME_UNKNOWN_DO_NOT_RETRY")
            report = json.loads(result.stdout)
            receipt_path = evidence / (request.execution_id.hex + ".semantic-receipt.json")
            with receipt_path.open("xb") as file:
                file.write(result.stdout)
                file.flush()
                os.fsync(file.fileno())
            if (report["execution"] != request.execution_id.hex
                    or report["manifest"] != request.manifest_hash()):
                raise RuntimeError("SEMANTIC_PROBE_RECEIPT_IDENTITY_MISMATCH")
            receipt = report["receipt"]
            if (receipt.get("cleanup") != "confirmed" or receipt.get("collected") is not True
                    or type(receipt.get("runtime_client_exit_code")) is not int
                    or receipt.get("runtime_client_exit_code") != 0
                    or receipt.get("unit_result") != "success"):
                raise RuntimeError("CRITICAL_SEMANTIC_PROBE_RUNTIME_OR_CLEANUP_FAILED")
            files = {key: base64.b64decode(value, validate=True)
                     for key, value in report["files"].items()}
            comparison = compare_bytes(transactions, customers, contract_bytes, files)
            checks = sorted({finding.check_id for finding in comparison.findings})
            expected_checks = {"wrong_owner": ["V04"], "wrong_filter": ["V08"], "correct_held": []}
            expected_blocking = 0 if name == "wrong_owner" else 2
            if (checks != expected_checks[name]
                    or comparison.expected.blocking_occurrences != expected_blocking):
                raise RuntimeError("SEMANTIC_PROBE_EXPECTATION_FAILED")
            summaries.append({"fixture": name, "execution": request.execution_id.hex,
                "execution_manifest_sha256": request.manifest_hash(),
                "pipeline_sha256": hashlib.sha256(pipeline).hexdigest(),
                "contract_sha256": comparison.contract_sha256,
                "transactions_sha256": comparison.transactions_sha256,
                "customers_sha256": comparison.customers_sha256,
                "output_sha256": dict(comparison.output_hashes), "findings": checks,
                "blocking_occurrences": comparison.expected.blocking_occurrences,
                "runtime_exit": 0, "cleanup": "confirmed",
                "runtime_identity_sha256": report["runtime_identity_sha256"]})
            print(json.dumps({"fixture": name, "checks": checks,
                              "source_blocking": comparison.expected.blocking_occurrences,
                              "cleanup": "confirmed"}), flush=True)
        result = {"scope": "actual_worker_fixtures_trusted_local_comparison",
                  "observed_at": datetime.now(UTC).isoformat(), "probes": summaries,
                  "provider_calls": 0, "bounded_deployed_verifier": "NOT_RUN",
                  "protected_canary_workflow": "NOT_RUN", "activation": "NOT_AUTHORIZED"}
        (evidence / "phase2-semantic-probes-latest.json").write_text(
            json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps(result, sort_keys=True))
    finally:
        admin.close()


if __name__ == "__main__":
    main()
