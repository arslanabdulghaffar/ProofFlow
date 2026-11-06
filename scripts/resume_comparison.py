"""Continue only an undispatched suffix after confirmed between-job transport recovery."""

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from comparison_api import save  # noqa: E402
from continue_comparison import ORIGINAL_SOURCE, frozen_files  # noqa: E402
from product_live_session import LiveSession, require  # noqa: E402
from run_comparison import closed, dispatch, refresh  # noqa: E402
from vultr_phase1 import PRIVATE, ROOT  # noqa: E402


def prefix(root, freeze):
    require(
        freeze["plan"]["freeze"]["source"] == ORIGINAL_SOURCE, "COMPARISON_RECOVERY_WRONG_CAMPAIGN"
    )
    jobs = freeze["jobs"]
    present = {p.name for p in root.glob("dispatch-*.json")}
    count = len(present)
    require(
        4 <= count < len(jobs)
        and present == {"dispatch-" + j["run_id"] + ".json" for j in jobs[:count]},
        "COMPARISON_DISPATCH_PREFIX_UNCERTAIN",
    )
    for index, job in enumerate(jobs[:count]):
        require(
            json.loads((root / ("closed-" + job["run_id"] + ".json")).read_bytes())
            == {"admission": False, "inference": False},
            "COMPARISON_CLOSURE_UNCONFIRMED",
        )
        path = (
            root / job["run_id"] / "result.json"
            if job["arm"] == "A"
            else root / ("result-" + job["run_id"] + ".json")
        )
        result = json.loads(path.read_bytes())
        require(all(result[k] == job[k] for k in job), "COMPARISON_RESULT_IDENTITY_CHANGED")
        if index == 3:
            folder = root / job["run_id"]
            reconciled = json.loads((folder / "original-reconciled.json").read_bytes())
            require(
                result.get("critical")
                and result["calls"] == []
                and reconciled["state"] == "CANCELLED"
                and reconciled["worker_receipt"]["cleanup"] == "confirmed",
                "COMPARISON_INTERRUPTED_PREFIX_UNRECONCILED",
            )
        else:
            require(
                not result.get("critical") and result["cleanup"] in ("confirmed", "no_execution"),
                "COMPARISON_CRITICAL_PREFIX_UNRECONCILED",
            )
        if job["arm"] == "A":
            retired = json.loads((root / job["run_id"] / "retirement-completed.json").read_bytes())
            require(
                retired["sql_completed"] is True and retired["workspace"] == result["workspace"],
                "COMPARISON_PREFIX_RETIREMENT_UNCONFIRMED",
            )
    return count


def main():
    require(sys.argv[1:] == [], "COMPARISON_RECOVERY_ARGUMENTS_FORBIDDEN")
    root = PRIVATE / "evidence/final-comparison-v1"
    freeze = json.loads((root / "freeze.json").read_bytes())
    amendment = json.loads((root / "polling-amendment.json").read_bytes())
    require(
        amendment["original_freeze_sha256"]
        == hashlib.sha256((root / "freeze.json").read_bytes()).hexdigest(),
        "COMPARISON_FREEZE_CHANGED",
    )
    hashes = amendment["sources"]
    require(
        all(
            hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == value
            for name, value in hashes.items()
        ),
        "COMPARISON_AMENDED_SOURCE_CHANGED",
    )
    start = prefix(root, freeze)
    record = "transport-recovery-" + str(start) + ".json"
    require(not (root / record).exists(), "COMPARISON_RECOVERY_ALREADY_STARTED")
    files = frozen_files(root, freeze)
    settings = json.loads(files["settings.json"])
    require(settings["jobs"] == freeze["jobs"], "COMPARISON_FROZEN_JOBS_CHANGED")
    config = refresh()
    require(config["account_id"] == settings["account_id"], "COMPARISON_ACCOUNT_CHANGED")
    with LiveSession() as live:
        closed(live)  # Fresh actual host identity, queue/service/quote/credit checks.
        require(
            json.loads(live.host("cat /etc/proofflow-repair/config.json")) == config,
            "COMPARISON_INSTALLED_QUOTE_CHANGED",
        )
        save(
            root,
            record,
            {
                "start_index": start,
                "undispatched": len(freeze["jobs"]) - start,
                "credit": live.credit,
                "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "reason": "read-only preflight transport recovered; no dispatched run replay",
                "prior_results_preserved": True,
            },
        )
    lookup = {}
    for case in freeze["plan"]["cases"]:
        key = case["id"]
        lookup[key] = {
            **case,
            **settings["cases"][key],
            "files": {
                name: files["cases/" + key + "/" + name]
                for name in settings["cases"][key]["file_hashes"]
            },
        }
    dispatch(
        root,
        freeze["jobs"],
        lookup,
        "/opt/proofflow-comparison/" + freeze["revision"],
        "/var/lib/proofflow-comparison-v1",
        settings,
        hashes,
        start=start,
    )


if __name__ == "__main__":
    main()
