"""Root-owned timer with a bounded nonroot, network-denied physical deletion process."""

import json
import os
import re
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from install_product_services import command, directory, write  # noqa: E402


def service_update(path, raw):
    """Only replace a prior exact service whose sole change is its pinned revision."""
    target = Path(path)
    if target.exists() or target.is_symlink():
        info = target.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != 0o644):
            raise RuntimeError("RETENTION_UNIT_UNSAFE")
        old = target.read_bytes()
        if old != raw:
            pattern = rb"/opt/proofflow-retention/[a-f0-9]{64}/product_retention_host.py"
            if (len(re.findall(pattern, old)) != 1 or len(re.findall(pattern, raw)) != 1
                    or re.sub(pattern, b"REVISION", old) != re.sub(pattern, b"REVISION", raw)):
                raise RuntimeError("RETENTION_UNIT_POLICY_CHANGED")
            import hashlib

            backup = str(target) + ".previous-" + hashlib.sha256(old).hexdigest()
            write(backup, old, mode=0o644)
            command(["/usr/bin/systemctl", "stop", "proofflow-product-retention.timer"])
            command(["/usr/bin/systemctl", "stop", "proofflow-product-retention.service"])
            temporary = str(target) + ".next"
            write(temporary, raw, mode=0o644)
            os.replace(temporary, target)
            parent = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(parent)
            finally:
                os.close(parent)
            return
    write(path, raw, mode=0o644)


def main():
    if os.geteuid() != 0:
        raise RuntimeError("ADMINISTRATOR_REQUIRED")
    here = Path(__file__).resolve().parent
    directory("/var/lib/proofflow-retention")
    service = f"""[Unit]
Description=ProofFlow revoked workspace retention coordinator
Requires=proofflow-budget.service
After=proofflow-budget.service
[Service]
Type=oneshot
UMask=0077
ExecStart=/usr/bin/python3 -I -B {here}/product_retention_host.py
TimeoutStartSec=240
TimeoutStopSec=5
MemoryMax=512M
TasksMax=32
LimitCORE=0
StandardOutput=journal
StandardError=journal
""".encode()
    timer = b"""[Unit]
Description=ProofFlow private workspace retention schedule
[Timer]
OnBootSec=1min
OnUnitInactiveSec=1min
AccuracySec=5s
Unit=proofflow-product-retention.service
[Install]
WantedBy=timers.target
"""
    service_update("/etc/systemd/system/proofflow-product-retention.service", service)
    write("/etc/systemd/system/proofflow-product-retention.timer", timer, mode=0o644)
    command(["/usr/bin/systemctl", "daemon-reload"])
    command(["/usr/bin/systemctl", "enable", "--now", "proofflow-product-retention.timer"])
    command(["/usr/bin/systemctl", "start", "proofflow-product-retention.service"], timeout=245)
    print(json.dumps({"timer": "enabled", "byte_uid": 10003, "byte_network": "denied",
                      "raw_guest_expiry_margin_seconds": 300, "metadata_pruning": "not_enabled"}))


if __name__ == "__main__":
    main()
