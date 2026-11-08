"""Actual fresh network-denied recovery containers; synthetic inert bytes only."""

import base64
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from asset_recovery_container import WSL, absent, command
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from vultr_phase1 import ROOT

sys.path.insert(0, str(ROOT))
from orchestrator.asset_backup import seal  # noqa: E402


def fixture(case):
    now = datetime.now(UTC)
    saved = now - timedelta(days=2) if case == "expired_backup" else now - timedelta(seconds=2)
    workspace = str(uuid4())
    snapshot = {"observed_at": saved.isoformat(), "workspaces": [{
        "id": workspace, "created_at": (saved-timedelta(minutes=1)).isoformat(),
        "expires_at": (saved+timedelta(hours=1)).isoformat()}]}
    content = b"INERT_RECOVERY_DENIAL_FIXTURE_NEVER_EXECUTED"
    digest = hashlib.sha256(content).hexdigest()
    key = AESGCM.generate_key(bit_length=256)
    envelope = seal(snapshot, [{"workspace": workspace, "created_at": saved.isoformat(),
                               "sha256": digest, "bytes": content}],
                    b"inert database; not SQL", key, now=saved)
    current = {**snapshot, "observed_at": now.isoformat()}
    if case == "missing_authority":
        current = None
    elif case == "stale_authority":
        current = {**snapshot, "observed_at": (now-timedelta(seconds=90)).isoformat()}
    elif case == "future_authority":
        current = {**snapshot, "observed_at": (now+timedelta(minutes=5)).isoformat()}
    elif case == "deleted_workspace":
        current["workspaces"] = []
    elif case == "wrong_key":
        key = AESGCM.generate_key(bit_length=256)
    elif case == "tampered_ciphertext":
        envelope = envelope[:-1] + bytes([envelope[-1] ^ 1])
    raw = json.dumps({"envelope": base64.b64encode(envelope).decode(),
                      "key": base64.b64encode(key).decode(), "current": current}).encode()
    return raw, digest


def main():
    results = []
    expected_errors = {
        "missing_authority": "RESTORE_AUTHORITY_INVALID",
        "stale_authority": "RESTORE_CURRENT_AUTHORITY_REQUIRED",
        "future_authority": "RESTORE_CURRENT_AUTHORITY_REQUIRED",
        "wrong_key": "BACKUP_AUTHENTICATION_OR_FORMAT_FAILED",
        "tampered_ciphertext": "BACKUP_AUTHENTICATION_OR_FORMAT_FAILED",
        "expired_backup": "BACKUP_EXPIRED_OR_CLOCK_INVALID",
    }
    for case in ("valid", "deleted_workspace", "missing_authority", "stale_authority",
                 "future_authority", "wrong_key", "tampered_ciphertext", "expired_backup"):
        raw, digest = fixture(case)
        args, name, source_hash = command()
        try:
            reply = subprocess.run(args, input=raw, capture_output=True, timeout=35)  # noqa: S603
            if case in {"valid", "deleted_workspace"}:
                if reply.returncode:
                    raise RuntimeError("RECOVERY_POSITIVE_CONTROL_FAILED")
                receipt = json.loads(reply.stdout)
                expected = [digest] if case == "valid" else []
                if ([a["sha256"] for a in receipt["assets"]] != expected
                        or receipt["temporary_asset_cleanup"] != "confirmed"
                        or receipt["mode"] != "INERT_DATA_ONLY_NO_PROMOTION"):
                    raise RuntimeError("RECOVERY_CONTROL_CHANGED")
            else:
                error = expected_errors[case]
                if (reply.returncode != 1 or reply.stdout.strip()
                        or not reply.stderr.rstrip().endswith((": " + error).encode())):
                    raise RuntimeError("RECOVERY_EXPECTED_DENIAL_NOT_OBSERVED")
            if not absent(name):
                raise RuntimeError("RECOVERY_DENIAL_CLEANUP_UNCONFIRMED")
            results.append({"case": case, "passed": True, "exit": reply.returncode,
                            "denial_code": expected_errors.get(case),
                            "container_removed": True, "source_hash": source_hash})
        finally:
            if not absent(name):
                subprocess.run([*WSL, "docker", "rm", "-f", name],  # noqa: S603
                               capture_output=True, check=True, timeout=10)
    print(json.dumps({"observed_at": datetime.now(UTC).isoformat(), "cases": results,
                      "scope": "real_local_pinned_recovery_containers_synthetic_inert_data",
                      "cloud_calls": 0, "production_restore": False,
                      "compromised_host_rebuild": False, "offline_owner_key_used": False}))


if __name__ == "__main__":
    main()
