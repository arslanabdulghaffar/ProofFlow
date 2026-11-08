"""Actual local inert recovery and container-owned timeout/ephemeral-byte cleanup."""

import argparse
import base64
import hashlib
import json
import re
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from asset_recovery_container import WSL, absent, command, run
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from vultr_phase1 import PRIVATE, ROOT

sys.path.insert(0, str(ROOT))
from orchestrator.asset_backup import seal  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt-name", default="phase5-recovery-tmpfs.json")
    receipt_name = parser.parse_args().receipt_name
    if re.fullmatch(r"phase[56]-[a-z0-9-]{1,90}\.json", receipt_name) is None:
        raise RuntimeError("RECOVERY_RECEIPT_NAME_INVALID")
    destination = PRIVATE / "evidence" / receipt_name
    if destination.exists():
        raise RuntimeError("RECOVERY_RECEIPT_EXISTS_RECONCILE_BEFORE_RETRY")
    now = datetime.now(UTC)
    workspace = str(uuid4())
    snapshot = {"observed_at": now.isoformat(), "workspaces": [{
        "id": workspace, "created_at": (now-timedelta(minutes=1)).isoformat(),
        "expires_at": (now+timedelta(hours=1)).isoformat()}]}
    content = b"INERT_ASSET_RECOVERY_MEMORY_ONLY_FIXTURE"
    assets = [{"workspace": workspace, "created_at": now.isoformat(),
               "sha256": hashlib.sha256(content).hexdigest(), "bytes": content}]
    key = AESGCM.generate_key(bit_length=256)
    envelope = seal(snapshot, assets, b"inert snapshot; never interpreted as SQL", key, now=now)
    raw = json.dumps({"envelope": base64.b64encode(envelope).decode(),
                      "key": base64.b64encode(key).decode(), "current": snapshot}).encode()
    receipt = run(raw)
    if len(receipt["assets"]) != 1 or receipt["assets"][0]["sha256"] != assets[0]["sha256"]:
        raise RuntimeError("INERT_RECOVERY_BYTES_CHANGED")
    args, name, digest = command(fixture_hold=True)
    started = time.monotonic()
    try:
        fault = subprocess.run(  # noqa: S603 - fixed trusted hold, no candidate program
            args, input=raw, capture_output=True, timeout=35
        )
        elapsed = time.monotonic() - started
        if (fault.returncode != 137 or fault.stdout.strip() != b"INERT_RECOVERY_MATERIALIZED"
                or not 18 <= elapsed < 35 or not absent(name)):
            raise RuntimeError("RECOVERY_INDEPENDENT_TIMEOUT_OR_CLEANUP_FAILED")
        result = {"observed_at": datetime.now(UTC).isoformat(), "completed": True,
                  "scope": "actual_local_pinned_container_inert_synthetic_bytes",
                  "normal_recovery": receipt, "timeout_seconds": round(elapsed, 3),
                  "fault_exit": fault.returncode, "fault_container_removed": True,
                  "fault_cleanup_finally_ran": False, "source_hash": digest,
                  "plaintext_storage": "private_bounded_tmpfs_no_disk_bind",
                  "cloud_calls": 0, "production_restore": False}
        with destination.open("x", encoding="utf-8") as output:
            json.dump(result, output, sort_keys=True)
        print(json.dumps({"normal_inert_recovery": "passed", "timeout_cleanup": "passed",
                          "seconds": round(elapsed, 3), "cloud_calls": 0}))
    finally:
        if not absent(name):
            subprocess.run(  # noqa: S603 - own generated ephemeral test container only
                [*WSL, "docker", "rm", "-f", name], capture_output=True, check=True, timeout=10
            )


if __name__ == "__main__":
    main()
