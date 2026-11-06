"""Linux SQLite retention checks using inert receipts, never candidate execution."""

import json
import os
import sqlite3
import sys
from dataclasses import replace

import pytest

from worker.journal import Journal
from worker.protocol import ExecutionRequest, SupervisorError, authority_id

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux worker ownership")


def request():
    return ExecutionRequest(authority_id(), authority_id(), 1, b"# inert", b"", b"", b"{}")


def test_expiry_removes_bytes_preserves_replay_conflict_and_fence(tmp_path, monkeypatch):
    monkeypatch.setattr("worker.journal.time.time", lambda: 1000)
    tmp_path.chmod(0o700)
    journal, item = Journal(tmp_path), request()
    assert journal.admit(item, "a" * 64)
    preview = "UNIQUE_INERT_RAW_PREVIEW_" + "x" * 500
    journal.finish(item.execution_id, {"cleanup": "confirmed", "outcome": "output_rejected",
                   "failure_log_preview": preview}, cleaned=True)
    assert journal.prune_failure_previews() == 0
    assert journal.receipt(item.execution_id)["failure_log_preview"] == preview
    monkeypatch.setattr("worker.journal.time.time", lambda: 1301)
    assert journal.prune_failure_previews() == 1
    receipt = journal.receipt(item.execution_id)
    assert receipt["failure_log_preview_retired"] is True
    assert "failure_log_preview" not in receipt and receipt["cleanup"] == "confirmed"
    assert len(receipt["failure_log_preview_sha256"]) == 64
    for path in tmp_path.iterdir():
        assert preview.encode() not in path.read_bytes()
    reopened = Journal(tmp_path)
    assert reopened.prune_failure_previews() == 0
    assert reopened.receipt(item.execution_id) == receipt
    assert not reopened.admit(item, "a" * 64)
    with pytest.raises(SupervisorError, match="CONFLICT"):
        reopened.admit(replace(item, pipeline=b"changed"), "a" * 64)
    reopened.fence(item.job_id, 2)
    with pytest.raises(SupervisorError, match="STALE_EXECUTION_GENERATION"):
        reopened.admit(replace(item, execution_id=authority_id()), "a" * 64)


def test_legacy_migration_gets_one_grace_period_and_keeps_quarantine(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    path, item = tmp_path / "journal.sqlite3", request()
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE executions(id TEXT PRIMARY KEY,job TEXT,generation INTEGER,"
                   "manifest TEXT,state TEXT,cancel INTEGER DEFAULT 0,receipt TEXT,"
                   "UNIQUE(job,generation))")
        db.execute("INSERT INTO executions VALUES(?,?,?,?,?,0,?)", (item.execution_id.hex,
                   item.job_id.hex, 1, "a" * 64, "QUARANTINED",
                   json.dumps({"cleanup": "uncertain", "failure_log_preview": "inert"})))
    path.chmod(0o600)
    monkeypatch.setattr("worker.journal.time.time", lambda: 1000)
    Journal(tmp_path)
    monkeypatch.setattr("worker.journal.time.time", lambda: 1299)
    assert Journal(tmp_path).prune_failure_previews() == 0
    monkeypatch.setattr("worker.journal.time.time", lambda: 1301)
    journal = Journal(tmp_path)
    assert journal.prune_failure_previews() == 1
    assert journal.unfinished() == [item.execution_id]
    assert journal.scoped_status(item.execution_id, item.job_id, 1)["state"] == "QUARANTINED"
    with pytest.raises(SupervisorError, match="WORKER_QUARANTINED"):
        journal.admit(request(), "a" * 64)


def test_checkpoint_failure_is_retryable_without_restoring_raw_preview(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    monkeypatch.setattr("worker.journal.time.time", lambda: 1000)
    journal, item = Journal(tmp_path), request()
    journal.admit(item, "a" * 64)
    journal.finish(item.execution_id, {"failure_log_preview": "inert"}, cleaned=True)
    # A real long reader pins old WAL frames. It must not be reported retired fully.
    reader = sqlite3.connect(journal.path, isolation_level=None)
    reader.execute("BEGIN")
    reader.execute("SELECT * FROM executions").fetchall()
    monkeypatch.setattr("worker.journal.time.time", lambda: 1301)
    try:
        with pytest.raises(SupervisorError, match="CHECKPOINT_BUSY"):
            journal.prune_failure_previews()
    finally:
        reader.close()
    assert journal.prune_failure_previews() == 0
    assert "failure_log_preview" not in journal.receipt(item.execution_id)
    assert not (tmp_path / "journal.sqlite3-wal").exists() or os.stat(
        tmp_path / "journal.sqlite3-wal").st_size == 0
