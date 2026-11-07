"""Actual disposable PostgreSQL snapshot/deletion/isolated restore; no cloud I/O.

Synthetic database AND asset bytes, encrypted on disk. This remains data-only
recovery, not permission to reopen a service or a production disaster-recovery claim.
"""

import base64
import hashlib
import json
import os
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID, uuid4

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from api.app.workspace_assets import WorkspaceAssets
from orchestrator.asset_backup import open_backup, seal
from orchestrator.asset_recovery import materialize
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
from scripts.consistent_product_backup import CaptureError
from scripts.consistent_product_backup import snapshot as consistent_snapshot
from tests.integration.product_database_fixture import database


def main():
    started = time.monotonic()
    clone = "proofflow_restore_" + uuid4().hex
    checks = []
    with (database() as db, database() as recovery_db,
          TemporaryDirectory(prefix="proofflow-encrypted-restore-") as temporary):
        from orchestrator.retention import retire

        # Real cached image's watchdog binary, shortened only for this fixed trusted
        # pg_sleep fault. Production command remains hardcoded to 55 seconds.
        timer = time.monotonic()
        try:
            docker("exec", "--user", "70:70", db.name, "timeout", "-s", "KILL", "1",
                   "psql", "-X", "-qAt", "-U", "postgres", "-d", "proofflow_product",
                   "-c", "SELECT pg_sleep(10);")
        except subprocess.CalledProcessError as error:
            require(error.returncode == 137 and time.monotonic()-timer < 5,
                    "Container watchdog did not kill bounded database client")
        else:
            raise RuntimeError("CONTAINER_DEADLINE_MISSING")
        checks.append("container_owned_client_watchdog_kills_independently")
        source, recovered, jobs = (Path(temporary) / n for n in ("source", "recovered", "jobs"))
        for directory in (source, recovered, jobs):
            directory.mkdir(mode=0o700)

        def cloned_sql(statement, role="postgres"):
            return docker(
                "exec",
                "-i",
                "--user",
                "70:70",
                recovery_db.name,
                "psql",
                "-X",
                "-qAt",
                "-U",
                role,
                "-d",
                clone,
                "--set",
                "ON_ERROR_STOP=1",
                stdin=statement,
            )

        def denied(statement, target=db.sql, code="RESTORE_TARGET_NOT_QUARANTINED"):
            try:
                target(statement)
            except subprocess.CalledProcessError as error:
                require(code in error.stderr, "Unexpected restore rejection")
            else:
                raise RuntimeError("RESTORE_REJECTION_MISSING")

        retained, removed, revoked = db.workspace(), db.workspace(), db.workspace()
        assets = []
        fd = os.open(source, os.O_RDONLY | os.O_DIRECTORY)
        try:
            store = WorkspaceAssets(fd)
            for context in (retained, removed, revoked):
                inert = ("INERT_SYNTHETIC_ASSET_" + context["w"]).encode()
                digest = store.put(UUID(context["w"]), inert)
                params = {**context, "a": str(uuid4()), "digest": digest, "size": len(inert)}
                db.sql(
                    "SELECT pf_product.reserve_upload(:'w',:'s',:'c',:'a',"
                    "'pipeline',:'digest',:'size');",
                    **params,
                )
                db.sql(
                    "SELECT pf_product.complete_upload(:'w',:'s',:'c',:'a',"
                    "'pipeline',:'digest',:'size');",
                    **params,
                )
                created = db.sql(
                    "SELECT created_at FROM pf_product.assets WHERE workspace_id=:'w' AND id=:'a';",
                    "admin",
                    **params,
                )
                assets.append(
                    {
                        "workspace": context["w"],
                        "sha256": digest,
                        "created_at": created,
                        "bytes": store.read(UUID(context["w"]), digest),
                    }
                )
        finally:
            os.close(fd)
        with consistent_snapshot(db.name) as capture:
            snapshot = capture.inventory
            require({a["sha256"] for a in capture.assets} == {a["sha256"] for a in assets},
                    "Snapshot registry and bytes disagree")
            # Commit concurrent metadata writes AFTER export, BEFORE pg_dump.
            # A separate uncoordinated dump would include these later rows.
            late = db.workspace()
            late_asset = db.asset(retained)
            raw = capture.dump()
        require(db.sql("SELECT count(*) FROM pg_stat_activity WHERE application_name='psql' "
                       "AND state='idle in transaction';", "admin") == "0",
                "Exporter transaction leaked")
        checks.append("exported_snapshot_registry_and_dump_exclude_concurrent_commits")
        try:
            capture.dump()  # Exporter ended: reuse must fail, never silently take a new snapshot.
        except CaptureError:
            checks.append("ended_exporter_snapshot_cannot_be_reused")
        else:
            raise RuntimeError("EXPIRED_SNAPSHOT_REUSED")
        try:
            with consistent_snapshot(db.name):
                raise RuntimeError("INJECTED_CAPTURE_INTERRUPTION")
        except RuntimeError as error:
            require(str(error) == "INJECTED_CAPTURE_INTERRUPTION", "Wrong capture failure")
        require(db.sql("SELECT count(*) FROM pg_stat_activity WHERE application_name='psql' "
                       "AND state='idle in transaction';", "admin") == "0",
                "Interrupted exporter transaction leaked")
        checks.append("interrupted_capture_rolls_back_exporter")
        check_dump(raw, hashlib.sha256(raw).hexdigest())
        key = AESGCM.generate_key(bit_length=256)  # Per-snapshot, memory-only fixture key.
        encrypted = seal(snapshot, assets, raw, key, now=datetime.now(UTC))
        backup = Path(temporary) / "snapshot.pfenc"
        backup.write_bytes(encrypted)
        backup.chmod(0o600)
        require(all(a["bytes"] not in backup.read_bytes() for a in assets), "Plaintext backup")
        payload = open_backup(backup.read_bytes(), key, now=datetime.now(UTC))
        require(base64.b64decode(payload["database"], validate=True) == raw, "DB recovery mismatch")
        checks.append("encrypted_database_and_asset_roundtrip")
        db.sql("SELECT pf_product.request_deletion(:'w',:'s',:'c');", **removed)
        plans = json.loads(db.sql("SELECT pf_product.retention_plan();", "provisioner"))
        require(len(plans) == 1, "Unexpected retention plan count")
        pending = plans[0]
        require(pending["workspace"] == removed["w"], "Unexpected retirement fixture")
        retire(pending, assets=source, jobs=jobs)
        db.sql(
            "SELECT pf_product.complete_deletion(:'w',:'digest');",
            "provisioner",
            w=removed["w"],
            digest=pending["manifest_sha256"],
        )
        db.sql("SELECT pf_product.request_deletion(:'w',:'s',:'c');", **revoked)
        current = json.loads(db.sql(CURRENT_AUTHORITY_SQL, "admin"))
        try:
            plan_restore(snapshot, None, now=datetime.now(UTC))
        except RestoreError:
            checks.append("missing_current_deletion_authority_denies_restore")
        else:
            raise RuntimeError("MISSING_AUTHORITY_ALLOWED")
        plan = plan_restore(snapshot, current, now=datetime.now(UTC))
        require(plan["keep"] == [retained["w"]], "Deleted/revoked workspace selected")
        checks.append("post_snapshot_completed_and_pending_deletions_excluded")
        # Connection limit zero starts with CREATE, before any restore statement.
        recovery_db.sql("CREATE DATABASE " + clone + " TEMPLATE template0 CONNECTION LIMIT 0;",
                        "admin")
        try:
            cloned_sql(raw.decode())
            require(cloned_sql("SELECT count(*) FROM pf_product.workspaces WHERE id='"  # noqa: S608 - generated UUID
                               + str(UUID(late["w"])) + "';") == "0", "Later workspace in dump")
            require(cloned_sql("SELECT count(*) FROM pf_product.assets WHERE id='"  # noqa: S608 - generated UUID
                               + str(UUID(late_asset["a"])) + "';") == "0", "Later asset in dump")
            checks.append("restored_into_separate_fresh_isolated_postgres_instance")
            denied("SELECT 1;", lambda q: cloned_sql(q, "fixture_api"), "too many connections")
            checks.append("runtime_login_denied_before_sanitization")
            sql = quarantine_sql(clone, plan["keep"])
            denied(sql, lambda q: db.sql(q, "admin"))
            checks.append("production_database_target_rejected")
            cloned_sql("CREATE TABLE pf_product.unreviewed_authority(id int);")
            denied(sql, cloned_sql, "RESTORE_SCHEMA_DRIFT")
            cloned_sql("DROP TABLE pf_product.unreviewed_authority;")
            checks.append("schema_drift_rejected_atomically")
            cloned_sql(sql)
            fd = os.open(recovered, os.O_RDONLY | os.O_DIRECTORY)
            try:
                restored = materialize(fd, payload, current, now=datetime.now(UTC))
            finally:
                os.close(fd)
            require(len(restored["assets"]) == 1, "Deleted asset bytes restored")
            require(
                sorted(p.name for p in recovered.iterdir()) == [UUID(retained["w"]).hex],
                "Deleted workspace bytes restored",
            )
            require(not (source / UUID(removed["w"]).hex).exists(), "Source deletion failed")
            require(
                cloned_sql("SELECT id FROM pf_product.workspaces;") == retained["w"],
                "Deleted workspace restored",
            )
            require(
                cloned_sql("SELECT count(*) FROM pf_product.assets;") == "1",
                "Deleted asset registry restored",
            )
            require(
                cloned_sql("SELECT bool_and(revoked_at IS NOT NULL) FROM pf_product.workspaces;")
                == "t",
                "Restore grants access",
            )
            for table in AUTHORITY_TABLES:
                require(
                    cloned_sql("SELECT count(*) FROM pf_product." + table + ";") == "0",  # noqa: S608
                    "Restored runtime authority",
                )
            checks.append("only_current_data_retained_all_runtime_authority_removed")
            revalidate_restore(
                snapshot,
                plan,
                json.loads(db.sql(CURRENT_AUTHORITY_SQL, "admin")),
                now=datetime.now(UTC),
            )
            db.sql("SELECT pf_product.request_deletion(:'w',:'s',:'c');", **retained)
            try:
                revalidate_restore(
                    snapshot,
                    plan,
                    json.loads(db.sql(CURRENT_AUTHORITY_SQL, "admin")),
                    now=datetime.now(UTC),
                )
            except RestoreError as error:
                require(str(error) == "RESTORE_AUTHORITY_CHANGED", "Wrong restore error")
            else:
                raise RuntimeError("CONCURRENT_DELETION_ACCEPTED")
            checks.append("second_live_read_detects_deletion_during_restore")
        finally:
            recovery_db.sql("DROP DATABASE " + clone + ";", "admin")
        require(
            recovery_db.sql("SELECT count(*) FROM pg_database WHERE datname=:'clone';",
                            "admin", clone=clone)
            == "0",
            "Clone cleanup failed",
        )
    require(not Path(temporary).exists(), "Local encrypted fixture cleanup failed")
    print(
        json.dumps(
            {
                "scope": "local_disposable_encrypted_database_and_synthetic_assets",
                "checks": checks,
                "cleanup": "confirmed",
                "cloud_calls": 0,
                "production_recovery": "NOT_RUN",
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "dump_bytes": len(raw),
            }
        )
    )


if __name__ == "__main__":
    main()
