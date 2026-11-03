"""Administrator fault injection against owned probe services; no policy relaxation.

Temporarily disable supervisor restart to prove the execution's independent
watchdog, or kill only the trusted controller probe to prove disconnect handling.
"""

import argparse
import json
import time
from datetime import UTC, datetime
from uuid import uuid4

from vultr_phase1 import PRIVATE, ROOT, Admin


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("supervisor", "controller"))
    args = parser.parse_args()
    admin = Admin()
    restore_restart = False
    execution, job = uuid4().hex, uuid4().hex
    unit = "proofflow-exec-" + execution + ".service"
    control_unit = "proofflow-crash-probe-" + execution
    script = "/opt/proofflow-control/probe_worker_crash_controller.py"
    dropin = "/run/systemd/system/proofflow-worker.service.d/99-crash-probe.conf"
    try:

        def host(role, command, data=None):
            result = admin.host(role, command, stdin=data, timeout=40)
            if result.returncode:
                raise RuntimeError("CRASH_PROBE_ADMIN_OPERATION_FAILED")
            return result.stdout

        for name in ("probe_worker_controller.py", "probe_worker_crash_controller.py"):
            host(
                "control",
                "umask 077; cat > /opt/proofflow-control/" + name,
                (ROOT / "scripts" / name).read_bytes(),
            )
        if args.mode == "supervisor":
            host("worker", "install -d -m 0755 /run/systemd/system/proofflow-worker.service.d")
            host("worker", "set -C; cat > " + dropin, b"[Service]\nRestart=no\n")
            restore_restart = True
            host("worker", "systemctl daemon-reload")
            if (
                host("worker", "systemctl show proofflow-worker.service -p Restart --value").strip()
                != b"no"
            ):
                raise RuntimeError("RESTART_TEST_PRECONDITION_FAILED")
        host(
            "control",
            "systemd-run --quiet --unit="
            + control_unit
            + " --property=RuntimeMaxSec=60 --property=KillMode=control-group "
            "--property=MemoryMax=134217728 --property=TasksMax=16 "
            "/usr/bin/python3 -I -B " + script + " dispatch " + execution + " " + job,
        )
        deadline = time.monotonic() + 8
        started = time.monotonic()
        while True:
            values = host("worker", "systemctl show " + unit + " -p ActiveState -p MainPID")
            state = dict(line.split("=", 1) for line in values.decode().splitlines())
            if state.get("ActiveState") == "active" and state.get("MainPID") not in (None, "0"):
                break
            if time.monotonic() >= deadline:
                raise RuntimeError("EXECUTION_NOT_OBSERVED_ACTIVE")
            time.sleep(0.1)
        if args.mode == "supervisor":
            host(
                "worker",
                "systemctl kill --kill-whom=main --signal=SIGKILL proofflow-worker.service",
            )
        else:
            host("control", "systemctl kill --kill-whom=all --signal=SIGKILL " + control_unit)
        # Inspect only this exact execution's systemd and kernel state, not logs
        # authored by a candidate. It has at most20s execution and2s exit observation.
        query = """import json
from pathlib import Path
p=Path('/sys/fs/cgroup/system.slice/UNIT')
print(json.dumps({'cgroup_exists':p.exists(),
 'events':(p/'cgroup.events').read_text() if p.exists() else None,
 'process_count':len((p/'cgroup.procs').read_text().split()) if p.exists() else 0}))
""".replace("UNIT", unit)
        while True:
            kernel = json.loads(host("worker", "/usr/bin/python3 -I -S -B -", query.encode()))
            values = host(
                "worker", "systemctl show " + unit + " -p ActiveState -p MainPID -p Result"
            )
            state = dict(line.split("=", 1) for line in values.decode().splitlines())
            empty = not kernel["cgroup_exists"] or "populated 0" in kernel["events"].splitlines()
            if (
                empty
                and kernel["process_count"] == 0
                and state.get("ActiveState") in ("inactive", "failed")
            ):
                break
            if time.monotonic() - started > 28:
                raise RuntimeError("INDEPENDENT_WATCHDOG_OR_CLEANUP_FAILED")
            time.sleep(0.5)
        elapsed = round(time.monotonic() - started, 3)
        if args.mode == "supervisor":
            if state.get("Result") != "timeout":
                raise RuntimeError("INDEPENDENT_WATCHDOG_NOT_PROVEN")
            host("worker", "systemctl start proofflow-worker.service")
        status_deadline = time.monotonic() + 5
        while True:
            result = admin.host("control", "/usr/bin/python3 -I -B " + script
                                + " status " + execution + " " + job)
            if result.returncode == 0:
                status = json.loads(result.stdout)
                break
            if time.monotonic() >= status_deadline:
                raise RuntimeError("RECOVERY_STATUS_READBACK_FAILED")
            time.sleep(0.1)  # Read-only status reconciliation, never redispatch.
        receipt = status.get("receipt") or {}
        if (
            status["state"] != "CLEANED"
            or receipt.get("cleanup") != "confirmed"
            or receipt.get("verification") != "NOT_PERFORMED"
        ):
            raise RuntimeError("RECOVERY_NOT_CONFIRMED")
        check = """from pathlib import Path
p=Path('/var/lib/proofflow-worker/state/executions/IDENTIFIER')
if p.exists(): raise SystemExit('STAGING_REMAINS')
print('staging_absent')
""".replace("IDENTIFIER", execution)
        host("worker", "/usr/bin/python3 -I -S -B -", check.encode())
        report = {
            "mode": args.mode,
            "recorded_at": datetime.now(UTC).isoformat(),
            "execution": execution,
            "elapsed_seconds": elapsed,
            "unit": state,
            "kernel": kernel,
            "status": status,
            "staging": "absent",
            "acceptance": "passed",
        }
        (PRIVATE / "evidence" / ("crash-" + args.mode + "-" + execution + ".json")).write_text(
            json.dumps(report, sort_keys=True, indent=2)
        )
        print(
            json.dumps(
                {
                    k: report[k]
                    for k in ("mode", "elapsed_seconds", "unit", "kernel", "staging", "acceptance")
                }
            )
        )
    finally:
        if restore_restart:
            cleanup = """from pathlib import Path
p=Path(__DROPIN_PATH__)
if p.read_bytes()!=b'[Service]\\nRestart=no\\n': raise SystemExit('DROPIN_CHANGED')
p.unlink()
""".replace("__DROPIN_PATH__", repr(dropin))
            result = admin.host("worker", "/usr/bin/python3 -I -S -B -", stdin=cleanup.encode())
            if result.returncode:
                raise RuntimeError("RESTART_POLICY_RESTORE_FAILED")
            result = admin.host("worker", "systemctl daemon-reload")
            if result.returncode:
                raise RuntimeError("RESTART_POLICY_RELOAD_FAILED")
            # A failed critical probe is left stopped, never silently reopened here.
        admin.close()


if __name__ == "__main__":
    main()
