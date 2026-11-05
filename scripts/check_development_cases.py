"""Deploy inert fixed development fixtures, prove original faults + positive controls.

Not A/B/C/D results, held-out scoring, product API intake or human oracle review.
Every payload executes only on the designated worker via the existing bounded verifier.
"""

import hashlib
import io
import json
import sys
import tarfile
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from product_live_session import LiveSession, require  # noqa: E402
from vultr_phase1 import PRIVATE, ROOT  # noqa: E402

from contracts.codec import canonical_bytes  # noqa: E402
from eval.development import cases, inventory  # noqa: E402
from orchestrator.repair_evidence import bind_sources, classify  # noqa: E402


def main():
    dataset, declared = cases(), inventory()
    verifier = json.loads((PRIVATE / "evidence/verifier-deployment.json").read_bytes())
    reference = (ROOT / "tests/fixtures/phase2/canary_correct.py.txt").read_bytes()
    settings = {"verifier_path": "/opt/proofflow-verifier/" + verifier["deployment"],
                "verifier_sha256": verifier["rootfs_sha256"],
                "reference_sha256": hashlib.sha256(reference).hexdigest(),
                "cases": {c["id"]: {"file_hashes": c["file_hashes"]} for c in dataset}}
    files = {"settings.json": canonical_bytes(settings), "reference.py.txt": reference,
             "probe.py": (ROOT / "scripts/probe_development_controller.py").read_bytes()}
    for case in dataset:
        files.update({case["id"] + "/" + name: raw for name, raw in case["files"].items()})
    hashes = {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}
    revision = hashlib.sha256(canonical_bytes(hashes)).hexdigest()
    target = "/opt/proofflow-evaluation/" + revision
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as tar:
        for name, raw in files.items():
            entry = tarfile.TarInfo(name)
            entry.size, entry.mode = len(raw), 0o400
            tar.addfile(entry, io.BytesIO(raw))
    folder = PRIVATE / "evidence" / ("phase5-development-" + uuid4().hex)
    folder.mkdir(mode=0o700)
    summary = {"observed_at": datetime.now(UTC).isoformat(), "revision": revision,
               "inventory": declared, "runs": [], "model_calls": 0,
               "scope": "development_fixture_fault_detection_and_positive_controls_only"}
    try:
        with LiveSession() as live:
            summary["credit"] = live.credit
            require(live.sql("SELECT count(*)=1 AND bool_and(blocked) FROM pf_budget.accounts;",
                             "proofflow_budget") == b"t", "INFERENCE_MUST_STAY_BLOCKED")
            exists = live.host("test -d " + target + " && echo present || echo absent")
            if exists == b"absent":
                live.host("install -d -m 0700 " + target)
                live.host("tar -xf - --no-same-owner -C " + target, archive.getvalue())
            for name, digest in hashes.items():
                require(live.host("sha256sum " + target + "/" + name).decode().split()[0]
                        == digest, "EVALUATION_INSTALLED_SOURCE_CHANGED")
            for case in dataset:
                for variant in ("fault", "reference"):
                    message = {"case": case["id"], "variant": variant,
                               "execution": uuid4().hex, "job": uuid4().hex}
                    raw = canonical_bytes(message)
                    (folder / (message["execution"] + ".intent.json")).write_bytes(raw)
                    started = time.monotonic()
                    reply = live.host("/usr/bin/python3 -I -B " + target + "/probe.py", raw)
                    (folder / (message["execution"] + ".result.json")).write_bytes(reply)
                    result = json.loads(reply)
                    intent = result["intent"]
                    require(intent["execution"] == message["execution"]
                            and intent["job"] == message["job"] and intent["generation"] == 1,
                            "DEVELOPMENT_EXECUTION_BINDING")
                    bind_sources(intent, source=(reference if variant == "reference" else
                        case["files"]["pipeline.py.txt"]), contract=case["files"]["contract.json"],
                        transactions=case["files"]["transactions.csv"],
                        customers=case["files"]["customers.csv"],
                        runtime=live.policy["runtime_sha256"], verifier=verifier["rootfs_sha256"],
                        purpose="original")
                    decision, _ = classify(result, intent, live.policy["runtime_sha256"],
                                           verifier["rootfs_sha256"])
                    require(result["worker"]["cleanup"] == "confirmed", "WORKER_CLEANUP_FAILED")
                    semantic = result.get("semantic")
                    comparison, blocked = None, None
                    if semantic is not None:
                        require(semantic["cleanup_confirmed"] is True, "VERIFIER_CLEANUP_FAILED")
                        report = semantic["report"]
                        if report["status"] == "processed":
                            comparison = report["result"]["comparison"]
                            blocked = report["result"]["blocking_occurrences"]
                    passed = decision in ("mismatch", "rejected") if variant == "fault" else (
                        decision in ("match", "held") and blocked == case["oracle_summary"][
                            "blocking_occurrences"])
                    # A failed transport/verifier is not evidence that a source fault was detected.
                    if variant == "fault" and semantic is None:
                        passed = (type(result["worker"].get("runtime_client_exit_code")) is int
                                  and result["worker"]["runtime_client_exit_code"] == 1
                                  and result["worker"]["outcome"] in ("exited", "output_rejected"))
                    entry = {**message, "passed": passed, "comparison": comparison,
                             "blocking_occurrences": blocked,
                             "seconds": round(time.monotonic() - started, 3),
                             "receipt_sha256": hashlib.sha256(reply).hexdigest(),
                             "cleanup": "confirmed"}
                    summary["runs"].append(entry)
                    print(json.dumps(entry), flush=True)
                    require(passed, "DEVELOPMENT_CASE_VALIDATION_FAILED")
            summary["passed"] = True
    finally:
        (folder / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps({"revision": revision, "passed": summary.get("passed", False),
                          "worker_runs": len(summary["runs"]), "model_calls": 0}))


if __name__ == "__main__":
    main()
