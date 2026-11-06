"""Read-only amendment validation fixtures; no provider/API/worker execution."""

import hashlib
import importlib
import io
import json
import tarfile
from pathlib import Path
from uuid import uuid4

import pytest


def fixture(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    module = importlib.import_module("scripts.continue_comparison")
    jobs = [
        {"run_id": str(uuid4()), "arm": arm, "case": "synthetic", "repeat": 1}
        for arm in "BDCA" * 24
    ]
    freeze = {"jobs": jobs, "plan": {"freeze": {"source": module.ORIGINAL_SOURCE}}}
    for job in jobs[:4]:
        (tmp_path / ("dispatch-" + job["run_id"] + ".json")).write_text("{}")
        (tmp_path / ("closed-" + job["run_id"] + ".json")).write_text(
            json.dumps({"admission": False, "inference": False})
        )
    for job in jobs[:3]:
        (tmp_path / ("result-" + job["run_id"] + ".json")).write_text(
            json.dumps({**job, "cleanup": "confirmed"})
        )
    folder = tmp_path / jobs[3]["run_id"]
    folder.mkdir()
    (folder / "result.json").write_text(
        json.dumps({"critical": True, "stage": "original", "calls": []})
    )
    (folder / "original.json").write_text(json.dumps({"state": "BASELINE_RUNNING"}))
    (folder / "original-reconciled.json").write_text(
        json.dumps({"state": "CANCELLED", "worker_receipt": {"cleanup": "confirmed"}})
    )
    return module, freeze, folder


def test_only_exact_reconciled_prefix_can_continue(tmp_path, monkeypatch):
    module, freeze, folder = fixture(tmp_path, monkeypatch)
    jobs, actual_folder, _ = module.validate(tmp_path, freeze)
    assert len(jobs) == 96 and actual_folder == folder
    (tmp_path / ("dispatch-" + jobs[4]["run_id"] + ".json")).write_text("{}")
    with pytest.raises(RuntimeError, match="UNEXPECTED_DISPATCH"):
        module.validate(tmp_path, freeze)


@pytest.mark.parametrize("fault", ["cleanup", "closure", "order", "campaign"])
def test_unresolved_or_different_campaign_is_rejected(tmp_path, monkeypatch, fault):
    module, freeze, folder = fixture(tmp_path, monkeypatch)
    if fault == "cleanup":
        (folder / "original-reconciled.json").write_text(
            json.dumps({"state": "CANCELLED", "worker_receipt": {"cleanup": "unknown"}})
        )
    elif fault == "closure":
        (tmp_path / ("closed-" + freeze["jobs"][0]["run_id"] + ".json")).write_text("{}")
    elif fault == "order":
        freeze["jobs"][0]["arm"] = "A"
    else:
        freeze["plan"]["freeze"]["source"] = "f" * 64
    with pytest.raises(RuntimeError):
        module.validate(tmp_path, freeze)


@pytest.mark.parametrize("linked", [False, True])
def test_archive_reads_only_bound_bytes_never_extracts_paths(tmp_path, monkeypatch, linked):
    module, freeze, _ = fixture(tmp_path, monkeypatch)
    raw = b"inert text, never executed"
    freeze["shipped"] = {"cases/synthetic/pipeline.py.txt": hashlib.sha256(raw).hexdigest()}
    with tarfile.open(tmp_path / "frozen-sources.tar", "w:") as archive:
        member = tarfile.TarInfo("cases/synthetic/pipeline.py.txt")
        member.size = len(raw)
        if linked:
            member.type, member.linkname, member.size = tarfile.SYMTYPE, "/unrelated", 0
        archive.addfile(member, None if linked else io.BytesIO(raw))
    if linked:
        with pytest.raises(RuntimeError, match="ARCHIVE_INVALID"):
            module.frozen_files(tmp_path, freeze)
    else:
        assert module.frozen_files(tmp_path, freeze) == {"cases/synthetic/pipeline.py.txt": raw}
    assert not (tmp_path / "cases").exists()
