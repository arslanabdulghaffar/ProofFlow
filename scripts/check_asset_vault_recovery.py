"""Actual Windows vault exclusion/process-death/interrupted-save checks; inert data only."""

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta

import asset_backup_vault as vault
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from vultr_phase1 import PRIVATE, ROOT


def child(source, *, wait=True):
    args = [sys.executable, "-I", "-c", "import sys;sys.path.insert(0," +
            repr(str(ROOT / "scripts")) + ");" + source]
    options = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE,
               "creationflags": subprocess.CREATE_NO_WINDOW}
    if wait:
        return subprocess.run(args, timeout=10, **options)  # noqa: S603 - fixed trusted code
    return subprocess.Popen(args, **options)  # noqa: S603 - fixed lock holder, no candidate


def main():
    identifier, holder = None, None
    record = {"started_at": datetime.now(UTC).isoformat(), "checks": [], "cloud_calls": 0,
              "scope": "actual_windows_vault_inert_fixture", "completed": False}
    receipt = PRIVATE / "evidence/phase5-vault-recovery-check.json"
    try:
        with vault.exclusive():
            contender = child(
                "import asset_backup_vault as v\n"
                "try: v.expire()\n"
                "except RuntimeError as e:\n"
                " assert str(e)=='ASSET_BACKUP_VAULT_BUSY'\n"
                " print('exclusive_denied')\n"
                "else: raise RuntimeError('LOCK_BYPASSED')\n"
            )
            if contender.returncode or contender.stdout.strip() != b"exclusive_denied":
                raise RuntimeError("VAULT_EXCLUSION_FAILED")
        record["checks"].append("concurrent_process_expiry_denied")
        holder = child(
            "import asset_backup_vault as v,time\n"
            "with v.exclusive():\n"
            " print('lock_held',flush=True)\n"
            " time.sleep(30)\n", wait=False
        )
        try:
            holder.communicate(timeout=3)
            raise RuntimeError("LOCK_HOLDER_EXITED_EARLY")
        except subprocess.TimeoutExpired:
            pass  # Windows communicate drains its reader thread only after EOF.
        holder.terminate()
        output, _ = holder.communicate(timeout=5)
        holder = None
        if output.strip() != b"lock_held":
            raise RuntimeError("LOCK_HOLDER_NOT_READY")
        with vault.exclusive():
            pass
        record["checks"].append("terminated_holder_releases_os_lock")
        key = AESGCM.generate_key(bit_length=256)
        cipher = AESGCM(key).encrypt(b"vault-check1", b"inert recovery fixture", b"fixture")
        identifier = vault.save(cipher, key, datetime.now(UTC) + timedelta(minutes=2))
        with vault.exclusive():
            name = vault.filename(identifier, "pfenc")
            # Scoped fixture fault: emulate a crash while publishing ciphertext.
            vault.checked_path(name, 64 * 1024 * 1024).unlink()
            vault.write_private(name + ".pending", b"partial ciphertext")
        vault.expire()
        if any(PRIVATE.glob("asset-backup-" + identifier + "*")):
            raise RuntimeError("INTERRUPTED_SAVE_NOT_RETIRED")
        record["checks"].append("partial_cipher_and_unusable_key_removed")
        record["completed"] = True
        print(json.dumps(record))
    finally:
        if holder is not None:
            holder.terminate()
            holder.communicate(timeout=5)
        if identifier is not None:
            vault.retire(identifier)
        record["finished_at"] = datetime.now(UTC).isoformat()
        receipt.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    main()
