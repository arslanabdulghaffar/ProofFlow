"""Undispatched-suffix validation only; no network or candidate execution."""

import importlib
import json
from pathlib import Path
from uuid import uuid4

import pytest


def fixture(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    module = importlib.import_module("scripts.resume_comparison")
    arms = "BDCACABDA" + "B" * 87
    jobs = [{"run_id": str(uuid4()), "arm": arm, "case": "synthetic", "repeat": 1} for arm in arms]
    freeze = {"jobs": jobs, "plan": {"freeze": {"source": module.ORIGINAL_SOURCE}}}
    for index, job in enumerate(jobs[:9]):
        (tmp_path / ("dispatch-" + job["run_id"] + ".json")).write_text("{}")
        (tmp_path / ("closed-" + job["run_id"] + ".json")).write_text(
            json.dumps({"admission": False, "inference": False})
        )
        result = {**job, "cleanup": "confirmed", "calls": [], "workspace": str(uuid4())}
        if job["arm"] == "A":
            folder = tmp_path / job["run_id"]
            folder.mkdir()
            if index == 3:
                result["critical"] = True
                (folder / "original-reconciled.json").write_text(
                    json.dumps({"state": "CANCELLED", "worker_receipt": {"cleanup": "confirmed"}})
                )
            (folder / "result.json").write_text(json.dumps(result))
            (folder / "retirement-completed.json").write_text(
                json.dumps({"workspace": result["workspace"], "sql_completed": True})
            )
        else:
            (tmp_path / ("result-" + job["run_id"] + ".json")).write_text(json.dumps(result))
    return module, freeze


def test_recovery_starts_after_all_nine_dispatches(tmp_path, monkeypatch):
    module, freeze = fixture(tmp_path, monkeypatch)
    assert module.prefix(tmp_path, freeze) == 9


@pytest.mark.parametrize("fault", ["hole", "unclosed", "no_result", "critical", "not_retired"])
def test_uncertain_prefix_cannot_be_replayed_or_skipped(tmp_path, monkeypatch, fault):
    module, freeze = fixture(tmp_path, monkeypatch)
    jobs = freeze["jobs"]
    if fault == "hole":
        (tmp_path / ("dispatch-" + jobs[5]["run_id"] + ".json")).unlink()
    elif fault == "unclosed":
        (tmp_path / ("closed-" + jobs[8]["run_id"] + ".json")).write_text("{}")
    elif fault == "no_result":
        (tmp_path / ("result-" + jobs[7]["run_id"] + ".json")).unlink()
    elif fault == "critical":
        path = tmp_path / ("result-" + jobs[7]["run_id"] + ".json")
        value = json.loads(path.read_bytes())
        value["critical"] = True
        path.write_text(json.dumps(value))
    else:
        (tmp_path / jobs[8]["run_id"] / "retirement-completed.json").unlink()
    with pytest.raises((RuntimeError, FileNotFoundError)):
        module.prefix(tmp_path, freeze)
