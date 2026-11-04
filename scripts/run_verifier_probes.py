"""Deployed boundary + fresh protected canary probes; no LLM or new resources."""

import hashlib
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vultr_credit_guard import run as credit_guard  # noqa: E402
from vultr_phase1 import PRIVATE, ROOT, Admin  # noqa: E402

from contracts.codec import canonical_bytes  # noqa: E402
from verifier.protocol import encode  # noqa: E402


def main():
    deployment = json.loads((PRIVATE / "evidence/verifier-deployment.json").read_bytes())
    identifier = deployment["deployment"]
    if re.fullmatch(r"[0-9a-f]{64}", identifier) is None:
        raise RuntimeError("INVALID_DEPLOYMENT_ID")
    target = "/opt/proofflow-verifier/" + identifier
    admin = Admin()
    try:
        if credit_guard(admin, datetime.now(UTC)).get("credit_guard") != "within_early_cutoff":
            raise RuntimeError("CREDIT_GUARD_NOT_ADMITTING")

        def host(command, raw=None, timeout=120):
            reply = admin.host("control", command, stdin=raw, timeout=timeout)
            if reply.returncode:
                raise RuntimeError("VERIFIER_PROBE_FAILED_OR_UNKNOWN_NO_AUTOMATIC_RETRY")
            return reply.stdout

        files = {"probe_verifier_controller.py": ROOT / "scripts/probe_verifier_controller.py",
                 "boundary_check.py": ROOT / "tests/security/verifier_boundary_linux_check.py",
                 "canary_correct.py.txt": ROOT / "tests/fixtures/phase2/canary_correct.py.txt",
                 "wrong_owner.py.txt": ROOT / "tests/fixtures/phase2/wrong_owner.py.txt"}
        source_hashes = {}
        for name, path in files.items():
            raw = path.read_bytes()
            host("umask 077; cat > " + target + "/" + name, raw)
            actual = host("sha256sum " + target + "/" + name).decode().split()[0]
            source_hashes[str(path.relative_to(ROOT)).replace("\\", "/")] = actual
            if actual != hashlib.sha256(raw).hexdigest():
                raise RuntimeError("PROBE_SOURCE_HASH_CHANGED")
        # Fixed trusted diagnostic code, not submitted or model-generated code.
        command = ("/usr/bin/python3 -I -B -c 'import sys,runpy;sys.path.insert(0,\"" + target
                   + "\");sys.path.append(\"/opt/proofflow-control/lib\");runpy.run_path(\""
                   + target + "/boundary_check.py\",run_name=\"__main__\")' --image "
                   + target + "/rootfs.squashfs --sha256 " + deployment["rootfs_sha256"])
        boundary = json.loads(host(command))
        print(json.dumps({"deployed_boundary_groups": boundary["passed"],
                          "cleanup_confirmed": boundary["cleanup_confirmed"]}), flush=True)
        cases = [("canary_correct", "ownership", False), ("canary_correct", "quarantine", False),
                 ("canary_correct", "quarantine", True), ("wrong_owner", "ownership", False)]
        summaries = []
        for fixture, case, extended in cases:
            contract = json.loads((ROOT / "contracts/examples/synthetic-v1.1.json").read_bytes())
            if extended:
                contract["downstream"].update(customer_attributes=["segment"],
                    occurred_at_from_utc="2026-11-04T00:00:00.000000Z",
                    occurred_at_before_utc="2026-11-05T00:00:00.000000Z",
                    rollup="merchant_currency")
            execution = uuid4()
            message = {"execution": execution.hex, "job": uuid4().hex, "fixture": fixture,
                       "case": case, "contract": encode(canonical_bytes(contract))}
            raw = canonical_bytes(message)
            intent = PRIVATE / "evidence" / (execution.hex + ".verifier-intent.json")
            with intent.open("xb") as file:
                file.write(raw)
                file.flush()
                os.fsync(file.fileno())
            reply = host("/usr/bin/python3 -I -B " + target + "/probe_verifier_controller.py", raw)
            (PRIVATE / "evidence" / (execution.hex + ".verifier-receipt.json")).write_bytes(reply)
            result = json.loads(reply)
            run = result["result"]
            worker = run["worker"]
            if (run["intent"]["execution"] != execution.hex or worker["cleanup"] != "confirmed"
                    or worker["collected"] is not True or worker["runtime_client_exit_code"] != 0
                    or run["semantic"] is None or run["semantic"]["cleanup_confirmed"] is not True):
                raise RuntimeError("CRITICAL_WORKER_OR_VERIFIER_GATE_FAILED")
            report = run["semantic"]["report"]
            expected = "match" if fixture == "canary_correct" else "mismatch"
            blocked = (5 if extended else 4) if case == "quarantine" else 0
            if (report["status"] != "processed" or report["result"]["comparison"] != expected
                    or report["result"]["blocking_occurrences"] != blocked):
                raise RuntimeError("CANARY_PROBE_EXPECTATION_FAILED")
            if fixture == "wrong_owner" and "V04" not in {
                    f["check"] for f in report["result"]["findings"]}:
                raise RuntimeError("OWNERSHIP_CANARY_NOT_DETECTED")
            if fixture == "wrong_owner":
                witnesses = report["result"]["ownership_witnesses"]
                if not witnesses or not any(
                        w["expected_owner"] != w["actual_owner"] for w in witnesses):
                    raise RuntimeError("SOURCE_OWNERSHIP_WITNESS_MISSING")
            summary = {**run["intent"], "fixture": fixture, "extended": extended,
                       "generation_report_sha256": result["generation_report_sha256"],
                       "seed_sha256": result["seed_sha256"],
                       "verification_report_sha256": run["semantic"]["report_sha256"],
                       "comparison": expected, "blocking_occurrences": blocked,
                       "checks": sorted({f["check"] for f in report["result"]["findings"]}),
                       "output_sha256": report["result"]["output_hashes"], "cleanup": "confirmed"}
            summaries.append(summary)
            print(json.dumps({"fixture": fixture, "case": case, "extended": extended,
                              "comparison": expected, "blocking": blocked}), flush=True)
        evidence = {"observed_at": datetime.now(UTC).isoformat(), "deployment": identifier,
                    "rootfs_sha256": deployment["rootfs_sha256"], "boundary": boundary,
                    "probes": summaries, "sources": source_hashes, "provider_calls": 0,
                    "product_api_queue": "NOT_RUN", "independent_human_review": "NOT_AVAILABLE"}
        (PRIVATE / "evidence/verifier-probes-latest.json").write_text(
            json.dumps(evidence, indent=2))
        print(json.dumps({"deployed_canary_cases_passed": len(summaries), "provider_calls": 0}))
    finally:
        admin.close()


if __name__ == "__main__":
    main()
