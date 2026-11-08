"""Receipt swaps must not mislabel an authenticated offline backup. Inert fixtures."""

import hashlib
import json
import sys
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from export_portable_backup import checked_backup  # noqa: E402

from orchestrator.asset_backup import open_backup, seal  # noqa: E402
from orchestrator.restore_guard import RestoreError  # noqa: E402
from tests.security.test_asset_backup import NOW, fixture  # noqa: E402


@pytest.mark.parametrize("change", [None, "encrypted_sha256", "expires_at", "snapshot_at"])
def test_receipt_must_match_authenticated_backup(change):
    snapshot, assets, key = fixture()
    envelope = seal(snapshot, assets, b"inert database", key, now=NOW)
    payload = open_backup(envelope, key, now=NOW)
    receipt = {"encrypted_sha256": hashlib.sha256(envelope).hexdigest(),
               "expires_at": payload["expires_at"], "snapshot_at": snapshot["observed_at"]}
    if change:
        receipt[change] = "different receipt"
        with pytest.raises(RuntimeError, match="PORTABLE_BACKUP_RECEIPT_CHANGED"):
            checked_backup(receipt, envelope, key, now=NOW)
    else:
        assert checked_backup(receipt, envelope, key, now=NOW) == payload
        with pytest.raises(RestoreError, match="EXPIRED"):
            checked_backup(receipt, envelope, key, now=NOW + timedelta(hours=24))


def test_key_retired_during_password_prompt_cannot_be_exported(tmp_path, monkeypatch):
    import export_portable_backup as exporter

    snapshot, assets, key = fixture()
    envelope = seal(snapshot, assets, b"inert database", key, now=NOW)
    payload = open_backup(envelope, key, now=NOW)
    receipt = {"backup_id": "a" * 32, "encrypted_sha256": hashlib.sha256(envelope).hexdigest(),
               "expires_at": payload["expires_at"], "snapshot_at": snapshot["observed_at"]}
    (tmp_path / "scheduled-backup-latest.json").write_text(json.dumps(receipt))
    reads = []

    def read(_):
        reads.append(True)
        if len(reads) == 2:
            raise RuntimeError("synthetic key retired")
        return envelope, key

    monkeypatch.setattr(exporter, "PRIVATE", tmp_path)
    monkeypatch.setattr(exporter, "recover", read)
    monkeypatch.setattr(exporter.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(exporter, "datetime", SimpleNamespace(now=lambda _: NOW))
    monkeypatch.setattr(exporter.getpass, "getpass", lambda _: "synthetic-password-24bytes")
    monkeypatch.setattr(exporter, "export_portable", lambda *a, **kw: pytest.fail("exported"))
    with pytest.raises(RuntimeError, match="synthetic key retired"):
        exporter.main()
    assert len(reads) == 2
    assert list(tmp_path.iterdir()) == [tmp_path / "scheduled-backup-latest.json"]


@pytest.mark.parametrize("change", ["pending", "replaced", "oversize"])
def test_changed_or_pending_pointer_never_silently_falls_back(tmp_path, change):
    from export_portable_backup import read_latest, require_current_receipt

    path = tmp_path / "scheduled-backup-latest.json"
    receipt = {"backup_id": "synthetic-only"}
    path.write_text(json.dumps(receipt))
    assert read_latest(tmp_path) == receipt
    if change == "pending":
        path.with_suffix(".pending").write_text("interrupted replacement")
    elif change == "replaced":
        path.write_text(json.dumps({"backup_id": "replacement"}))
    else:
        path.write_bytes(b" " * 65537)
    with pytest.raises(RuntimeError, match="BACKUP_RECEIPT_"):
        require_current_receipt(receipt, tmp_path)


def test_pending_restore_stops_before_vault_cloud_or_sql(tmp_path, monkeypatch):
    import check_saved_database_recovery as restore

    (tmp_path / "scheduled-backup-latest.pending").write_text("unfinished")
    monkeypatch.setattr(restore, "PRIVATE", tmp_path)
    monkeypatch.setattr(restore, "recover", lambda *_: pytest.fail("vault reached"))
    monkeypatch.setattr(restore, "Admin", lambda: pytest.fail("cloud reached"))
    with pytest.raises(RuntimeError, match="BACKUP_RECEIPT_RECONCILE_REQUIRED"):
        restore.main()


@pytest.mark.parametrize("fault", ["pending", "replaced"])
def test_backup_pointer_changed_during_password_wait_cannot_export(tmp_path, monkeypatch, fault):
    import export_portable_backup as exporter

    snapshot, assets, key = fixture()
    envelope = seal(snapshot, assets, b"inert database", key, now=NOW)
    payload = open_backup(envelope, key, now=NOW)
    receipt = {"backup_id": "a" * 32, "encrypted_sha256": hashlib.sha256(envelope).hexdigest(),
               "expires_at": payload["expires_at"], "snapshot_at": snapshot["observed_at"]}
    path = tmp_path / "scheduled-backup-latest.json"
    path.write_text(json.dumps(receipt))

    def password(_):
        if fault == "pending":
            path.with_suffix(".pending").write_text("unfinished")
        else:
            path.write_text(json.dumps({**receipt, "backup_id": "b" * 32}))
        return "synthetic-password-24bytes"

    monkeypatch.setattr(exporter, "PRIVATE", tmp_path)
    monkeypatch.setattr(exporter, "recover", lambda _: (envelope, key))
    monkeypatch.setattr(exporter.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(exporter, "datetime", SimpleNamespace(now=lambda _: NOW))
    monkeypatch.setattr(exporter.getpass, "getpass", password)
    monkeypatch.setattr(exporter, "export_portable", lambda *a, **kw: pytest.fail("exported"))
    with pytest.raises(RuntimeError, match="BACKUP_RECEIPT_"):
        exporter.main()
    assert not list(tmp_path.glob("*.pfr"))



def test_key_retired_during_sql_rehearsal_cannot_report_recovery(tmp_path, monkeypatch, capsys):
    import check_saved_database_recovery as restore

    from orchestrator.restore_guard import plan_restore

    snapshot, assets, key = fixture()
    envelope = seal(snapshot, assets, b"inert database; subprocess is a double", key, now=NOW)
    payload = open_backup(envelope, key, now=NOW)
    receipt = {"backup_id": "a" * 32, "encrypted_sha256": hashlib.sha256(envelope).hexdigest(),
               "expires_at": payload["expires_at"], "snapshot_at": snapshot["observed_at"]}
    (tmp_path / "scheduled-backup-latest.json").write_text(json.dumps(receipt))
    reads, closed = [], []

    def recover(_):
        reads.append(True)
        if len(reads) == 2:
            raise RuntimeError("synthetic key retired during rehearsal")
        return envelope, key

    monkeypatch.setattr(restore, "PRIVATE", tmp_path)
    monkeypatch.setattr(restore, "recover", recover)
    monkeypatch.setattr(restore, "datetime", SimpleNamespace(now=lambda _: NOW))
    monkeypatch.setattr(restore, "Admin", lambda: SimpleNamespace(
        close=lambda: closed.append(True)))
    monkeypatch.setattr(restore, "authority", lambda _: snapshot)
    monkeypatch.setattr(restore, "wait_for_observation", lambda _: NOW)
    monkeypatch.setattr(restore.subprocess, "run", lambda *a, **kw: SimpleNamespace(
        returncode=0, stdout=json.dumps({"plan": plan_restore(snapshot, snapshot, now=NOW)})))
    with pytest.raises(RuntimeError, match="synthetic key retired during rehearsal"):
        restore.main()
    assert reads == [True, True] and closed == [True]
    assert capsys.readouterr().out == ""
