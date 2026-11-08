"""Authenticate latest scheduled backup, rehearse it off-VM, recheck live deletions.

Only GET/SELECT against the existing deployment. No cloud changes, backup replacement,
password prompt, product session, job, SQL import on production, or candidate execution.
"""

import json
import subprocess
import sys
from datetime import UTC, datetime

from asset_backup_vault import recover
from export_portable_backup import checked_backup
from recovery_clock import wait_for_observation
from vultr_phase1 import PRIVATE, ROOT, Admin

sys.path.insert(0, str(ROOT))
from orchestrator.restore_guard import CURRENT_AUTHORITY_SQL, revalidate_restore  # noqa: E402


def require(value, code):
    if not value:
        raise RuntimeError(code)


def authority(admin):
    identity = admin.host("control", "cat /etc/machine-id")
    require(identity.returncode == 0
            and identity.stdout.decode().strip() == admin.state["control_machine_id"],
            "SAVED_RESTORE_CONTROL_IDENTITY_CHANGED")
    reply = admin.host("control", "docker exec -i --user=70:70 proofflow-budget psql -X -qAt "
                       "-h /run/proofflow-budget -U postgres -d proofflow_product "
                       "--set ON_ERROR_STOP=1", stdin=CURRENT_AUTHORITY_SQL.encode())
    require(reply.returncode == 0, "SAVED_RESTORE_AUTHORITY_UNAVAILABLE")
    current = json.loads(reply.stdout)
    wait_for_observation(current["observed_at"])
    return current


def main():
    latest = json.loads((PRIVATE / "scheduled-backup-latest.json").read_bytes())
    envelope, key = recover(latest["backup_id"])
    payload = checked_backup(latest, envelope, key, now=datetime.now(UTC))
    admin = Admin()
    try:
        current = authority(admin)
        value = {name: payload[name] for name in ("database", "database_sha256", "snapshot")}
        value["current"] = current
        reply = subprocess.run(  # noqa: S603 - trusted fixed module; authenticated SQL via stdin
            ["C:/Windows/System32/wsl.exe", "-d", "Ubuntu-24.04", "--cd",
             "/mnt/a/hackathon/ProofFlow", "/root/proofflow-check-env/bin/python",
             "-m", "scripts.rehearse_saved_database"],
            input=json.dumps(value).encode(), capture_output=True, timeout=110)
        if reply.returncode:
            # The fixed runner emits classified stages only, never raw SQL diagnostics.
            with (PRIVATE / "evidence" / ("saved-database-failure-"
                  + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f") + ".txt")).open("xb") as out:
                out.write(reply.stderr)
        require(reply.returncode == 0, "SAVED_DATABASE_REHEARSAL_FAILED")
        result = json.loads(reply.stdout)
        # The rehearsal's local timestamp is not current live deletion authority.
        fresh = authority(admin)
        now = wait_for_observation(fresh["observed_at"])
        checked_backup(latest, envelope, key, now=now)
        revalidate_restore(payload["snapshot"], result["plan"], fresh, now=now)
        result.pop("plan")  # Never include workspace identifiers in the public-safe receipt.
        result.update(observed_at=now.isoformat(), snapshot_at=latest["snapshot_at"],
                      expires_at=payload["expires_at"],
                      snapshot_age_seconds=round((now-datetime.fromisoformat(
                          latest["snapshot_at"])).total_seconds(), 3),
                      authenticated_vault_and_receipt=True, fresh_authority_rechecked=True,
                      scope="actual_scheduled_SQL_backup_restored_into_fresh_local_tmpfs_database",
                      provider_calls=0, new_resources=0, owner_offline_keys_used=False,
                      compromised_host_rebuild=False, production_RTO_measured=False)
        print(json.dumps(result))
    finally:
        admin.close()


if __name__ == "__main__":
    main()
