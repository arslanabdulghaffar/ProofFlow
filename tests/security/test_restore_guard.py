"""Untrusted metadata rejection and deletion-aware, data-only recovery policy."""

import copy
import hashlib
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from orchestrator.restore_guard import (
    RestoreError,
    check_dump,
    plan_restore,
    quarantine_sql,
    revalidate_restore,
)

NOW = datetime(2026, 11, 7, tzinfo=UTC)


def authority():
    return {"observed_at": NOW.isoformat(), "workspaces": [
        {"id": str(uuid4()), "created_at": (NOW - timedelta(hours=1)).isoformat(),
         "expires_at": (NOW + timedelta(hours=1)).isoformat()}]}


def test_deleted_or_missing_workspace_never_restored():
    old = authority()
    live = {"observed_at": NOW.isoformat(), "workspaces": []}
    result = plan_restore(old, live, now=NOW)
    assert result["keep"] == []
    assert result["exclude"] == [old["workspaces"][0]["id"]]


def test_live_identity_cannot_be_replaced_or_expiry_extended():
    old = authority()
    live = copy.deepcopy(old)
    live["workspaces"][0]["expires_at"] = (NOW + timedelta(hours=2)).isoformat()
    assert plan_restore(old, live, now=NOW)["keep"] == []


@pytest.mark.parametrize("age", [-1, 61])
def test_requires_fresh_nonfuture_authority(age):
    old = authority()
    old["observed_at"] = (NOW - timedelta(hours=2)).isoformat()
    live = authority()
    live["observed_at"] = (NOW - timedelta(seconds=age)).isoformat()
    with pytest.raises(RestoreError, match="CURRENT_AUTHORITY_REQUIRED"):
        plan_restore(old, live, now=NOW)


@pytest.mark.parametrize("age", [-1, 86401])
def test_rejects_expired_or_future_backup(age):
    old = authority()
    old["observed_at"] = (NOW - timedelta(seconds=age)).isoformat()
    with pytest.raises(RestoreError, match="BACKUP_EXPIRED"):
        plan_restore(old, authority(), now=NOW)


def test_second_authority_read_detects_deletion_during_restore():
    old = authority()
    plan = plan_restore(old, old, now=NOW)
    assert revalidate_restore(old, plan, old, now=NOW)["keep"] == plan["keep"]
    with pytest.raises(RestoreError, match="AUTHORITY_CHANGED"):
        revalidate_restore(old, plan, {**old, "workspaces": []}, now=NOW)


@pytest.mark.parametrize("mutation", ["duplicate", "extra", "naive", "badid", "too_many"])
def test_malformed_inventory_is_not_authority(mutation):
    old = authority()
    if mutation == "duplicate":
        old["workspaces"] *= 2
    elif mutation == "extra":
        old["sessions"] = []
    elif mutation == "naive":
        old["observed_at"] = "2026-11-07T00:00:00"
    elif mutation == "badid":
        old["workspaces"][0]["id"] = "'); DROP DATABASE proofflow_product; --"
    else:
        old["workspaces"] *= 9
    with pytest.raises(RestoreError):
        plan_restore(old, authority(), now=NOW)


def test_bytes_binding_and_sql_target_are_fail_closed():
    raw = b"inert synthetic dump"
    check_dump(raw, hashlib.sha256(raw).hexdigest())
    with pytest.raises(RestoreError, match="DUMP_BINDING"):
        check_dump(raw + b"changed", hashlib.sha256(raw).hexdigest())
    with pytest.raises(RestoreError, match="TARGET_FORBIDDEN"):
        quarantine_sql("proofflow_product", [])
    with pytest.raises(RestoreError, match="ID_INVALID"):
        quarantine_sql("proofflow_restore_" + uuid4().hex, ["';--"])


def test_snapshot_created_after_workspace_or_expired_workspace_is_excluded():
    old = authority()
    old["workspaces"][0]["created_at"] = (NOW + timedelta(seconds=1)).isoformat()
    assert plan_restore(old, old, now=NOW)["keep"] == []
    old = authority()
    old["workspaces"][0]["expires_at"] = NOW.isoformat()
    assert plan_restore(old, old, now=NOW)["keep"] == []
