"""Reviewed root installation on the existing control host; no resource provisioning."""

import hashlib
import json
import os
import stat
from datetime import UTC, datetime
from pathlib import Path

from install_product_services import (
    DOCKER,
    IMAGE,
    PREVIOUS,
    command,
    directory,
    expected_mounts,
    write,
)
from judging_guard import allowed
from public_api_policy import PUBLIC_MOUNTS, validate_public_container


def reviewed_replace(path, raw, mode=0o600):
    path = Path(path)
    if path.exists():
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1:
            raise RuntimeError("JUDGING_INSTALL_TARGET_UNSAFE")
        old = path.read_bytes()
        if old == raw:
            return
        archive = Path(__file__).resolve().parent / (
            "prior-" + path.name + "-" + hashlib.sha256(old).hexdigest()
        )
        if not archive.exists():
            write(archive, old)
    pending = path.with_name(path.name + ".judging-stage")
    fd = os.open(pending, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, "wb") as stream:
        os.fchmod(stream.fileno(), mode)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(pending, path)
    parent = os.open(path.parent, os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(parent)
    finally:
        os.close(parent)


def main():
    if os.geteuid() != 0:
        raise RuntimeError("ROOT_REQUIRED")
    here = Path(__file__).resolve().parent
    config = json.loads((here / "judging.json").read_bytes())
    if not allowed(
        config, datetime.now(UTC), Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    ):
        raise RuntimeError("FUNDED_WINDOW_INVALID")
    # Existing services must be upgraded while admission is closed and idle.
    from guest_demo_guard import sql

    if sql("proofflow_product", "SELECT NOT enabled FROM pf_product.execution_policy;") != b"t":
        raise RuntimeError("CLOSED_ADMISSION_REQUIRED")
    name = "proofflow-public-api"
    old = json.loads(command([*DOCKER, "inspect", name]))[0]
    image = json.loads(command([*DOCKER, "image", "inspect", "sha256:" + IMAGE]))[0]
    if old["Image"] != "sha256:" + IMAGE:
        if (
            old["Image"] != "sha256:" + PREVIOUS
            or old["Config"]["Labels"].get("proofflow.role") != "product-public-api"
        ):
            raise RuntimeError("PUBLIC_PREDECESSOR_CHANGED")
        archived = name + "-previous-" + PREVIOUS[:12]
        if command([*DOCKER, "ps", "-aq", "--filter=name=^/" + archived + "$"]):
            raise RuntimeError("PUBLIC_ARCHIVE_EXISTS_RECONCILE")
        command(["/usr/bin/systemctl", "stop", name + ".service"])
        command([*DOCKER, "rename", name, archived])
        args = [
            *DOCKER,
            "create",
            "--pull=never",
            "--name=" + name,
            "--label=proofflow.role=product-public-api",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--user=10003:10003",
            "--group-add=10001",
            "--memory=384m",
            "--memory-swap=384m",
            "--cpus=1",
            "--pids-limit=64",
            "--ulimit=core=0",
            "--ulimit=nofile=128:128",
            "--network=none",
        ]
        for destination, (source, writable) in (expected_mounts("api") | PUBLIC_MOUNTS).items():
            args.append(
                "--mount=type=bind,src="
                + source
                + ",dst="
                + destination
                + ("" if writable else ",readonly")
            )
        command(args + ["sha256:" + IMAGE, "python", "-m", "api.app.product_bootstrap"])
    validate_public_container(
        json.loads(command([*DOCKER, "inspect", name]))[0], image["Config"]["Env"]
    )
    command(["/usr/bin/systemctl", "start", name + ".service"])
    directory("/etc/proofflow-judging")
    target = Path("/etc/proofflow-judging/config.json")
    if target.exists():
        previous = json.loads(target.read_bytes())
        if previous.get("enabled") is not False:
            raise RuntimeError("JUDGING_CONFIG_REQUIRES_CLOSED_REVIEW")

        archive = target.with_name(
            "config-" + hashlib.sha256(target.read_bytes()).hexdigest() + ".json"
        )
        if not archive.exists():
            write(archive, target.read_bytes())
    reviewed_replace(target, json.dumps(config | {"enabled": False}).encode())
    service = f"""[Unit]
Description=ProofFlow bounded judging admission guard
After=docker.service proofflow-product-dispatcher.service
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 {here}/judging_guard.py
TimeoutStartSec=55
UMask=0077
NoNewPrivileges=yes
PrivateTmp=yes
ProtectHome=yes
MemoryMax=128M
TasksMax=32
LimitCORE=0
"""
    reviewed_replace("/etc/systemd/system/proofflow-judging.service", service.encode(), mode=0o644)
    timer = b"""[Unit]
Description=ProofFlow judging guard every minute
[Timer]
OnBootSec=60
OnUnitActiveSec=60
AccuracySec=5
[Install]
WantedBy=timers.target
"""
    reviewed_replace("/etc/systemd/system/proofflow-judging.timer", timer, mode=0o644)
    command(["/usr/bin/systemctl", "daemon-reload"])
    # Explicit deployment activation follows testing; installation stays closed.
    print(
        json.dumps(
            {"installed": True, "image": IMAGE, "admission": "closed", "revision": str(here)}
        )
    )


if __name__ == "__main__":
    main()
