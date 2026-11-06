"""Bounded data-only off-VM recovery. Plaintext assets exist only in container tmpfs.

Trusted source-only mounts; backup/key/current authority go over stdin, never argv.
Even if this Windows coordinator dies, the container's own timeout kills recovery.
No uploaded bytes are imported or executed; the pinned image executes our helper only.
"""

import hashlib
import json
import subprocess
from uuid import uuid4

from check_product_image import IMAGE
from vultr_phase1 import ROOT

SOURCES = ("orchestrator/__init__.py", "orchestrator/asset_backup.py",
           "orchestrator/asset_recovery.py", "orchestrator/restore_guard.py",
           "scripts/restore_asset_fixture.py")
WSL = ["C:/Windows/System32/wsl.exe", "-d", "Ubuntu-24.04", "--"]


def validate_tree(target):
    if target.is_symlink() or (target.exists() and not target.is_dir()):
        raise RuntimeError("RECOVERY_SOURCE_CHANGED")
    for path in target.rglob("*"):
        relative = path.relative_to(target).as_posix()
        if (path.is_symlink() or (path.is_file() and relative not in SOURCES)
                or (path.is_dir() and relative not in {"scripts", "orchestrator"})):
            raise RuntimeError("RECOVERY_SOURCE_INVENTORY_CHANGED")


def source_tree():
    values = {name: (ROOT / name).read_bytes() for name in SOURCES}
    identity = hashlib.sha256(json.dumps(
        {n: hashlib.sha256(raw).hexdigest() for n, raw in values.items()}, sort_keys=True
    ).encode()).hexdigest()
    target = ROOT / ".tools" / ("recovery-source-" + identity)
    validate_tree(target)
    for name, raw in values.items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            with path.open("xb") as output:
                output.write(raw)
        if path.is_symlink() or path.read_bytes() != raw:
            raise RuntimeError("RECOVERY_SOURCE_CHANGED")
    validate_tree(target)
    reply = subprocess.run(  # noqa: S603 - fixed WSL path conversion
        [*WSL, "wslpath", "-a", target.as_posix()], capture_output=True, check=True, timeout=10
    )
    return reply.stdout.decode().strip(), identity


def command(*, fixture_hold=False):
    source, digest = source_tree()
    name = "proofflow-inert-recovery-" + uuid4().hex
    args = [*WSL, "docker", "run", "--rm", "--pull=never", "--name=" + name,
            "--network=none", "--read-only", "--cap-drop=ALL",
            "--security-opt=no-new-privileges", "--memory=512m", "--memory-swap=512m",
            "--cpus=1", "--pids-limit=16", "--user=10003:10003", "--ulimit=nofile=64:64",
            "--ulimit=core=0:0",
            "--tmpfs=/run/proofflow-recovery:rw,noexec,nosuid,nodev,size=67108864,"
            "mode=0700,uid=10003,gid=10003",
            "--mount=type=bind,source=" + source + ",destination=/trusted,readonly",
            "--entrypoint=/usr/bin/timeout", "--interactive"]
    if fixture_hold:
        # Trusted fault test only; a backup cannot set this environment variable.
        args.append("--env=PROOFFLOW_INERT_RECOVERY_HOLD=1")
    args += ["sha256:" + IMAGE, "--signal=KILL", "20s", "python", "-I", "-B", "-c",
             "import sys;sys.path.insert(0,'/app');sys.path.insert(0,'/trusted');"
             "from scripts.restore_asset_fixture import main;main()"]
    return args, name, digest


def absent(name):
    result = subprocess.run(  # noqa: S603 - generated exact name, no runtime credentials
        [*WSL, "docker", "container", "ls", "-aq", "--filter=name=^/" + name + "$"],
        capture_output=True, timeout=10
    )
    if result.returncode:
        raise RuntimeError("RECOVERY_CONTAINER_STATE_UNKNOWN")
    return not result.stdout.strip()


def run(raw):
    if type(raw) is not bytes or len(raw) > 96 * 1024 * 1024:
        raise RuntimeError("RECOVERY_INPUT_LIMIT")
    args, name, digest = command()
    try:
        result = subprocess.run(  # noqa: S603 - fixed trusted recovery only; secrets via stdin
            args, input=raw, capture_output=True, timeout=35
        )
        if result.returncode:
            raise RuntimeError("OFFVM_ASSET_MATERIALIZATION_FAILED")
        if not absent(name):
            raise RuntimeError("RECOVERY_CONTAINER_CLEANUP_UNCONFIRMED")
        receipt = json.loads(result.stdout)
        return {**receipt, "recovery_image": IMAGE, "recovery_sources": digest,
                "plaintext_storage": "container_tmpfs", "container_cleanup": "confirmed"}
    finally:
        if not absent(name):
            # Scoped cleanup of this newly created ephemeral container only.
            result = subprocess.run(  # noqa: S603 - generated exact owned container
                [*WSL, "docker", "rm", "-f", name], capture_output=True, timeout=10
            )
            if result.returncode or not absent(name):
                raise RuntimeError("RECOVERY_CONTAINER_CLEANUP_UNCONFIRMED")
