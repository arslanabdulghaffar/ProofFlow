"""Fixed Linux data-only recovery into a temporary private directory, then cleanup."""

import base64
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from orchestrator.asset_backup import open_backup
from orchestrator.asset_recovery import materialize

STAGING_ROOT = Path("/run/proofflow-recovery")


def main():
    mounts = Path("/proc/self/mountinfo").read_text().splitlines()
    if not any(line.split()[4] == str(STAGING_ROOT)
               and line.split(" - ", 1)[1].split()[0] == "tmpfs"
               and {"nosuid", "nodev", "noexec"} <= set(line.split()[5].split(","))
               for line in mounts):
        raise RuntimeError("RECOVERY_REQUIRES_PRIVATE_TMPFS")
    capacity = os.statvfs(STAGING_ROOT)
    if not 0 < capacity.f_blocks * capacity.f_frsize <= 64 * 1024 * 1024:
        raise RuntimeError("RECOVERY_TMPFS_LIMIT_INVALID")
    expected = {"memory.max": "536870912", "memory.swap.max": "0", "pids.max": "16"}
    observed = {name: (Path("/sys/fs/cgroup") / name).read_text().strip() for name in expected}
    if observed != expected or os.geteuid() != 10003:
        raise RuntimeError("RECOVERY_RESOURCE_BOUNDARY_INVALID")
    raw = sys.stdin.buffer.read(96 * 1024 * 1024 + 1)
    if len(raw) > 96 * 1024 * 1024:
        raise RuntimeError("RECOVERY_INPUT_LIMIT")
    value = json.loads(raw)
    if set(value) != {"envelope", "key", "current"}:
        raise RuntimeError("RECOVERY_INPUT_INVALID")
    payload = open_backup(
        base64.b64decode(value["envelope"], validate=True),
        base64.b64decode(value["key"], validate=True),
        now=datetime.now(UTC),
    )
    with TemporaryDirectory(prefix="proofflow-asset-recovery-", dir=STAGING_ROOT) as target:
        fd = os.open(target, os.O_RDONLY | os.O_DIRECTORY)
        try:
            result = materialize(fd, payload, value["current"], now=datetime.now(UTC))
            if os.environ.get("PROOFFLOW_INERT_RECOVERY_HOLD") == "1":
                # Explicit trusted fault fixture; the container-owned timeout
                # must kill this process and remove its tmpfs without finally.
                print("INERT_RECOVERY_MATERIALIZED", flush=True)
                time.sleep(60)
        finally:
            os.close(fd)
    if Path(target).exists():
        raise RuntimeError("RECOVERY_FIXTURE_CLEANUP_FAILED")
    print(json.dumps({**result, "temporary_asset_cleanup": "confirmed",
                      "observed_cgroup_limits": observed}))


if __name__ == "__main__":
    main()
