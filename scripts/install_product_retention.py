"""Root-owned timer with a bounded nonroot, network-denied physical deletion process."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from install_product_services import command, directory, write  # noqa: E402


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
    write("/etc/systemd/system/proofflow-product-retention.service", service, mode=0o644)
    write("/etc/systemd/system/proofflow-product-retention.timer", timer, mode=0o644)
    command(["/usr/bin/systemctl", "daemon-reload"])
    command(["/usr/bin/systemctl", "enable", "--now", "proofflow-product-retention.timer"])
    command(["/usr/bin/systemctl", "start", "proofflow-product-retention.service"], timeout=245)
    print(json.dumps({"timer": "enabled", "byte_uid": 10003, "byte_network": "denied",
                      "raw_guest_expiry_margin_seconds": 300, "metadata_pruning": "not_enabled"}))


if __name__ == "__main__":
    main()
