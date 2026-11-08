"""Real authenticated encryption on inert synthetic bytes, no candidate execution."""

import hashlib
import os
import sys
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from orchestrator.asset_backup import open_backup, seal, select_recovery
from orchestrator.restore_guard import RestoreError

NOW = datetime(2026, 11, 7, tzinfo=UTC)


def fixture():
    workspace = str(uuid4())
    created = (NOW - timedelta(hours=1)).isoformat()
    snapshot = {"observed_at": NOW.isoformat(), "workspaces": [
        {"id": workspace, "created_at": created,
         "expires_at": (NOW + timedelta(hours=1)).isoformat()}]}
    raw = b"not executable; synthetic asset for encrypted recovery"
    asset = {"workspace": workspace, "created_at": created,
             "sha256": hashlib.sha256(raw).hexdigest(), "bytes": raw}
    return snapshot, [asset], AESGCM.generate_key(bit_length=256)


def test_authenticated_roundtrip_and_no_plaintext_on_disk(tmp_path):
    snapshot, assets, key = fixture()
    encrypted = seal(snapshot, assets, b"inert database snapshot", key, now=NOW)
    path = tmp_path / "backup.pfenc"
    path.write_bytes(encrypted)
    assert assets[0]["bytes"] not in path.read_bytes()
    assert snapshot["workspaces"][0]["id"].encode() not in encrypted
    payload = open_backup(path.read_bytes(), key, now=NOW)
    plan, recovered = select_recovery(payload, snapshot, now=NOW)
    assert plan["keep"] == [assets[0]["workspace"]]
    assert recovered == [(assets[0]["workspace"], assets[0]["sha256"], assets[0]["bytes"])]


@pytest.mark.parametrize("change", ["key", "nonce", "ciphertext", "tag", "header", "truncated"])
def test_tampering_never_returns_assets(change):
    snapshot, assets, key = fixture()
    raw = bytearray(seal(snapshot, assets, b"inert", key, now=NOW))
    if change == "key":
        key = AESGCM.generate_key(bit_length=256)
    elif change == "truncated":
        raw = raw[:-10]
    else:
        index = {"nonce": 26, "ciphertext": 50, "tag": -1, "header": 0}[change]
        raw[index] ^= 1
    with pytest.raises(RestoreError):
        open_backup(bytes(raw), key, now=NOW)


def test_expired_envelope_and_deleted_workspace_are_rejected():
    snapshot, assets, key = fixture()
    encrypted = seal(snapshot, assets, b"inert", key, now=NOW)
    with pytest.raises(RestoreError, match="EXPIRED"):
        open_backup(encrypted, key, now=NOW + timedelta(hours=24))
    payload = open_backup(encrypted, key, now=NOW)
    plan, recovered = select_recovery(payload, {**snapshot, "workspaces": []}, now=NOW)
    assert recovered == [] and plan["keep"] == []


@pytest.mark.parametrize("change", ["hash", "duplicate", "scope", "future", "old", "size"])
def test_invalid_registry_bytes_or_times_fail_before_encryption(change):
    snapshot, assets, key = fixture()
    if change == "hash":
        assets[0]["sha256"] = "a" * 64
    elif change == "duplicate":
        assets *= 2
    elif change == "scope":
        assets[0]["workspace"] = str(uuid4())
    elif change == "size":
        assets[0]["bytes"] = b""
    else:
        hours = 1 if change == "future" else -49
        assets[0]["created_at"] = (NOW + timedelta(hours=hours)).isoformat()
    with pytest.raises(RestoreError):
        seal(snapshot, assets, b"inert", key, now=NOW)


@pytest.mark.skipif(sys.platform != "linux", reason="Linux descriptor-based private asset store")
def test_materialization_private_modes_bytes_and_nonempty_target(tmp_path):
    from orchestrator.asset_recovery import materialize

    snapshot, assets, key = fixture()
    encrypted = seal(snapshot, assets, b"inert", key, now=NOW)
    payload = open_backup(encrypted, key, now=NOW)
    tmp_path.chmod(0o700)
    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        result = materialize(fd, payload, snapshot, now=NOW)
        assert result["mode"] == "INERT_DATA_ONLY_NO_PROMOTION"
        path = tmp_path / UUID_HEX(snapshot) / assets[0]["sha256"]
        assert path.read_bytes() == assets[0]["bytes"]
        assert path.stat().st_mode & 0o777 == 0o400
        with pytest.raises(RestoreError, match="NOT_EMPTY"):
            materialize(fd, payload, snapshot, now=NOW)
    finally:
        os.close(fd)


def UUID_HEX(snapshot):
    return snapshot["workspaces"][0]["id"].replace("-", "")


@pytest.mark.skipif(sys.platform != "linux", reason="Linux descriptor-based private asset store")
@pytest.mark.parametrize("expired", ["authority", "workspace", "backup", "clock"])
def test_materialization_cannot_claim_success_after_expiry(tmp_path, monkeypatch, expired):
    from orchestrator import asset_recovery

    snapshot, assets, key = fixture()
    if expired == "workspace":
        snapshot["workspaces"][0]["expires_at"] = (NOW + timedelta(seconds=1)).isoformat()
    payload = open_backup(seal(snapshot, assets, b"inert", key, now=NOW), key, now=NOW)
    if expired == "backup":
        payload["expires_at"] = (NOW + timedelta(seconds=1)).isoformat()
    elapsed = {"authority": 61, "workspace": 2, "backup": 2, "clock": -1}[expired]
    ticks = iter([100.0, 100.0 + elapsed])
    monkeypatch.setattr(asset_recovery.time, "monotonic", lambda: next(ticks))
    tmp_path.chmod(0o700)
    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        with pytest.raises(RestoreError):
            asset_recovery.materialize(fd, payload, snapshot, now=NOW)
        # The isolated caller must discard staging even when validation fails.
        recovered = tmp_path / UUID_HEX(snapshot) / assets[0]["sha256"]
        assert recovered.read_bytes() == assets[0]["bytes"]
    finally:
        os.close(fd)
