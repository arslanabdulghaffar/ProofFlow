"""One-shot kernel149 maintenance on existing idle private hosts.

Use install, status, reboot, status in that order, worker before control. Every
mutation has a durable intent; failures require reconciliation, never blind retry.
No new resources, payment, admission, candidate, model, or product PR operation.
"""

import argparse
import json
import os
import re
from contextlib import closing
from datetime import UTC, datetime

from product_live_session import LiveSession, require
from vultr_credit_guard import run as credit_guard
from vultr_phase1 import PRIVATE, Admin

VERSION = "6.8.0-149.149"
KERNEL = "6.8.0-149-generic"
PACKAGES = (
    "linux-generic", "linux-headers-generic", "linux-image-generic",
    "linux-headers-6.8.0-149", "linux-headers-6.8.0-149-generic",
    "linux-image-6.8.0-149-generic", "linux-modules-6.8.0-149-generic",
    "linux-modules-extra-6.8.0-149-generic", "linux-libc-dev", "linux-tools-common",
)
UNIT = "proofflow-kernel149"
INSTALL = ("/usr/bin/apt-get -y --no-remove --no-install-recommends "
           "-o Acquire::Retries=0 -o Acquire::http::Timeout=20 "
           "-o Acquire::https::Timeout=20 install "
           + " ".join(p + "=" + VERSION for p in PACKAGES))


def validate_simulation(text):
    if any(line.startswith("Remv ") for line in text.splitlines()):
        raise RuntimeError("KERNEL_PLAN_REMOVES_PACKAGES")
    actual = {}
    for line in text.splitlines():
        if not line.startswith("Inst "):
            continue
        match = re.fullmatch(r"Inst (\S+)(?: \[[^]]+\])? \((\S+) ([^\n]+)\)(?: \[.*\])?", line)
        require(match is not None, "KERNEL_PLAN_UNRECOGNIZED")
        name, version, origin = match.groups()
        require(name not in actual and "Ubuntu:24.04/noble-updates" in origin,
                "KERNEL_PLAN_ORIGIN_OR_DUPLICATE")
        actual[name] = version
    require(actual == dict.fromkeys(PACKAGES, VERSION), "KERNEL_PLAN_CHANGED")


def persist(path, record):
    pending = path.with_suffix(".pending")
    with pending.open("xb") as output:
        output.write(json.dumps(record, indent=2).encode())
        output.flush()
        os.fsync(output.fileno())
    os.replace(pending, path)


def host(admin, role, command):
    result = admin.host(role, command, timeout=45)
    require(result.returncode == 0, "KERNEL_HOST_COMMAND_FAILED")
    return result.stdout.decode().strip()


def observe(admin, role):
    return {
        "kernel": host(admin, role, "uname -r"),
        "boot_id": host(admin, role, "cat /proc/sys/kernel/random/boot_id"),
        "packages": host(admin, role, "dpkg-query -W -f='${Package} ${Version}\\n' "
                         + " ".join(PACKAGES)),
        "unit": host(admin, role, "systemctl show " + UNIT + ".service "
                     "--property=LoadState,ActiveState,SubState,Result,ExecMainStatus"),
        "dpkg_audit": host(admin, role, "dpkg --audit"),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=("worker", "control"))
    parser.add_argument("action", choices=("install", "status", "reboot"))
    args = parser.parse_args()
    path = PRIVATE / ("evidence/phase5-kernel149-" + args.role + ".json")
    if args.action == "status":
        with closing(Admin()) as admin:
            record = json.loads(path.read_bytes())
            record["credit"] = credit_guard(admin, datetime.now(UTC))
            record["observation"] = observe(admin, args.role)
            persist(path, record)
            print(json.dumps(record["observation"]))
        return
    with LiveSession() as live:
        if args.role == "control":
            require(host(live.admin, "worker", "uname -r") == KERNEL,
                    "WORKER_MUST_BE_UPDATED_FIRST")
        require(live.sql("SELECT count(*) FROM pf_product.workspaces;") == b"0",
                "KERNEL_MAINTENANCE_REQUIRES_EMPTY_PRODUCT")
        require(live.sql("SELECT count(*) FROM pf_product.jobs WHERE state NOT IN "
                         "('NEEDS_REVIEW','FAILED_INFRA','CANCELLED');") == b"0", "JOBS_NOT_IDLE")
        require(live.sql("SELECT bool_and(blocked) FROM pf_budget.accounts;",
                         "proofflow_budget") == b"t", "INFERENCE_MUST_STAY_CLOSED")
        require(live.sql("SELECT count(*) FROM pf_product.pr_intents WHERE lease_owner IS NOT NULL "
                         "OR state IN ('BRANCH_PENDING','COMMIT_PENDING','PR_PENDING');") == b"0",
                "EXTERNAL_WRITES_NOT_IDLE")
        machine = host(live.admin, args.role, "cat /etc/machine-id")
        require(machine == live.admin.state[args.role + "_machine_id"], "HOST_IDENTITY_CHANGED")
        require(not host(live.admin, "worker", "systemctl list-units --all --no-legend "
                         "'proofflow-exec-*.service'"), "EXECUTION_UNITS_REMAIN")
        if args.action == "install":
            require(not path.exists(), "KERNEL_INSTALL_ALREADY_STARTED_RECONCILE")
            require(host(live.admin, args.role, "uname -r") == "6.8.0-147-generic",
                    "UNEXPECTED_KERNEL_PREDECESSOR")
            simulation = host(live.admin, args.role, INSTALL.replace(" -y ", " --simulate "))
            validate_simulation(simulation)
            record = {"started_at": datetime.now(UTC).isoformat(), "credit": live.credit,
                      "before_boot_id": host(live.admin, args.role,
                                             "cat /proc/sys/kernel/random/boot_id"),
                      "role": args.role, "version": VERSION, "simulation": simulation,
                      "stage": "install_intent", "new_resources": 0, "provider_calls": 0}
            persist(path, record)
            host(live.admin, args.role, "systemd-run --no-block --unit=" + UNIT
                 + " --property=Type=oneshot --property=RemainAfterExit=yes "
                 "--property=TimeoutStartSec=900 /usr/bin/env DEBIAN_FRONTEND=noninteractive "
                 "NEEDRESTART_MODE=l " + INSTALL)
            record["stage"] = "install_dispatched"
        else:
            record = json.loads(path.read_bytes())
            require(record["stage"] == "install_dispatched", "REBOOT_ALREADY_STARTED_RECONCILE")
            current = observe(live.admin, args.role)
            require("Result=success" in current["unit"] and "ExecMainStatus=0" in current["unit"]
                    and "SubState=exited" in current["unit"] and not current["dpkg_audit"],
                    "KERNEL_INSTALL_NOT_SUCCESSFUL")
            require(dict(line.split() for line in current["packages"].splitlines())
                    == dict.fromkeys(PACKAGES, VERSION), "INSTALLED_PACKAGE_MISMATCH")
            record["installed"] = current
            record["stage"] = "reboot_intent"
            persist(path, record)
            host(live.admin, args.role, "systemd-run --unit=" + UNIT
                 + "-reboot --on-active=5s /usr/bin/systemctl reboot")
            record["stage"] = "reboot_dispatched"
        persist(path, record)
        print(json.dumps({"role": args.role, "stage": record["stage"]}))


if __name__ == "__main__":
    main()
