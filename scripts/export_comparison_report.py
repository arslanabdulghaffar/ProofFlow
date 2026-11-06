"""Export allowlisted synthetic cases/metrics after real receipt reconciliation.

No deployment, inference, live lookup or source execution. Private raw model
responses, protected canaries, account IDs and credentials stay outside Git.
"""

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from continue_comparison import frozen_files  # noqa: E402
from product_live_session import require  # noqa: E402
from vultr_phase1 import PRIVATE, ROOT  # noqa: E402

from eval.comparison_artifact import FILES, check  # noqa: E402


def main():
    root = PRIVATE / "evidence/final-comparison-v1"
    freeze = json.loads((root / "freeze.json").read_bytes())
    frozen = frozen_files(root, freeze)
    report = json.loads((root / "report.json").read_bytes())
    require(
        report["evidence_validation"] == "ACTUAL_PRIVATE_RECEIPTS_RECONCILED",
        "COMPARISON_RECEIPTS_NOT_RECONCILED",
    )
    cases = [
        {
            "id": case["id"],
            "oracle_summary": freeze["oracles"][case["id"]],
            "files": {
                name: frozen["cases/" + case["id"] + "/" + name].decode("utf-8")
                for name in sorted(FILES)
            },
        }
        for case in freeze["plan"]["cases"]
    ]
    collection = json.loads((root / "collection.json").read_bytes())
    amendment = json.loads((root / "polling-amendment.json").read_bytes())
    artifact = {
        "version": "proofflow-synthetic-comparison-v1",
        "plan": freeze["plan"],
        "cases": cases,
        "records": json.loads((root / "normalized-records.json").read_bytes()),
        "report": report,
        "provenance": {
            "original_sources": freeze["sources"],
            "amended_sources": amendment["sources"],
            "private_remote_receipts_sha256": collection["remote_sha256"],
            "private_receipt_audit_sha256": hashlib.sha256(
                (root / "receipt-audit.json").read_bytes()
            ).hexdigest(),
            "collection_is_not_publication": True,
            "human_oracle_review": False,
            "shared_positive_template_and_fault_families": True,
            "repeated_trials": False,
        },
    }
    check(artifact)
    raw = (json.dumps(artifact, indent=2, sort_keys=True) + "\n").encode()
    require(len(raw) < 4 * 1024 * 1024, "COMPARISON_EXPORT_TOO_LARGE")
    destination = ROOT / "eval/final-comparison-2026-11-06.json"
    with destination.open("xb") as output:
        output.write(raw)
    print(json.dumps({"synthetic_cases": len(cases), "records": len(artifact["records"]),
                      "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}))


if __name__ == "__main__":
    main()
