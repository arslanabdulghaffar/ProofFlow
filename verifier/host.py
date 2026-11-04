"""Root-only fixed verifier launcher, never a candidate execution interface.

One service slot serializes admission. systemd owns the watchdog even if this
controller dies. Recovery stops the old slot before removing bounded scratch.
No request field can change the executable, image, properties or host paths.
"""

import fcntl
import os
import stat
import time
from pathlib import Path

from contracts.codec import InputError, parse_object
from verifier.protocol import MAX_REQUEST, MAX_RESPONSE, VERSION, sha
from worker.host import command, sync_directory, synced_write
from worker.protocol import SupervisorError
from worker.rootfs import regular_hash

UNIT = "proofflow-verifier.service"
DIRECTORY = Path("/var/lib/proofflow-verifier")
PROPERTIES = {
    "Description": "ProofFlow fixed trusted verifier v1",
    "Type": "exec", "RemainAfterExit": "yes", "User": "10002", "Group": "10002",
    "PrivateNetwork": "yes", "PrivateDevices": "yes", "NoNewPrivileges": "yes",
    "CapabilityBoundingSet": "", "AmbientCapabilities": "", "ProtectSystem": "strict",
    "ProtectHome": "yes", "ProtectKernelTunables": "yes", "ProtectKernelModules": "yes",
    "ProtectControlGroups": "yes", "ProtectKernelLogs": "yes", "RestrictNamespaces": "yes",
    "RestrictSUIDSGID": "yes", "LockPersonality": "yes", "MemoryDenyWriteExecute": "yes",
    "SystemCallArchitectures": "native", "RestrictAddressFamilies": "AF_UNIX",
    "SystemCallFilter": "~@network-io @mount @privileged @resources",
    "SystemCallErrorNumber": "EPERM",
    "UMask": "0077", "MemoryMax": "536870912", "MemorySwapMax": "0",
    "CPUQuota": "100%", "TasksMax": "32", "LimitNOFILE": "64",
    "LimitFSIZE": str(MAX_RESPONSE), "LimitCORE": "0", "RuntimeMaxSec": "10s",
    "TimeoutStartSec": "5s", "TimeoutStopSec": "1s", "KillMode": "control-group",
    "SendSIGKILL": "yes", "StandardError": "null", "OOMPolicy": "kill",
}


def _state():
    wanted = ["LoadState", "ActiveState", "SubState", "Result", "ExecMainStatus", "ExecMainCode",
              "ControlGroup", "Description", "MainPID"]
    raw = command(["/usr/bin/systemctl", "show", UNIT, "--property=" + ",".join(wanted)])
    return dict(line.split("=", 1) for line in raw.splitlines() if "=" in line)


def _stop():
    state = _state()
    if state.get("LoadState") == "not-found":
        return
    if state.get("Description") != PROPERTIES["Description"]:
        raise SupervisorError("VERIFIER_UNIT_IDENTITY_CHANGED")
    group = state.get("ControlGroup", "")
    command(["/usr/bin/systemctl", "stop", UNIT], timeout=6)
    if group:
        if group != "/system.slice/" + UNIT:
            raise SupervisorError("VERIFIER_CGROUP_CHANGED")
        events = Path("/sys/fs/cgroup" + group) / "cgroup.events"
        if events.exists() and "populated 1" in events.read_text():
            raise SupervisorError("VERIFIER_CLEANUP_UNCERTAIN")
    command(["/usr/bin/systemctl", "reset-failed", UNIT], allow_failure=True)
    final = _state()
    if final.get("ActiveState") not in ("inactive", "failed") or final.get("MainPID") != "0":
        raise SupervisorError("VERIFIER_CLEANUP_UNCERTAIN")


def _private(path):
    info = path.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != 0
            or stat.S_IMODE(info.st_mode) != 0o700):
        raise SupervisorError("VERIFIER_PRIVATE_DIRECTORY_REQUIRED")


def properties(image: Path) -> dict[str, str]:
    """Administrative plan, not caller data. Paths cannot contain systemd specifiers."""
    if (not image.is_absolute() or any(char in str(image) for char in "%\n\r\x00 ")
            or ".." in image.parts):
        raise SupervisorError("VERIFIER_IMAGE_PATH_INVALID")
    return {**PROPERTIES, "RootImage": str(image), "RootImageOptions": "root:ro",
            "WorkingDirectory": "/opt/proofflow", "Environment": "LANG=C LC_ALL=C",
            "StandardInput": "file:" + str(DIRECTORY / "request"),
            "StandardOutput": "file:" + str(DIRECTORY / "response")}


def run(raw: bytes, *, image: Path, image_sha256: str) -> dict:
    if os.geteuid() != 0 or type(raw) is not bytes or not 1 <= len(raw) <= MAX_REQUEST:
        raise SupervisorError("VERIFIER_ADMIN_REQUEST_INVALID")
    plan = properties(image)
    # Every parent must be root-owned and not writable by other users.
    for parent in image.parents:
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise SupervisorError("VERIFIER_IMAGE_PARENT_INVALID")
    if regular_hash(image) != image_sha256:
        raise SupervisorError("VERIFIER_IMAGE_CHANGED")
    DIRECTORY.mkdir(mode=0o700, exist_ok=True)
    _private(DIRECTORY)
    fd = os.open(DIRECTORY / "lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1:
            raise SupervisorError("VERIFIER_LOCK_INVALID")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SupervisorError("VERIFIER_BUSY") from None
        _stop()  # Includes recovery after a previous controller crashed.
        for name in ("request", "response"):
            path = DIRECTORY / name
            if path.exists() or path.is_symlink():
                info = path.lstat()
                if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1:
                    raise SupervisorError("VERIFIER_SCRATCH_CHANGED")
                path.unlink()
        synced_write(DIRECTORY / "request", raw)
        synced_write(DIRECTORY / "response", b"")
        sync_directory(DIRECTORY)
        started = time.monotonic()
        try:
            command(["/usr/bin/systemd-run", "--quiet", "--unit=" + UNIT,
                     *["--property=" + key + "=" + value for key, value in plan.items()],
                     "/usr/local/bin/python3", "-I", "-B", "/opt/proofflow/verifier_main.py"],
                    timeout=8)
            while True:
                state = _state()
                if state.get("SubState") in ("exited", "failed", "dead"):
                    break
                if time.monotonic() - started > 17:
                    raise SupervisorError("VERIFIER_WATCHDOG_UNCERTAIN")
                time.sleep(0.05)
            if (state.get("Result") != "success" or state.get("ExecMainCode") != "1"
                    or state.get("ExecMainStatus") != "0" or state.get("SubState") != "exited"):
                raise SupervisorError("VERIFIER_PROCESS_FAILED")
            _stop()
            response = DIRECTORY / "response"
            regular_hash(response)
            if response.stat().st_size > MAX_RESPONSE:
                raise SupervisorError("VERIFIER_RESPONSE_LIMIT")
            raw_report = response.read_bytes()
            report = parse_object(raw_report, max_bytes=MAX_RESPONSE)
            if (report.get("version") != VERSION or report.get("request_sha256") != sha(raw)
                    or report.get("status") not in ("processed", "rejected")):
                raise SupervisorError("VERIFIER_REPORT_BINDING_INVALID")
            return {"report": report, "report_sha256": sha(raw_report),
                    "rootfs_sha256": image_sha256, "cleanup_confirmed": True}
        except InputError:
            raise SupervisorError("VERIFIER_RESPONSE_INVALID") from None
        finally:
            _stop()
            for name in ("request", "response"):
                (DIRECTORY / name).unlink(missing_ok=True)
            sync_directory(DIRECTORY)
    finally:
        os.close(fd)
