"""Root timer coordinator: DB revocation/cleanup gate, bounded nonroot byte worker."""

import fcntl
import json
import os
import re
import subprocess
from pathlib import Path
from uuid import UUID

HERE = Path(__file__).resolve().parent
SCRATCH = Path("/var/lib/proofflow-retention")
UNIT = "proofflow-retention-bytes.service"


def command(args, raw=None, timeout=30):
    reply = subprocess.run(  # noqa: S603 - fixed administrator commands, no candidate input
        args,
        input=raw,
        capture_output=True,
        timeout=timeout,  # noqa: S603
        env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C"},
    )
    if reply.returncode or len(reply.stdout) > 65536:
        raise RuntimeError("RETENTION_ADMIN_FAILED")
    return reply.stdout.strip()


def sql(statement):
    return command(
        [
            "/usr/bin/docker",
            "--host=unix:///var/run/docker.sock",
            "exec",
            "-i",
            "--user=70:70",
            "proofflow-budget",
            "psql",
            "-X",
            "-qAt",
            "-h",
            "/run/proofflow-budget",
            "-U",
            "postgres",
            "-d",
            "proofflow_product",
            "--set",
            "ON_ERROR_STOP=1",
        ],
        ("SET ROLE pf_product_provisioner; " + statement).encode(),
    )


def stop():
    if (
        command(["/usr/bin/systemctl", "show", UNIT, "--property=LoadState", "--value"])
        != b"not-found"
    ):
        command(["/usr/bin/systemctl", "stop", UNIT])


def main():
    if os.geteuid() != 0:
        raise RuntimeError("ADMINISTRATOR_REQUIRED")
    lock = os.open(SCRATCH / "lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        plans = json.loads(sql("SELECT pf_product.retention_plan();"))
        completed = 0
        operations = list(plans)
        if sql("SELECT pf_product.retention_expiry_ready();") == b"t":
            operations.append({"operation": "prune_expired_markers_v1"})
        for plan in operations:
            pruning = plan == {"operation": "prune_expired_markers_v1"}
            workspace = None if pruning else str(UUID(plan["workspace"]))
            digest = None if pruning else plan["manifest_sha256"]
            if not pruning and re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                raise RuntimeError("RETENTION_PLAN_INVALID")
            request, response = SCRATCH / "request", SCRATCH / "response"
            stop()
            for path, raw in ((request, json.dumps(plan).encode()), (response, b"")):
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
                try:
                    os.write(fd, raw)
                    os.fsync(fd)
                finally:
                    os.close(fd)
            props = {
                "User": "10003",
                "Group": "10003",
                "UMask": "0077",
                "PrivateNetwork": "yes",
                "PrivateDevices": "yes",
                "NoNewPrivileges": "yes",
                "CapabilityBoundingSet": "",
                "ProtectSystem": "strict",
                "ProtectHome": "yes",
                "RestrictNamespaces": "yes",
                "RestrictAddressFamilies": "AF_UNIX",
                "SystemCallFilter": "~@network-io @mount @privileged",
                "SystemCallErrorNumber": "EPERM",
                "BindPaths": "/var/lib/proofflow-product/assets:/run/proofflow-retention-assets "
                "/var/lib/proofflow-product/jobs:/run/proofflow-retention-jobs",
                "ReadWritePaths": "/run/proofflow-retention-assets /run/proofflow-retention-jobs",
                "MemoryMax": "134217728",
                "MemorySwapMax": "0",
                "CPUQuota": "100%",
                "TasksMax": "16",
                "RuntimeMaxSec": "20s",
                "TimeoutStopSec": "2s",
                "LimitNOFILE": "64",
                "LimitFSIZE": "65536",
                "LimitCORE": "0",
                "StandardInput": "file:" + str(request),
                "StandardOutput": "file:" + str(response),
                "StandardError": "null",
                "KillMode": "control-group",
            }
            try:
                command(
                    [
                        "/usr/bin/systemd-run",
                        "--quiet",
                        "--wait",
                        "--collect",
                        "--unit=" + UNIT,
                        *["--property=" + k + "=" + v for k, v in props.items()],
                        "/usr/bin/python3",
                        "-I",
                        "-B",
                        str(HERE / "retention.py"),
                    ],
                    timeout=28,
                )
                receipt = json.loads(response.read_bytes())
                if pruning:
                    if (set(receipt) != {"removed", "deferred"}
                            or type(receipt["removed"]) is not int
                            or not 0 <= receipt["removed"] <= 32
                            or receipt["deferred"] not in (None, "RAW_TREES_PRESENT")):
                        raise RuntimeError("RETENTION_EXPIRY_RECEIPT_INVALID")
                    sql("SELECT pf_product.prune_deletion_metadata();")
                    continue
                if receipt != {
                    "workspace": workspace,
                    "manifest_sha256": digest,
                    "bytes_removed": True,
                    "restore_markers": True,
                }:
                    raise RuntimeError("RETENTION_RECEIPT_INVALID")
                sql("SELECT pf_product.complete_deletion('" + workspace + "','" + digest + "');")
                completed += 1
            finally:
                stop()
                request.unlink(missing_ok=True)
                response.unlink(missing_ok=True)
        print(json.dumps({"retention_plans": len(plans), "completed": completed}))
    finally:
        os.close(lock)


if __name__ == "__main__":
    main()
