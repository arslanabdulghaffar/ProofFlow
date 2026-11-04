"""Root-only fixed integration setup on the designated control. Secrets arrive on stdin."""

import base64
import json
import os
import stat
import subprocess
import sys
from pathlib import Path


def command(argv, raw=None):
    result = subprocess.run(  # noqa: S603 - fixed trusted administrator argv only
        argv,
        input=raw,
        capture_output=True,
        timeout=30,  # noqa: S603
        env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C"},
    )
    if result.returncode:
        raise RuntimeError("GITHUB_SETUP_COMMAND_FAILED")
    return result.stdout.strip()


def main():
    if os.geteuid() != 0:
        raise RuntimeError("ADMINISTRATOR_REQUIRED")
    raw = sys.stdin.buffer.read(65537)
    if not 1 <= len(raw) <= 65536:
        raise RuntimeError("GITHUB_SETUP_PAYLOAD_LIMIT")
    payload = json.loads(raw)
    if set(payload) != {"configuration", "private_key_base64"}:
        raise RuntimeError("GITHUB_SETUP_PAYLOAD_INVALID")
    config = payload["configuration"]
    if set(config) != {
        "client_id",
        "installation_id",
        "repository_id",
        "owner",
        "repository",
        "base",
        "path",
    } or (config["owner"], config["repository"], config["base"], config["path"]) != (
        "arslanabdulghaffar",
        "ProofFlow-Demo",
        "main",
        "pipeline.py",
    ):
        raise RuntimeError("GITHUB_SETUP_SCOPE_INVALID")
    pem = base64.b64decode(payload["private_key_base64"], validate=True)
    if not 512 <= len(pem) <= 32768 or not pem.startswith(
        (b"-----BEGIN RSA PRIVATE KEY-----", b"-----BEGIN PRIVATE KEY-----")
    ):
        raise RuntimeError("GITHUB_SETUP_KEY_INVALID")
    psql = [
        "/usr/bin/docker",
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
    ]
    ready = command(
        psql,
        b"SELECT NOT EXISTS(SELECT 1 FROM pf_product.execution_policy WHERE enabled) "
        b"AND NOT EXISTS(SELECT 1 FROM pf_product.jobs WHERE state NOT IN "
        b"('NEEDS_REVIEW','FAILED_INFRA','CANCELLED')) "
        b"AND NOT EXISTS(SELECT 1 FROM pf_product.repairs "
        b"WHERE state IN ('QUEUED','RUNNING','RECONCILING')) "
        b"AND NOT EXISTS(SELECT 1 FROM pf_product.pr_intents "
        b"WHERE state NOT IN ('COMPLETE','STOPPED','PREVIEW'));",
    )
    if ready != b"t":
        raise RuntimeError("GITHUB_SETUP_REQUIRES_CLOSED_IDLE")
    root = Path("/etc/proofflow-github")
    info = root.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != 10003
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise RuntimeError("GITHUB_SETUP_DIRECTORY_CHANGED")
    command(["/usr/bin/systemctl", "stop", "proofflow-product-dispatcher.service"])
    # No overwrite/rotation. A partial installation can only finish with identical bytes.
    for name, data in (
        ("private-key.pem", pem),
        ("configuration.json", json.dumps(config, sort_keys=True).encode()),
    ):
        path = root / name
        if path.exists() or path.is_symlink():
            info = path.lstat()
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != 10003
                or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != 0o400
                or info.st_size != len(data)
                or path.read_bytes() != data
            ):
                raise RuntimeError("GITHUB_EXISTING_SECRET_CHANGED")
            continue
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
        try:
            with os.fdopen(fd, "wb", closefd=False) as output:
                output.write(data)
                output.flush()
                os.fchown(fd, 10003, 10003)
                os.fchmod(fd, 0o400)
                os.fsync(fd)
        finally:
            os.close(fd)
    parent = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(parent)
    finally:
        os.close(parent)
    encoded = json.dumps(config, sort_keys=True).replace("'", "''")
    digest = command(
        psql,
        (
            "SET ROLE pf_product_provisioner; SELECT pf_product.configure_github('"
            + encoded
            + "'::jsonb,true);"
        ).encode(),
    ).decode()
    command(["/usr/bin/systemctl", "start", "proofflow-product-dispatcher.service"])
    print(
        json.dumps(
            {
                "configured": True,
                "configuration_sha256": digest,
                "repository": "arslanabdulghaffar/ProofFlow-Demo",
                "product_pr_approved": False,
                "new_cloud_resources": 0,
            }
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("GITHUB_SETUP_FAILED_RECONCILE_PARTIAL_STATE") from None
