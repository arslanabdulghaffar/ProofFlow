"""One reviewed polling-only amendment; preserve four dispatched runs, never replay them."""

import hashlib
import json
import sys
import tarfile
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from comparison_api import save  # noqa: E402
from product_live_session import LiveSession, require  # noqa: E402
from run_comparison import SOURCES, closed, dispatch, refresh  # noqa: E402
from vultr_phase1 import PRIVATE, ROOT  # noqa: E402

from eval.report import digest  # noqa: E402

ORIGINAL_SOURCE = "13d33003d202e0afeefbd9d311b612b3ee7adb6be54466fe0f1332a33c181555"


def validate(root, freeze):
    require(
        freeze["plan"]["freeze"]["source"] == ORIGINAL_SOURCE, "COMPARISON_AMENDMENT_WRONG_CAMPAIGN"
    )
    jobs = freeze["jobs"]
    require(
        len(jobs) == 96 and [j["arm"] for j in jobs[:4]] == ["B", "D", "C", "A"],
        "COMPARISON_AMENDMENT_WRONG_ORDER",
    )
    expected = {"dispatch-" + j["run_id"] + ".json" for j in jobs[:4]}
    require(
        {p.name for p in root.glob("dispatch-*.json")} == expected, "COMPARISON_UNEXPECTED_DISPATCH"
    )
    for job in jobs[:4]:
        require(
            json.loads((root / ("closed-" + job["run_id"] + ".json")).read_bytes())
            == {"admission": False, "inference": False},
            "COMPARISON_CLOSURE_UNCONFIRMED",
        )
    for job in jobs[:3]:
        result = json.loads((root / ("result-" + job["run_id"] + ".json")).read_bytes())
        require(
            all(result[k] == job[k] for k in job)
            and result["cleanup"] == "confirmed"
            and not result.get("critical"),
            "COMPARISON_PREVIOUS_RESULT_UNCONFIRMED",
        )
    folder = root / jobs[3]["run_id"]
    failure = json.loads((folder / "result.json").read_bytes())
    premature = json.loads((folder / "original.json").read_bytes())
    reconciled = json.loads((folder / "original-reconciled.json").read_bytes())
    require(
        failure["critical"] is True
        and failure["stage"] == "original"
        and failure["calls"] == []
        and premature["state"] == "BASELINE_RUNNING"
        and reconciled["state"] == "CANCELLED"
        and reconciled["worker_receipt"]["cleanup"] == "confirmed",
        "COMPARISON_FAILURE_NOT_RECONCILED",
    )
    return jobs, folder, reconciled


def frozen_files(root, freeze):
    with tarfile.open(root / "frozen-sources.tar", "r:") as archive:
        members = archive.getmembers()
        require(
            len(members) == len(freeze["shipped"])
            and {m.name for m in members} == set(freeze["shipped"])
            and all(m.isfile() and 0 <= m.size <= 5242880 for m in members),
            "COMPARISON_ARCHIVE_INVALID",
        )
        files = {
            m.name: archive.extractfile(m).read() for m in members
        }  # Never extract paths/code.
    require(
        all(
            hashlib.sha256(raw).hexdigest() == freeze["shipped"][name]
            for name, raw in files.items()
        ),
        "COMPARISON_FROZEN_BYTES_CHANGED",
    )
    return files


def main():
    require(sys.argv[1:] == [], "COMPARISON_AMENDMENT_ARGUMENTS_FORBIDDEN")
    root = PRIVATE / "evidence/final-comparison-v1"
    require(not (root / "polling-amendment.json").exists(), "COMPARISON_AMENDMENT_ALREADY_STARTED")
    freeze = json.loads((root / "freeze.json").read_bytes())
    jobs, folder, reconciled = validate(root, freeze)
    files = frozen_files(root, freeze)
    settings = json.loads(files["settings.json"])
    require(
        settings["jobs"] == jobs and settings["campaign_sha256"] == digest(freeze["plan"]),
        "COMPARISON_FROZEN_SETTINGS_CHANGED",
    )
    hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCES}
    require(
        set(hashes) == set(freeze["sources"])
        and {n for n in hashes if hashes[n] != freeze["sources"][n]}
        == {"scripts/comparison_api.py", "scripts/run_comparison.py"},
        "COMPARISON_UNREVIEWED_SOURCE_CHANGE",
    )
    amended_hashes = {
        **hashes,
        "scripts/continue_comparison.py": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    save(
        root,
        "polling-amendment.json",
        {
            "original_freeze_sha256": hashlib.sha256(
                (root / "freeze.json").read_bytes()
            ).hexdigest(),
            "sources": amended_hashes,
            "start_index": 4,
            "remaining_jobs": jobs[4:],
            "reason": "Missing baseline polling states; gate closure cancelled original",
            "preserved": "all four dispatched records; A remains interrupted with zero model calls",
            "unchanged": "cases/order/prompts/model/rates/runtime/grader/limits; no reruns",
            "disclosure": "polling amendment after three observations; source change disclosed",
        },
    )
    config = refresh()
    require(config["account_id"] == settings["account_id"], "COMPARISON_ACCOUNT_CHANGED")
    with LiveSession() as live:
        closed(live)
        parent = str(UUID(reconciled["id"]))
        workspace = str(UUID(reconciled["workspace_id"]))
        intent = json.loads((folder / "intent.json").read_bytes())
        require(workspace == intent["workspace"], "COMPARISON_WORKSPACE_CHANGED")
        current = json.loads(
            live.sql("SELECT row_to_json(j) FROM pf_product.jobs j WHERE id='" + parent + "';")  # noqa: S608 - canonical UUID
        )
        require(current == reconciled, "COMPARISON_RECONCILED_JOB_CHANGED")
        require(
            live.sql(
                "SELECT count(*) FROM pf_product.repairs WHERE workspace_id='" + workspace + "';"  # noqa: S608 - canonical UUID
            )
            == b"0",
            "COMPARISON_INTERRUPTED_JOB_HAS_REPAIR",
        )
        save(
            folder,
            "retirement-intent.json",
            {"workspace": workspace, "reason": "reconciled cancelled fixture"},
        )
        client = live.login(workspace)
        response = client.post(
            "/v1/workspace/delete", json={"workspace_id": workspace, "confirm": True}
        )
        require(
            response.status_code == 200 and response.json()["access_revoked"] is True,
            "COMPARISON_RETIREMENT_UNCERTAIN",
        )
        save(folder, "retirement-requested.json", response.json())
        live.host("systemctl start proofflow-product-retention.service")
        require(
            live.sql(
                "SELECT count(*) FROM pf_product.deletions WHERE workspace_id='"  # noqa: S608 - canonical UUID
                + workspace
                + "' AND completed_at IS NOT NULL;"
            )
            == b"1",
            "COMPARISON_RETIREMENT_INCOMPLETE",
        )
        assets = "/var/lib/proofflow-product/assets/"
        suffix = UUID(workspace).hex
        require(
            live.host(
                "test ! -e "
                + assets
                + suffix
                + " && test -f "
                + assets
                + ".deleted-"
                + suffix
                + " && echo retired"
            )
            == b"retired",
            "COMPARISON_BYTES_NOT_RETIRED",
        )
        save(
            folder,
            "retirement-completed.json",
            {
                "workspace": workspace,
                "sql_completed": True,
                "bytes_absent": True,
                "restore_marker": True,
                "worker_cleanup": "confirmed",
                "original_outcome": "cancelled",
                "benchmark_record": "preserved_interrupted",
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
        jobs,
        lookup,
        "/opt/proofflow-comparison/" + freeze["revision"],
        "/var/lib/proofflow-comparison-v1",
        settings,
        amended_hashes,
        start=4,
    )


if __name__ == "__main__":
    main()
