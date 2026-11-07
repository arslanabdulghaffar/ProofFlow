"""Owner-operated synthetic recovery kit; hidden password, no automatic live restore."""

import getpass
import json
import os
import sys
from datetime import UTC, datetime

from asset_backup_vault import recover
from product_live_session import PRIVATE, require

from orchestrator.portable_backup import export_portable


def main():
    require(sys.stdin.isatty(), "PORTABLE_EXPORT_REQUIRES_PRIVATE_INTERACTIVE_TERMINAL")
    latest = json.loads((PRIVATE / "scheduled-backup-latest.json").read_bytes())
    print("Synthetic project recovery only. Keep your password and kit separately offline.")
    print("This does not recover lost deletion authority or authorize a production restore.")
    password = getpass.getpass("Recovery password (at least 24 UTF-8 bytes; never send in chat): ")
    repeated = getpass.getpass("Repeat recovery password: ")
    require(password == repeated, "PORTABLE_PASSWORDS_DIFFER")
    envelope, key = recover(latest["backup_id"])
    raw = export_portable(envelope, key, password.encode(), now=datetime.now(UTC))
    target = PRIVATE / "evidence" / ("portable-" + latest["backup_id"] + ".pfr")
    with target.open("xb") as output:
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())
    print("Encrypted kit: " + str(target))
    print("Expires: " + latest["expires_at"] + "; destroy exported copies by expiry.")
    print("Copy to your secure offline storage. Password was not saved by this helper.")


if __name__ == "__main__":
    main()
