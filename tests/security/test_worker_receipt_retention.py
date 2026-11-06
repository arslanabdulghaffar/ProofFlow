"""Real Linux SQLite retirement; inert metadata, no candidate execution."""

import json
import sqlite3
import sys
from dataclasses import replace
from uuid import uuid4

import pytest

from worker.journal import RECEIPT_TTL, Journal
from worker.protocol import ExecutionRequest, SupervisorError

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux journal ownership")


def item():
    return ExecutionRequest(uuid4(), uuid4(), 1, b"# inert", b"", b"", b"{}")


def test_retirement_erases_details_and_never_reopens_identity(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    monkeypatch.setattr("worker.journal.time.time", lambda: 1000)
    journal, request = Journal(tmp_path), item()
    journal.admit(request, "a" * 64)
    marker = "INERT_RECEIPT_PRIVATE_DETAIL_" + "z" * 800
    journal.finish(request.execution_id, {"cleanup": "confirmed", "output": marker}, cleaned=True)
    monkeypatch.setattr("worker.journal.time.time", lambda: 1000 + RECEIPT_TTL - 1)
    assert Journal(tmp_path).prune_receipts() == 0
    monkeypatch.setattr("worker.journal.time.time", lambda: 1000 + RECEIPT_TTL)
    assert Journal(tmp_path).prune_receipts() == 1
    for path in tmp_path.iterdir():
        assert marker.encode() not in path.read_bytes()
    journal = Journal(tmp_path)
    retired = journal.receipt(request.execution_id)
    assert retired["verification"] == "NOT_PERFORMED" and not retired["collected"]
    assert retired["outcome"] == "receipt_retired" and journal.unfinished() == []
    assert not journal.admit(request, "a" * 64)
    with pytest.raises(SupervisorError, match="EXECUTION_CONFLICT"):
        journal.admit(replace(request, pipeline=b"changed"), "a" * 64)
    with pytest.raises(SupervisorError, match="EXECUTION_GENERATION_REUSED"):
        journal.admit(replace(request, execution_id=uuid4()), "a" * 64)
    journal.fence(request.job_id, 2)
    with pytest.raises(SupervisorError, match="STALE_EXECUTION_GENERATION"):
        journal.admit(replace(request, execution_id=uuid4()), "a" * 64)
    assert journal.prune_receipts() == 0


def test_quarantine_deadline_survives_recovery_and_restart(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    monkeypatch.setattr("worker.journal.time.time", lambda: 1000)
    journal, request = Journal(tmp_path), item()
    journal.admit(request, "a" * 64)
    journal.finish(request.execution_id, {"cleanup": "uncertain", "detail": "inert"}, cleaned=False)
    monkeypatch.setattr("worker.journal.time.time", lambda: 1001 + RECEIPT_TTL)
    journal = Journal(tmp_path)
    assert journal.prune_receipts() == 0
    assert journal.unfinished() == [request.execution_id]
    with pytest.raises(SupervisorError, match="WORKER_QUARANTINED"):
        journal.admit(item(), "a" * 64)
    journal.finish(request.execution_id, {"cleanup": "confirmed"}, cleaned=True)
    assert journal.prune_receipts() == 1  # Recovery must not renew an old deadline.


def test_legacy_cleaned_receipt_gets_only_one_grace(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    request, path = item(), tmp_path / "journal.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE executions(id TEXT PRIMARY KEY,job TEXT,generation INTEGER,"
                   "manifest TEXT,state TEXT,cancel INTEGER DEFAULT 0,receipt TEXT,"
                   "preview_expires_at REAL,UNIQUE(job,generation))")
        db.execute("INSERT INTO executions VALUES(?,?,?,?,?,0,?,NULL)",
                   (request.execution_id.hex, request.job_id.hex, 1, "a" * 64, "CLEANED",
                    json.dumps({"cleanup": "confirmed", "detail": "inert"})))
    path.chmod(0o600)
    monkeypatch.setattr("worker.journal.time.time", lambda: 1000)
    Journal(tmp_path)
    monkeypatch.setattr("worker.journal.time.time", lambda: 1000 + RECEIPT_TTL)
    assert Journal(tmp_path).prune_receipts() == 1


def test_wal_reader_blocks_completion_then_checkpoint_retries(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    monkeypatch.setattr("worker.journal.time.time", lambda: 1000)
    journal, request = Journal(tmp_path), item()
    journal.admit(request, "a" * 64)
    journal.finish(request.execution_id, {"cleanup": "confirmed", "detail": "inert"}, cleaned=True)
    reader = sqlite3.connect(journal.path, isolation_level=None)
    reader.execute("BEGIN")
    reader.execute("SELECT * FROM executions").fetchall()
    monkeypatch.setattr("worker.journal.time.time", lambda: 1000 + RECEIPT_TTL)
    try:
        with pytest.raises(SupervisorError, match="WORKER_RECEIPT_CHECKPOINT_BUSY"):
            journal.prune_receipts()
        assert journal.receipt(request.execution_id)["receipt_retired"]
    finally:
        reader.close()
    assert Journal(tmp_path).prune_receipts() == 0


def test_each_sweep_is_bounded(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    monkeypatch.setattr("worker.journal.time.time", lambda: 1000)
    journal = Journal(tmp_path)
    for _ in range(33):
        request = item()
        journal.admit(request, "a" * 64)
        journal.finish(request.execution_id, {"cleanup": "confirmed"}, cleaned=True)
    monkeypatch.setattr("worker.journal.time.time", lambda: 1000 + RECEIPT_TTL)
    assert journal.prune_receipts() == 32
    assert journal.prune_receipts() == 1
