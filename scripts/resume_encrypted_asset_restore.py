"""Reconcile the saved encrypted snapshot only; never upload, enqueue, or take another backup."""

import base64
import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from asset_backup_vault import recover, retire
from asset_recovery_container import run as run_asset_recovery
from check_encrypted_asset_recovery_live import clone_sql, current_authority
from product_live_session import LiveSession, require
from vultr_phase1 import PRIVATE

from orchestrator.asset_backup import open_backup
from orchestrator.restore_guard import (
    AUTHORITY_TABLES,
    plan_restore,
    quarantine_sql,
    revalidate_restore,
)


def main():
    path = PRIVATE / "evidence/phase5-encrypted-asset-recovery.json"
    record = json.loads(path.read_bytes())
    require(
        not record["completed"]
        and record.get("resume_backup_only")
        and "backup_id" in record
        and "asset_recovery" not in record,
        "RESTORE_RESUME_SCOPE_MISMATCH",
    )
    primary, deleted = (str(UUID(w)) for w in record["fixture_workspaces"])
    # Immutable saved failure before doing any restore work.
    with path.with_name("phase5-encrypted-asset-recovery-after-backup.json").open("xb") as output:
        output.write(path.read_bytes())
    record["preserved_restore_failure"] = "DATABASE_NOT_ALLOWED before import; clone dropped"
    record["resume_restore_only"] = True
    envelope, key = recover(record["backup_id"])
    require(
        hashlib.sha256(envelope).hexdigest() == record["encrypted_sha256"],
        "SAVED_ENCRYPTED_BACKUP_CHANGED",
    )
    payload = open_backup(envelope, key, now=datetime.now(UTC))
    snapshot = payload["snapshot"]
    clone, created = "proofflow_restore_" + uuid4().hex, False

    def persist():
        path.write_bytes(json.dumps(record, sort_keys=True, indent=2).encode())

    with LiveSession() as live:
        require(
            live.sql("SELECT id::text FROM pf_product.workspaces;").decode() == primary,
            "RESTORE_RESUME_LIVE_SCOPE_CHANGED",
        )
        require(
            live.sql(
                "SELECT count(*) FROM pf_product.deletions WHERE workspace_id='"  # noqa: S608
                + deleted
                + "' AND completed_at IS NOT NULL;"
            )
            == b"1",
            "RESTORE_RESUME_DELETION_INCOMPLETE",
        )
        current = current_authority(live)
        plan = plan_restore(snapshot, current, now=datetime.now(UTC))
        require(
            plan["keep"] == [primary] and plan["exclude"] == [deleted],
            "RESTORE_RESUME_SELECTION_CHANGED",
        )
        persist()
        try:
            live.sql("CREATE DATABASE " + clone + " TEMPLATE template0 CONNECTION LIMIT 0;")
            created = True
            clone_sql(live, base64.b64decode(payload["database"], validate=True).decode(), clone)
            clone_sql(live, quarantine_sql(clone, plan["keep"]), clone)
            require(
                clone_sql(live, "SELECT count(*) FROM pf_product.assets;", clone) == b"4",
                "RESTORED_ASSET_REGISTRY_CHANGED",
            )
            for table in AUTHORITY_TABLES:
                require(
                    clone_sql(live, "SELECT count(*) FROM pf_product." + table + ";", clone)  # noqa: S608
                    == b"0",
                    "RESTORED_AUTHORITY_PRESENT",
                )
            current = current_authority(live)
            receipt = run_asset_recovery(json.dumps({
                "envelope": base64.b64encode(envelope).decode(),
                "key": base64.b64encode(key).decode(),
                "current": current,
            }).encode())
            require(
                len(receipt["assets"]) == 4
                and all(a["workspace"] == primary for a in receipt["assets"]),
                "OFFVM_ASSET_SCOPE_CHANGED",
            )
            revalidate_restore(snapshot, plan, current_authority(live), now=datetime.now(UTC))
            record["asset_recovery"] = receipt
            live.sql("DROP DATABASE " + clone + ";")
            created = False
            client = live.login(primary)
            response = client.post(
                "/v1/workspace/delete", json={"workspace_id": primary, "confirm": True}
            )
            require(response.status_code == 200, "FIXTURE_RETIREMENT_FAILED")
            live.host("systemctl start proofflow-product-retention.service")
            require(
                live.sql("SELECT count(*) FROM pf_product.workspaces;") == b"0", "FIXTURE_REMAINS"
            )
            retire(record["backup_id"])
            record.update(
                completed=True,
                backup_key_and_ciphertext_retired=True,
                clone_removed=True,
                workspaces_retired=True,
                finished_at=datetime.now(UTC).isoformat(),
                final_credit=live.credit,
            )
            persist()
            print(
                json.dumps(
                    {
                        "encrypted_offvm_recovery": "passed",
                        "assets_recovered": 4,
                        "deleted_workspace_excluded": True,
                        "runtime_authority_restored": False,
                        "job_replayed": False,
                        "new_snapshot": False,
                        "cleanup": "confirmed",
                    }
                )
            )
        finally:
            if created:
                live.sql("DROP DATABASE " + clone + ";")
            persist()


if __name__ == "__main__":
    main()
