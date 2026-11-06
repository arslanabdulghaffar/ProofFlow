"""Offline archive/proof audit fixtures only; never execute archived source."""

import hashlib
import importlib
import io
import json
import tarfile
from pathlib import Path
from uuid import uuid4

import pytest

from worker.protocol import runtime_identity_digest


def module(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    return importlib.import_module("scripts.collect_comparison")


@pytest.mark.parametrize("fault", [None, "link", "traversal", "absolute", "duplicate"])
def test_archive_bounded_regular_reads_without_extraction(tmp_path, monkeypatch, fault):
    audit = module(monkeypatch)
    path = tmp_path / "archive.tar"
    raw = b"inert candidate bytes"
    with tarfile.open(path, "w:") as archive:
        info = tarfile.TarInfo("proofflow-comparison-v1/inert.py.txt")
        info.size = len(raw)
        if fault == "link":
            info.type, info.linkname, info.size = tarfile.SYMTYPE, "/unrelated", 0
        elif fault == "traversal":
            info.name = "proofflow-comparison-v1/../escape"
        elif fault == "absolute":
            info.name = "/proofflow-comparison-v1/escape"
        archive.addfile(info, None if fault == "link" else io.BytesIO(raw))
        if fault == "duplicate":
            archive.addfile(info, io.BytesIO(raw))
    if fault:
        with pytest.raises(RuntimeError):
            audit.archive_bytes(path)
    else:
        assert audit.archive_bytes(path) == {"inert.py.txt": raw}
    assert not (tmp_path / "proofflow-comparison-v1").exists()


def fixture(monkeypatch):
    audit = module(monkeypatch)
    runtime, verifier = runtime_identity_digest({}), "3" * 64
    monkeypatch.setattr(audit, "RUNTIME", runtime)
    monkeypatch.setattr(audit, "VERIFIER", verifier)
    job = {"run_id": str(uuid4()), "arm": "C"}
    case = {"files": {"contract.json": b"{}", "transactions.csv": b"t", "customers.csv": b"c"}}
    source = b"inert candidate"
    digest = hashlib.sha256(source).hexdigest()
    files, executions = {}, []
    for generation, purpose in enumerate(("candidate", "canary_ownership", "canary_quarantine"), 1):
        execution = uuid4().hex
        intent = {
            "execution": execution,
            "job": uuid4().hex,
            "generation": generation,
            "manifest_sha256": "a" * 64,
            "purpose": purpose,
            "pipeline_sha256": digest,
            "runtime_sha256": runtime,
            "verifier_rootfs": verifier,
            "contract_sha256": "b" * 64,
        }
        intent["job"] = job["run_id"].replace("-", "")
        for key, name in (
            ("contract_raw_sha256", "contract.json"),
            ("transactions_sha256", "transactions.csv"),
            ("customers_sha256", "customers.csv"),
        ):
            intent[key] = hashlib.sha256(case["files"][name]).hexdigest()
        outputs = {"ledger.jsonl": "d" * 64, "unresolved.jsonl": "e" * 64}
        checked = {
            "operation": "verify",
            "comparison": "match",
            "finding_count": 0,
            "findings": [],
            "blocking_occurrences": int(purpose == "canary_quarantine"),
            "output_hashes": outputs,
            **{
                k: intent[k] for k in ("contract_sha256", "transactions_sha256", "customers_sha256")
            },
        }
        receipt = {
            "intent": intent,
            "worker": {
                "cleanup": "confirmed",
                "execution": execution,
                "job": intent["job"],
                "generation": generation,
                "manifest": intent["manifest_sha256"],
                "runtime": {},
                "collected": True,
                "runtime_client_exit_code": 0,
                "unit_result": "success",
                "files": [{"name": k, "sha256": v} for k, v in outputs.items()],
            },
            "semantic": {
                "cleanup_confirmed": True,
                "rootfs_sha256": verifier,
                "report": {
                    "version": "proofflow-verifier-v1",
                    "status": "processed",
                    "result": checked,
                },
            },
        }
        base = job["run_id"] + "/executions/" + execution + "/"
        files.update({base + k: v for k, v in case["files"].items()})
        files[base + "pipeline.py.txt"] = source
        files[base + "intent.json"] = json.dumps(intent).encode()
        files[base + "result.json"] = json.dumps(receipt).encode()
        executions.append(
            {
                "execution": execution,
                "purpose": purpose,
                "decision": "held" if purpose == "canary_quarantine" else "match",
            }
        )
    result = {
        "decision": "accepted",
        "grade": "correct",
        "candidate_sha256": digest,
        "executions": executions,
    }
    files[job["run_id"] + "/result.json"] = json.dumps(result).encode()
    return audit, job, result, files, case


def test_full_receipt_source_and_three_fresh_proofs(monkeypatch):
    audit, job, result, files, case = fixture(monkeypatch)
    assert len(audit.audit_controller(job, result, files, case)) == 3


@pytest.mark.parametrize("fault", ["source", "data", "scope", "missing_check", "summary"])
def test_changed_or_incomplete_proof_cannot_pass(monkeypatch, fault):
    audit, job, result, files, case = fixture(monkeypatch)
    base = job["run_id"] + "/executions/" + result["executions"][0]["execution"] + "/"
    if fault == "source":
        files[base + "pipeline.py.txt"] = b"changed"
    elif fault == "data":
        files[base + "transactions.csv"] = b"changed"
    elif fault == "scope":
        intent = json.loads(files[base + "intent.json"])
        intent["job"] = uuid4().hex
        files[base + "intent.json"] = json.dumps(intent).encode()
    elif fault == "missing_check":
        result["executions"].pop()
        files[job["run_id"] + "/result.json"] = json.dumps(result).encode()
    else:
        result["grade"] = "incorrect"
    from orchestrator.repair_proposal import RepairRejected

    with pytest.raises((RuntimeError, RepairRejected)):
        audit.audit_controller(job, result, files, case)


@pytest.mark.parametrize("fault", [None, "extra", "job", "open", "retirement", "workspace"])
def test_all_dispatches_closed_and_api_retired(tmp_path, monkeypatch, fault):
    audit = module(monkeypatch)
    job = {"run_id": str(uuid4()), "arm": "A", "case": "synthetic", "repeat": 1}
    identifier = job["run_id"]
    folder = tmp_path / identifier
    folder.mkdir()
    (folder / "result.json").write_text(json.dumps({"workspace": "fixture"}))
    retired = {"sql_completed": fault != "retirement", "workspace": "fixture"}
    if fault == "workspace":
        retired["workspace"] = "other"
    (folder / "retirement-completed.json").write_text(json.dumps(retired))
    dispatch = {"job": job if fault != "job" else {**job, "arm": "D"}}
    (tmp_path / ("dispatch-" + identifier + ".json")).write_text(json.dumps(dispatch))
    (tmp_path / ("closed-" + identifier + ".json")).write_text(
        json.dumps({"admission": fault == "open", "inference": False})
    )
    if fault == "extra":
        (tmp_path / "dispatch-extra.json").write_text("{}")
    if fault:
        with pytest.raises(RuntimeError):
            audit.lifecycle(tmp_path, [job])
    else:
        audit.lifecycle(tmp_path, [job])


@pytest.mark.parametrize("fault", [None, "wrong_job", "changed_source", "already_correct"])
def test_api_original_binds_actual_failure_not_just_repair_label(tmp_path, monkeypatch, fault):
    audit, job, result, files, case = fixture(monkeypatch)
    base = job["run_id"] + "/executions/" + result["executions"][0]["execution"] + "/"
    receipt = json.loads(files[base + "result.json"])
    receipt["intent"]["purpose"] = "original"
    if fault != "already_correct":
        receipt["worker"]["runtime_client_exit_code"] = 1
    case["files"]["pipeline.py.txt"] = files[base + "pipeline.py.txt"]
    original = {"id": job["run_id"], "state": "NEEDS_REVIEW", "report": receipt}
    if fault == "wrong_job":
        original["id"] = str(uuid4())
    if fault == "changed_source":
        case["files"]["pipeline.py.txt"] = b"changed inert source"
    (tmp_path / "original.json").write_text(json.dumps(original))
    settings = {"runtime_sha256": audit.RUNTIME, "verifier_sha256": audit.VERIFIER}
    from orchestrator.repair_proposal import RepairRejected

    if fault:
        with pytest.raises((RuntimeError, RepairRejected)):
            audit.audit_original(tmp_path, result, case, settings)
    else:
        checked = audit.audit_original(tmp_path, result, case, settings)
        assert checked["verdict"] == "execution_failed"
