"""Scheduling/registry policy only; no cloud or filesystem mutation."""

import hashlib
import importlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from orchestrator.asset_backup import seal
from tests.security.test_asset_backup import NOW, fixture


def module(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    return importlib.import_module("scripts.scheduled_product_backup")


def test_due_and_clock_rollback(monkeypatch):
    m = module(monkeypatch)
    now = datetime(2026, 11, 8, tzinfo=UTC)
    previous = {
        "snapshot_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=24)).isoformat(),
    }
    assert m.due(None, now)
    assert not m.due(previous, now + timedelta(hours=11))
    assert m.due(previous, now + timedelta(hours=12))
    with pytest.raises(RuntimeError, match="CLOCK"):
        m.due(previous, now - timedelta(seconds=1))
    previous["expires_at"] = (now + timedelta(hours=3)).isoformat()
    assert m.due(previous, now + timedelta(hours=1))


def test_duplicate_blob_uses_earliest_retention_timestamp(monkeypatch):
    m = module(monkeypatch)
    first = {
        "workspace_id": str(uuid4()),
        "sha256": "a" * 64,
        "byte_size": 4,
        "created_at": "2026-11-07T00:00:00+00:00",
    }
    later = {**first, "created_at": "2026-11-08T00:00:00+00:00"}
    assert m.unique_registry([later, first]) == [first]
    with pytest.raises(RuntimeError, match="CONFLICT"):
        m.unique_registry([first, {**later, "byte_size": 5}])
    with pytest.raises(RuntimeError, match="LIMIT"):
        m.unique_registry([first] * 257)


@pytest.mark.parametrize("fault", [None, "missing_key", "receipt", "corrupt_envelope", "snapshot"])
def test_not_due_still_authenticates_backup_without_cloud(monkeypatch, tmp_path, fault):
    m = module(monkeypatch)
    snapshot, assets, key = fixture()
    raw = seal(snapshot, assets, b"inert synthetic database", key, now=NOW)
    payload = m.open_backup(raw, key, now=NOW)
    latest = tmp_path / "latest.json"
    latest.write_text(
        json.dumps(
            {
                "backup_id": "synthetic-only",
                "snapshot_at": NOW.isoformat(),
                "expires_at": payload["expires_at"],
                "encrypted_sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    )
    monkeypatch.setattr(m, "LATEST", latest)
    monkeypatch.setattr(m, "expire", lambda: None)
    monkeypatch.setattr(m, "datetime", type("Clock", (datetime,), {"now": lambda _: NOW}))

    def recover(_):
        if fault == "missing_key":
            raise FileNotFoundError("vault key absent")
        return raw[:-1] + bytes([raw[-1] ^ 1]) if fault == "corrupt_envelope" else raw, key

    monkeypatch.setattr(m, "recover", recover)
    monkeypatch.setattr(m, "LiveSession", lambda: pytest.fail("No cloud check needed for not_due"))
    if fault in {"receipt", "snapshot"}:
        value = json.loads(latest.read_bytes())
        if fault == "receipt":
            value["encrypted_sha256"] = "0" * 64
        else:
            value["snapshot_at"] = (NOW-timedelta(minutes=1)).isoformat()
        latest.write_text(json.dumps(value))
    if fault:
        with pytest.raises((FileNotFoundError, RuntimeError, ValueError)):
            m.run()
    else:
        assert m.run()["scheduled_backup"] == "not_due"
