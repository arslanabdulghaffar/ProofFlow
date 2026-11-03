"""One controlled reboot of a recorded project VM; reconcile, never resend reboot."""

import json
import os
import sys
import time
from datetime import UTC, datetime
from uuid import UUID, uuid4

from vultr_phase1 import PRIVATE, Admin

if len(sys.argv) != 2 or sys.argv[1] not in ("control", "worker"):
    raise SystemExit("PROJECT_ROLE_REQUIRED")
role = sys.argv[1]
admin = Admin()
try:

    def host(command):
        result = admin.host(role, command, timeout=15)
        if result.returncode:
            raise RuntimeError("REBOOT_READBACK_UNAVAILABLE")
        return result.stdout.decode().strip()

    if host("cat /etc/machine-id") != admin.state[role + "_machine_id"]:
        raise RuntimeError("HOST_IDENTITY_MISMATCH")
    if role == "control":
        result = host(
            "docker exec --user=70:70 proofflow-budget psql -X -qAt "
            "-h /run/proofflow-budget -U postgres -d proofflow_budget "
            "-c 'SELECT bool_and(blocked) FROM pf_budget.accounts'"
        )
        if result != "t":
            raise RuntimeError("REBOOT_REQUIRES_CLOSED_ADMISSION")
    else:
        # Read-only cgroup enumeration; no active execution may be interrupted.
        command = """/usr/bin/python3 -I -S -B -c 'from pathlib import Path
assert not list(Path("/sys/fs/cgroup/system.slice").glob("proofflow-exec-*.service"))'
"""
        host(command)
    before = str(UUID(host("cat /proc/sys/kernel/random/boot_id")))
    intent = PRIVATE / ("reboot-" + role + "-" + uuid4().hex + ".json")
    with intent.open("xb") as file:
        file.write(
            json.dumps(
                {"before": before, "role": role, "started_at": datetime.now(UTC).isoformat()}
            ).encode()
        )
        file.flush()
        os.fsync(file.fileno())
    host("systemd-run --unit=proofflow-reboot-probe --on-active=2 /usr/bin/systemctl reboot")
    started = time.monotonic()
    while True:
        if time.monotonic() - started > 180:
            raise RuntimeError("REBOOT_RECOVERY_TIMEOUT_RECONCILE_ONLY")
        try:
            after = str(UUID(host("cat /proc/sys/kernel/random/boot_id")))
            if after != before:
                break
        except (RuntimeError, TimeoutError):
            pass
        time.sleep(3)
    if host("cat /etc/machine-id") != admin.state[role + "_machine_id"]:
        raise RuntimeError("REBOOT_HOST_IDENTITY_CHANGED")
    services = (
        ("proofflow-health.service", "proofflow-budget.service")
        if role == "control"
        else ("proofflow-worker.service",)
    )
    for service in services:
        if host("systemctl is-active " + service) != "active":
            raise RuntimeError("REBOOT_SERVICE_UNAVAILABLE")
    report = {
        "role": role,
        "recorded_at": datetime.now(UTC).isoformat(),
        "new_boot_id": True,
        "same_machine_and_pinned_ssh": True,
        "services_active": list(services),
        "seconds": round(time.monotonic() - started, 2),
        "dependency_probes_required": True,
    }
    (PRIVATE / "evidence" / ("reboot-" + role + ".json")).write_bytes(json.dumps(report).encode())
    print(json.dumps(report))
finally:
    admin.close()
