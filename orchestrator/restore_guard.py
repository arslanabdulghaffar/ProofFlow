"""Trusted-admin, data-only restore rehearsal. Never a production promotion path.

Inventory must come from an authenticated CURRENT source, not the backup. The
caller holds recovery access closed throughout and reads authority again before
accepting the result. No returned plan grants execution, sessions or approvals.
"""

import hashlib
import json
import re
from datetime import UTC, datetime
from uuid import UUID

MAX_BACKUP_AGE = 24 * 60 * 60
MAX_AUTHORITY_AGE = 60
MAX_DUMP_BYTES = 16 * 1024 * 1024

# Fail closed on schema drift. New authority tables require an explicit review.
AUTHORITY_TABLES = (
    "sessions", "uploads", "execution_policy", "contract_approvals", "jobs", "job_events",
    "repairs", "repair_allocation", "repair_calls", "repair_executions", "repair_events",
    "repair_candidates", "pipelines", "versions", "approval_intents", "batches", "version_events",
    "github_configuration", "pr_intents", "pr_writes", "batch_connections", "batch_deliveries",
    "evaluation_allocations", "retention_clock", "judge_admission",
)
TABLES = frozenset((*AUTHORITY_TABLES, "workspaces", "assets", "deletions"))

# One statement / MVCC view. Deleted IDs are never revived even if the old
# snapshot predates the deletion. Absence from the current allowlist is denial.
CURRENT_AUTHORITY_SQL = """
SELECT json_build_object('observed_at',clock_timestamp(),'workspaces',coalesce(
    (SELECT json_agg(json_build_object('id',w.id,'created_at',w.created_at,
                                     'expires_at',w.expires_at) ORDER BY w.id)
     FROM pf_product.workspaces w WHERE w.revoked_at IS NULL
       AND w.expires_at>clock_timestamp()
       AND NOT EXISTS(SELECT 1 FROM pf_product.deletions d WHERE d.workspace_id=w.id)),
    '[]'::json));
"""


class RestoreError(ValueError):
    pass


def timestamp(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value)
        if result.tzinfo is None:
            raise ValueError
        return result.astimezone(UTC)
    except (TypeError, ValueError):
        raise RestoreError("RESTORE_TIMESTAMP_INVALID") from None


def inventory(value: dict) -> dict:
    if type(value) is not dict or set(value) != {"observed_at", "workspaces"}:
        raise RestoreError("RESTORE_AUTHORITY_INVALID")
    timestamp(value["observed_at"])
    rows = value["workspaces"]
    if type(rows) is not list or len(rows) > 8:
        raise RestoreError("RESTORE_INVENTORY_LIMIT")
    result = {}
    for row in rows:
        if type(row) is not dict or set(row) != {"id", "created_at", "expires_at"}:
            raise RestoreError("RESTORE_INVENTORY_INVALID")
        try:
            if str(UUID(row["id"])) != row["id"] or row["id"] in result:
                raise ValueError
        except (TypeError, ValueError, AttributeError):
            raise RestoreError("RESTORE_ID_INVALID") from None
        created, expires = timestamp(row["created_at"]), timestamp(row["expires_at"])
        if not 0 < (expires - created).total_seconds() <= MAX_BACKUP_AGE:
            raise RestoreError("RESTORE_WORKSPACE_LIFETIME_INVALID")
        result[row["id"]] = (created, expires)
    return result


def plan_restore(snapshot: dict, current: dict, *, now: datetime) -> dict:
    """Snapshot metadata and dump digest must be authenticated by the caller."""
    if now.tzinfo is None:
        raise RestoreError("RESTORE_CLOCK_INVALID")
    old, live = inventory(snapshot), inventory(current)
    saved, observed = timestamp(snapshot["observed_at"]), timestamp(current["observed_at"])
    if not 0 <= (now - saved).total_seconds() <= MAX_BACKUP_AGE:
        raise RestoreError("RESTORE_BACKUP_EXPIRED")
    if not 0 <= (now - observed).total_seconds() <= MAX_AUTHORITY_AGE or observed < saved:
        raise RestoreError("RESTORE_CURRENT_AUTHORITY_REQUIRED")
    keep = sorted(key for key, lifetime in old.items()
                  if live.get(key) == lifetime and lifetime[0] <= saved
                  and lifetime[1] > now)
    binding = hashlib.sha256(json.dumps(current, sort_keys=True).encode()).hexdigest()
    return {"mode": "QUARANTINED_DATA_ONLY", "keep": keep,
            "exclude": sorted(set(old) - set(keep)), "authority_sha256": binding,
            "authority_observed_at": current["observed_at"]}


def check_dump(raw: bytes, expected_sha256: str) -> None:
    if (type(raw) is not bytes or not 0 < len(raw) <= MAX_DUMP_BYTES
            or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256)
            or hashlib.sha256(raw).hexdigest() != expected_sha256):
        raise RestoreError("RESTORE_DUMP_BINDING_INVALID")


def revalidate_restore(snapshot: dict, plan: dict, current: dict, *, now: datetime) -> dict:
    fresh = plan_restore(snapshot, current, now=now)
    if fresh["keep"] != plan["keep"] or fresh["exclude"] != plan["exclude"]:
        raise RestoreError("RESTORE_AUTHORITY_CHANGED")
    return fresh


def quarantine_sql(database: str, keep: list[str]) -> str:
    """SQL only for an admin-owned connection-limit-zero disposable clone.

    Retains eligible workspace/asset metadata and deletion markers. Removes ALL
    runtime authority, including sessions, approvals, queues, PR outbox and budget
    allocations. This clone cannot be promoted or used to resume production.
    """
    if not re.fullmatch(r"proofflow_restore_[0-9a-f]{32}", database):
        raise RestoreError("RESTORE_TARGET_FORBIDDEN")
    if type(keep) is not list or len(keep) > 8 or len(set(keep)) != len(keep):
        raise RestoreError("RESTORE_INVENTORY_INVALID")
    for key in keep:
        if type(key) is not str or not re.fullmatch(
                r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", key):
            raise RestoreError("RESTORE_ID_INVALID")
    ids = ",".join("'" + key + "'::uuid" for key in keep)
    allowed = "ARRAY[" + ids + "]::uuid[]"
    expected = ",".join("'" + name + "'" for name in sorted(TABLES))
    tables = ",".join("pf_product." + name for name in AUTHORITY_TABLES)
    # Only fixed identifiers and strictly validated UUIDs/clone name are interpolated.
    return f"""  -- fixed SQL, validated identifiers only
BEGIN;
SET LOCAL statement_timeout='10s'; SET LOCAL lock_timeout='3s';
DO $$ BEGIN
 IF current_database()<>'{database}' OR NOT EXISTS(
   SELECT 1 FROM pg_database d JOIN pg_roles r ON r.oid=d.datdba
   WHERE d.datname=current_database() AND d.datconnlimit=0 AND r.rolsuper)
   OR NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=current_user AND rolsuper)
 THEN RAISE EXCEPTION 'RESTORE_TARGET_NOT_QUARANTINED'; END IF;
 IF (SELECT array_agg(tablename::text ORDER BY tablename) FROM pg_tables
     WHERE schemaname='pf_product') IS DISTINCT FROM ARRAY[{expected}]
 THEN RAISE EXCEPTION 'RESTORE_SCHEMA_DRIFT'; END IF;
END $$;
TRUNCATE {tables};
DELETE FROM pf_product.assets WHERE NOT(workspace_id=ANY({allowed}));
DELETE FROM pf_product.workspaces WHERE NOT(id=ANY({allowed}));
UPDATE pf_product.workspaces SET revoked_at=coalesce(revoked_at,clock_timestamp());
COMMIT;
"""  # noqa: S608 - fixed table list, regex-validated target and UUIDs only
