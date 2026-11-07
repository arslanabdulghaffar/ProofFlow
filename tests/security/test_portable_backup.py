"""Real portable crypto with disclosed synthetic bytes; no cloud calls."""

from datetime import timedelta

import pytest

from orchestrator.asset_backup import seal
from orchestrator.portable_backup import export_portable, recover_portable
from orchestrator.restore_guard import RestoreError
from tests.security.test_asset_backup import NOW, fixture

PASSWORD = b"synthetic-test-only-long-password"


def package():
    snapshot, assets, key = fixture()
    envelope = seal(snapshot, assets, b"inert database", key, now=NOW)
    return export_portable(envelope, key, PASSWORD, now=NOW), snapshot, assets


def test_password_portable_roundtrip_and_current_deletion_exclusion():
    raw, current, assets = package()
    assert assets[0]["bytes"] not in raw
    payload, plan, restored = recover_portable(raw, PASSWORD, current, now=NOW)
    assert plan["keep"] == [assets[0]["workspace"]]
    assert restored[0][2] == assets[0]["bytes"]
    _, plan, restored = recover_portable(raw, PASSWORD, {**current,"workspaces":[]}, now=NOW)
    assert not restored and not plan["keep"]


@pytest.mark.parametrize("fault", ["password", "header", "wrapped_key", "envelope",
                                  "missing_authority", "stale_authority", "expired"])
def test_portable_failures_return_no_data(fault):
    raw, current, _ = package()
    password, now = PASSWORD, NOW
    if fault == "password":
        password = b"different-synthetic-test-password"
    elif fault in ("header", "wrapped_key", "envelope"):
        data = bytearray(raw)
        data[{"header":0,"wrapped_key":60,"envelope":-1}[fault]] ^= 1
        raw = bytes(data)
    elif fault == "missing_authority":
        current = None
    elif fault == "stale_authority":
        now += timedelta(seconds=61)
    else:
        now += timedelta(hours=24)
        current = {"observed_at":now.isoformat(),"workspaces":[]}
    with pytest.raises(RestoreError):
        recover_portable(raw, password, current, now=now)
