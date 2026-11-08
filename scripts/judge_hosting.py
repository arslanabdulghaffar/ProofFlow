# ruff: noqa: E501 - fixed administrative SQL and remote Python snippets
"""Explicit reviewed judging activation/status/close using existing encrypted admin access."""

import argparse
import json
import shlex
from datetime import UTC, datetime

from vultr_credit_guard import run as credit_guard
from vultr_phase1 import PRIVATE, Admin


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("status", "arm", "close", "drain"))
    options = parser.parse_args()
    receipt = json.loads((PRIVATE / "evidence/judge-access-install.json").read_bytes())
    revision = receipt["revision"]
    if not revision.startswith("/var/lib/proofflow-product-setup/judging-"):
        raise RuntimeError("JUDGE_REVISION_INVALID")
    admin = Admin()
    try:

        def host(command, raw=None):
            result = admin.host("control", command, stdin=raw, timeout=180)
            if result.returncode:
                (PRIVATE / "evidence/judge-operation-error.txt").write_bytes(
                    result.stdout + result.stderr
                )
                raise RuntimeError("JUDGING_OPERATION_FAILED_RECONCILE")
            return result.stdout.strip()

        if host("cat /etc/machine-id").decode() != admin.state["control_machine_id"]:
            raise RuntimeError("CONTROL_CHANGED")
        for name, digest in receipt["hashes"].items():
            actual = host("sha256sum " + shlex.quote(revision + "/" + name))
            if actual.decode().split()[0] != digest:
                raise RuntimeError("JUDGE_SOURCE_CHANGED")
        guard = "/usr/bin/python3 " + shlex.quote(revision + "/judging_guard.py")
        if options.action == "arm":
            review = credit_guard(admin, datetime.now(UTC))
            if review["credit_guard"] != "within_early_cutoff":
                raise RuntimeError("CREDIT_CLOSED")
            statement = "SELECT NOT EXISTS(SELECT 1 FROM pf_product.execution_policy WHERE enabled) AND NOT EXISTS(SELECT 1 FROM pf_product.jobs WHERE state NOT IN ('NEEDS_REVIEW','FAILED_INFRA','CANCELLED')) AND NOT EXISTS(SELECT 1 FROM pf_product.repairs WHERE state IN ('QUEUED','RUNNING','RECONCILING'));"
            reply = host(
                "docker exec -i --user=70:70 proofflow-budget psql -X -qAt -h /run/proofflow-budget -U postgres -d proofflow_product --set ON_ERROR_STOP=1",
                statement.encode(),
            )
            if reply != b"t":
                raise RuntimeError("JUDGE_ARM_REQUIRES_CLOSED_IDLE")
            config = {
                "enabled": True,
                "reviewed_at": datetime.now(UTC).isoformat(),
                "funded_until": admin.state["review_due_at"],
                "boot_id": host("cat /proc/sys/kernel/random/boot_id").decode(),
            }
            code = "import sys,json,os;from pathlib import Path;p=Path('/etc/proofflow-judging/config.json');v=json.load(sys.stdin);f=p.with_suffix('.pending');fd=os.open(f,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600);os.write(fd,json.dumps(v).encode());os.fsync(fd);os.close(fd);os.replace(f,p)"
            host("/usr/bin/python3 -c " + shlex.quote(code), json.dumps(config).encode())
            result = json.loads(host(guard + " arm"))
            host("systemctl enable --now proofflow-judging.timer")
        elif options.action in ("close", "drain"):
            result = json.loads(host(guard + " " + options.action))
        else:
            config = json.loads(host("cat /etc/proofflow-judging/config.json"))
            result = {
                "enabled": config["enabled"],
                "draining": config.get("draining", False),
                "funded_until": config["funded_until"],
                "timer": host("systemctl is-active proofflow-judging.timer").decode(),
                "last_result": host(
                    "systemctl show proofflow-judging.service -p Result --value"
                ).decode(),
            }
            statement = "SELECT json_build_object('admission_open',available_until>clock_timestamp(),'claims',claims,'active_guests',(SELECT count(*) FROM pf_product.workspaces WHERE kind='guest' AND revoked_at IS NULL AND expires_at>clock_timestamp()),'last_guest_expiry',(SELECT max(expires_at) FROM pf_product.workspaces WHERE kind='guest' AND revoked_at IS NULL)) FROM pf_product.judge_admission;"
            result['admission'] = json.loads(host('docker exec -i --user=70:70 proofflow-budget psql -X -qAt -h /run/proofflow-budget -U postgres -d proofflow_product --set ON_ERROR_STOP=1', statement.encode()))
        print(json.dumps(result))
    finally:
        admin.close()


if __name__ == "__main__":
    main()
