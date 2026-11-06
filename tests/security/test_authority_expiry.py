"""Real SQLite replay-record expiry and clock rollback checks; no code execution."""

import sqlite3
import sys
from dataclasses import replace
from uuid import uuid4

import pytest

from worker.journal import RECEIPT_TTL, Journal
from worker.protocol import ExecutionRequest, SupervisorError, authority_id, authority_time

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux worker journal")


def request():
    return ExecutionRequest(authority_id(), authority_id(), 1, b"inert", b"", b"", b"{}")


def start(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    monkeypatch.setattr("worker.journal.time.time", lambda: 1000)
    journal, item = Journal(tmp_path), request()
    assert item.job_id.version == 7 and authority_time(item.job_id) == 1000
    journal.admit(item, "a" * 64)
    return journal, item


def test_retired_id_and_fence_never_reopen_even_after_clock_rollback(tmp_path, monkeypatch):
    journal, item = start(tmp_path, monkeypatch)
    journal.finish(item.execution_id, {"cleanup": "confirmed"}, cleaned=True)
    monkeypatch.setattr("worker.journal.time.time", lambda: 1000 + RECEIPT_TTL)
    assert journal.prune_authority() == {"executions": 1, "fences": 1}
    assert journal.receipt(item.execution_id) is None
    with pytest.raises(SupervisorError, match="EXPIRED"):
        journal.admit(item, "a" * 64)
    monkeypatch.setattr("worker.journal.time.time", lambda: 1000)
    journal = Journal(tmp_path)
    with pytest.raises(SupervisorError, match="EXPIRED"):
        journal.admit(item, "a" * 64)
    with pytest.raises(SupervisorError, match="EXPIRED"):
        journal.fence(item.job_id, 9)


def test_expired_job_cannot_gain_fresh_execution_id(tmp_path, monkeypatch):
    journal, item = start(tmp_path, monkeypatch)
    journal.finish(item.execution_id, {"cleanup": "confirmed"}, cleaned=True)
    monkeypatch.setattr("worker.journal.time.time", lambda: 1000 + RECEIPT_TTL)
    journal.prune_authority()
    with pytest.raises(SupervisorError, match="EXPIRED"):
        journal.admit(replace(item, execution_id=authority_id(), generation=2), "a" * 64)


def test_legacy_unknown_ids_rejected_and_legacy_record_reconciled_until_retired(
    tmp_path, monkeypatch
):
    journal, item = start(tmp_path, monkeypatch)
    legacy = replace(item, execution_id=uuid4(), job_id=uuid4())
    with pytest.raises(SupervisorError, match="EXPIRING_AUTHORITY_ID_REQUIRED"):
        journal.admit(legacy, "a" * 64)
    # A labeled legacy fixture represents already-admitted history, not execution.
    import hashlib

    digest = hashlib.sha256((legacy.manifest_hash() + "a" * 64).encode()).hexdigest()
    with sqlite3.connect(journal.path) as db:
        db.execute(
            "INSERT INTO executions(id,job,generation,manifest,state,retire_at) "
            "VALUES(?,?,?,?,?,?)",
            (legacy.execution_id.hex, legacy.job_id.hex, 1, digest, "CLEANED", 1000 + RECEIPT_TTL),
        )
        db.execute("INSERT INTO fences VALUES(?,?,?)", (legacy.job_id.hex, 1, 1000 + RECEIPT_TTL))
    assert not journal.admit(legacy, "a" * 64)
    monkeypatch.setattr("worker.journal.time.time", lambda: 1000 + RECEIPT_TTL)
    journal.prune_authority()
    with pytest.raises(SupervisorError, match="EXPIRING_AUTHORITY_ID_REQUIRED"):
        journal.admit(legacy, "a" * 64)


def test_quarantine_and_active_fences_survive_expiry(tmp_path, monkeypatch):
    journal, item = start(tmp_path, monkeypatch)
    journal.finish(item.execution_id, {"cleanup": "uncertain"}, cleaned=False)
    monkeypatch.setattr("worker.journal.time.time", lambda: 1000 + RECEIPT_TTL)
    assert journal.prune_authority() == {"executions": 0, "fences": 0}
    assert journal.unfinished() == [item.execution_id]
    journal.fence(item.job_id, 2)  # Cleanup fencing remains available, never admission.
    with pytest.raises(SupervisorError, match="JOB_AUTHORITY_EXPIRED"):
        journal.admit(replace(item, execution_id=authority_id(), generation=2), "a" * 64)
    journal.finish(item.execution_id, {"cleanup": "confirmed"}, cleaned=True)
    assert journal.prune_authority() == {"executions": 1, "fences": 1}


def test_busy_reader_does_not_claim_physical_retirement(tmp_path, monkeypatch):
    journal, item = start(tmp_path, monkeypatch)
    journal.finish(item.execution_id, {"cleanup": "confirmed"}, cleaned=True)
    reader = sqlite3.connect(journal.path, isolation_level=None)
    reader.execute("BEGIN")
    reader.execute("SELECT * FROM executions").fetchall()
    monkeypatch.setattr("worker.journal.time.time", lambda: 1000 + RECEIPT_TTL)
    try:
        with pytest.raises(SupervisorError, match="AUTHORITY_CHECKPOINT_BUSY"):
            journal.prune_authority()
    finally:
        reader.close()
    assert journal.prune_authority() == {"executions": 0, "fences": 0}
    for path in tmp_path.iterdir():
        assert item.execution_id.hex.encode() not in path.read_bytes()


def test_future_identity_rejected(tmp_path, monkeypatch):
    journal, _ = start(tmp_path, monkeypatch)
    monkeypatch.setattr("worker.journal.time.time", lambda: 2000)
    future = request()
    monkeypatch.setattr("worker.journal.time.time", lambda: 1000)
    with pytest.raises(SupervisorError, match="FUTURE"):
        journal.admit(future, "a" * 64)
