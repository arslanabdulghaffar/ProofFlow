"""Owner-operated synthetic recovery kit; hidden password, no automatic live restore."""

import getpass
import hashlib
import json
import os
import sys
from datetime import UTC, datetime

from asset_backup_vault import recover
from product_live_session import PRIVATE, require

from orchestrator.asset_backup import open_backup
from orchestrator.portable_backup import export_portable


def read_latest(root):
    """An interrupted pointer replacement needs reconciliation, never silent fallback."""
    path = root / "scheduled-backup-latest.json"
    pending = path.with_suffix(".pending")
    require(not pending.exists(), "BACKUP_RECEIPT_RECONCILE_REQUIRED")
    with path.open("rb") as source:
        raw = source.read(65537)
    require(len(raw) <= 65536, "BACKUP_RECEIPT_LIMIT")
    value = json.loads(raw)
    require(type(value) is dict, "BACKUP_RECEIPT_INVALID")
    require(not pending.exists(), "BACKUP_RECEIPT_RECONCILE_REQUIRED")
    return value


def require_current_receipt(latest, root):
    require(read_latest(root) == latest, "BACKUP_RECEIPT_CHANGED_DURING_RECOVERY")


def checked_backup(latest, envelope, key, *, now):
    """Bind the local scheduling pointer to authenticated contents before export."""
    payload = open_backup(envelope, key, now=now)
    require(hashlib.sha256(envelope).hexdigest() == latest["encrypted_sha256"]
            and payload["expires_at"] == latest["expires_at"]
            and payload["snapshot"]["observed_at"] == latest["snapshot_at"],
            "PORTABLE_BACKUP_RECEIPT_CHANGED")
    return payload


def main():
    require(sys.stdin.isatty(), "PORTABLE_EXPORT_REQUIRES_PRIVATE_INTERACTIVE_TERMINAL")
    latest = read_latest(PRIVATE)
    envelope, key = recover(latest["backup_id"])
    payload = checked_backup(latest, envelope, key, now=datetime.now(UTC))
    print("Synthetic project recovery only. Keep your password and kit separately offline.")
    print("This does not recover lost deletion authority or authorize a production restore.")
    password = getpass.getpass("Recovery password (at least 24 UTF-8 bytes; never send in chat): ")
    repeated = getpass.getpass("Repeat recovery password: ")
    require(password == repeated, "PORTABLE_PASSWORDS_DIFFER")
    # Recheck after the potentially long interactive wait. Never trust receipt expiry.
    # A key may have been retired while waiting; re-read through the current vault.
    envelope, key = recover(latest["backup_id"])
    require_current_receipt(latest, PRIVATE)
    checked_backup(latest, envelope, key, now=datetime.now(UTC))
    raw = export_portable(envelope, key, password.encode(), now=datetime.now(UTC))
    checked_backup(latest, envelope, key, now=datetime.now(UTC))
    require_current_receipt(latest, PRIVATE)
    target = PRIVATE / "evidence" / ("portable-" + latest["backup_id"] + ".pfr")
    with target.open("xb") as output:
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())
    print("Encrypted kit: " + str(target))
    print("Expires: " + payload["expires_at"] + "; destroy exported copies by expiry.")
    print("Copy to your secure offline storage. Password was not saved by this helper.")


if __name__ == "__main__":
    main()
