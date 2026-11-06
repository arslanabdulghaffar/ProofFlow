"""Actual disposable PostgreSQL snapshot/deletion/isolated restore; no cloud I/O.

Synthetic metadata only. This is a data-only rehearsal, not production recovery,
asset backup, portable encryption or permission to reopen a restored service.
"""

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from uuid import uuid4

from orchestrator.restore_guard import (
    AUTHORITY_TABLES,
    CURRENT_AUTHORITY_SQL,
    RestoreError,
    check_dump,
    plan_restore,
    quarantine_sql,
    revalidate_restore,
)
from scripts.check_budget_postgres import docker, require
from tests.integration.product_database_fixture import database


def main():
    clone = "proofflow_restore_" + uuid4().hex
    checks = []
    with database() as db:
        def cloned_sql(statement, role="postgres"):
            return docker("exec", "-i", "--user", "70:70", db.name, "psql", "-X", "-qAt",
                          "-U", role, "-d", clone, "--set", "ON_ERROR_STOP=1", stdin=statement)

        def denied(statement, target=db.sql, code="RESTORE_TARGET_NOT_QUARANTINED"):
            try:
                target(statement)
            except subprocess.CalledProcessError as error:
                require(code in error.stderr, "Unexpected restore rejection")
            else:
                raise RuntimeError("RESTORE_REJECTION_MISSING")

        retained, removed, revoked = db.workspace(), db.workspace(), db.workspace()
        for context in (retained, removed, revoked):
            db.asset(context)
        snapshot = json.loads(db.sql(CURRENT_AUTHORITY_SQL, "admin"))
        # Trusted locally generated pg_dump, never an uploaded SQL program. Keep
        # in memory only. Schema and all workspace rows are captured consistently.
        raw = docker("exec", "--user", "70:70", db.name, "pg_dump", "-U", "postgres",
                     "--no-owner", "--no-privileges", "proofflow_product").encode()
        check_dump(raw, hashlib.sha256(raw).hexdigest())
        db.sql("SELECT pf_product.request_deletion(:'w',:'s',:'c');", **removed)
        plans = json.loads(db.sql("SELECT pf_product.retention_plan();", "provisioner"))
        require(len(plans) == 1, "Unexpected retention plan count")
        pending = plans[0]
        require(pending["workspace"] == removed["w"], "Unexpected retirement fixture")
        db.sql("SELECT pf_product.complete_deletion(:'w',:'digest');", "provisioner",
               w=removed["w"], digest=pending["manifest_sha256"])
        db.sql("SELECT pf_product.request_deletion(:'w',:'s',:'c');", **revoked)
        current = json.loads(db.sql(CURRENT_AUTHORITY_SQL, "admin"))
        plan = plan_restore(snapshot, current, now=datetime.now(UTC))
        require(plan["keep"] == [retained["w"]], "Deleted/revoked workspace selected")
        checks.append("post_snapshot_completed_and_pending_deletions_excluded")
        # Connection limit zero starts with CREATE, before any restore statement.
        db.sql("CREATE DATABASE " + clone + " TEMPLATE template0 CONNECTION LIMIT 0;", "admin")
        try:
            cloned_sql(raw.decode())
            denied("SELECT 1;", lambda q: cloned_sql(q, "fixture_api"),
                   "too many connections")
            checks.append("runtime_login_denied_before_sanitization")
            sql = quarantine_sql(clone, plan["keep"])
            denied(sql, lambda q: db.sql(q, "admin"))
            checks.append("production_database_target_rejected")
            cloned_sql("CREATE TABLE pf_product.unreviewed_authority(id int);")
            denied(sql, cloned_sql, "RESTORE_SCHEMA_DRIFT")
            cloned_sql("DROP TABLE pf_product.unreviewed_authority;")
            checks.append("schema_drift_rejected_atomically")
            cloned_sql(sql)
            require(cloned_sql("SELECT id FROM pf_product.workspaces;") == retained["w"],
                    "Deleted workspace restored")
            require(cloned_sql("SELECT count(*) FROM pf_product.assets;") == "1",
                    "Deleted asset registry restored")
            require(cloned_sql("SELECT bool_and(revoked_at IS NOT NULL) "
                               "FROM pf_product.workspaces;") == "t", "Restore grants access")
            for table in AUTHORITY_TABLES:
                require(cloned_sql("SELECT count(*) FROM pf_product." + table + ";") == "0",  # noqa: S608
                        "Restored runtime authority")
            checks.append("only_current_data_retained_all_runtime_authority_removed")
            revalidate_restore(snapshot, plan,
                               json.loads(db.sql(CURRENT_AUTHORITY_SQL, "admin")),
                               now=datetime.now(UTC))
            db.sql("SELECT pf_product.request_deletion(:'w',:'s',:'c');", **retained)
            try:
                revalidate_restore(snapshot, plan,
                                   json.loads(db.sql(CURRENT_AUTHORITY_SQL, "admin")),
                                   now=datetime.now(UTC))
            except RestoreError as error:
                require(str(error) == "RESTORE_AUTHORITY_CHANGED", "Wrong restore error")
            else:
                raise RuntimeError("CONCURRENT_DELETION_ACCEPTED")
            checks.append("second_live_read_detects_deletion_during_restore")
        finally:
            db.sql("DROP DATABASE " + clone + ";", "admin")
        require(db.sql("SELECT count(*) FROM pg_database WHERE datname=:'clone';",
                       "admin", clone=clone) == "0", "Clone cleanup failed")
    print(json.dumps({"scope": "local_disposable_postgres_synthetic_metadata_only",
                      "checks": checks, "cleanup": "confirmed", "cloud_calls": 0,
                      "production_recovery": "NOT_RUN"}))


if __name__ == "__main__":
    main()
