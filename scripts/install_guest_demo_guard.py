"""Trusted root service installer; source and timer precede opening admission."""

import hashlib
import json
import os
from pathlib import Path

from install_product_services import command, directory, write


def main():
    if os.geteuid() != 0:
        raise RuntimeError("ADMINISTRATOR_REQUIRED")
    directory("/etc/proofflow-guest-demo")
    source = Path(__file__).with_name("guest_demo_guard.py")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    base = directory("/opt/proofflow-guest-demo")
    target = directory(base / digest)
    write(target / "guest_demo_guard.py", source.read_bytes())
    unit = f"""[Unit]
Description=ProofFlow guest admission expiry guard
After=docker.service proofflow-budget.service
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 -I -B {target}/guest_demo_guard.py check
TimeoutStartSec=100
TimeoutStopSec=5
NoNewPrivileges=yes
PrivateTmp=yes
ProtectHome=yes
UMask=0077
MemoryMax=64M
TasksMax=16
LimitCORE=0
"""
    timer = b"""[Unit]
Description=ProofFlow guest window guard independent of desktop
[Timer]
OnBootSec=5s
OnUnitActiveSec=10s
AccuracySec=1s
[Install]
WantedBy=timers.target
"""
    write("/etc/systemd/system/proofflow-guest-demo.service", unit.encode(), mode=0o644)
    write("/etc/systemd/system/proofflow-guest-demo.timer", timer, mode=0o644)
    # A reboot must check boot identity before any dispatcher can resume work.
    dropin = directory('/etc/systemd/system/proofflow-product-dispatcher.service.d', mode=0o755)
    write(dropin / 'guest-guard.conf',
          b'[Unit]\nRequires=proofflow-guest-demo.service\nAfter=proofflow-guest-demo.service\n',
          mode=0o644)
    command(
        [
            "/usr/bin/systemd-analyze",
            "verify",
            "/etc/systemd/system/proofflow-guest-demo.service",
            "/etc/systemd/system/proofflow-guest-demo.timer",
            "/etc/systemd/system/proofflow-product-dispatcher.service",
        ]
    )
    command(["/usr/bin/systemctl", "daemon-reload"])
    command(["/usr/bin/systemctl", "enable", "--now", "proofflow-guest-demo.timer"])
    print(
        json.dumps(
            {
                "guard_source_sha256": digest,
                "timer_enabled": True,
                "admission_opened": False,
                "path": str(target / "guest_demo_guard.py"),
            }
        )
    )


if __name__ == "__main__":
    main()
