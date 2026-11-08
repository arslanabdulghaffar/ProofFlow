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
