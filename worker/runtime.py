"""Pinned runsc inside a systemd-owned cgroup and independent wall watchdog.

Only instantiated by trusted designated-worker composition. No Docker daemon,
user-selected runtime, fallback runtime, or candidate command executes on host.
"""

import hashlib
import json
import os
import re
import selectors
import signal
import stat
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from worker.host import HOST_ENV, command, synced_write
from worker.launcher import fixed_environment
from worker.log_capture import BoundedLogCapture
from worker.metrics import CgroupMetrics
from worker.protocol import ExecutionRequest, SupervisorError, execution_name
from worker.runtime_bundle import validate_bundle

WALL_SECONDS = 20
SYSTEMD_PROPERTIES = (
    "Type=exec", "Restart=no", "RemainAfterExit=no", "KillMode=control-group",
    "KillSignal=SIGKILL", "FinalKillSignal=SIGKILL", "SendSIGKILL=yes",
    "TimeoutStartSec=20s", "TimeoutStopSec=1s", "RuntimeMaxSec=20s",
    "CPUQuota=100%", "MemoryMax=805306368", "MemorySwapMax=0", "TasksMax=128",
    "OOMPolicy=kill", "NoNewPrivileges=yes", "PrivateNetwork=yes", "Delegate=no",
)
SHOW_PROPERTIES = ("LoadState", "ActiveState", "SubState", "MainPID", "ControlGroup",
                   "InvocationID", "Result", "ExecMainCode", "ExecMainStatus", "RuntimeMaxUSec",
                   "KillMode", "MemoryMax", "MemorySwapMax", "TasksMax", "Delegate",
                   "CPUQuotaPerSecUSec", "NoNewPrivileges", "PrivateNetwork", "Restart",
                   "KillSignal", "SendSIGKILL", "TimeoutStartUSec", "TimeoutStopUSec")


@dataclass(frozen=True)
class RuntimePolicy:
    machine_id: str
    runsc_sha256: str
    image_sha256: str
    rootfs: Path
    runsc: Path = Path("/usr/local/bin/runsc")
    rootfs_sha256: str = ""  # Required by deployment composition; empty never validates.
    runtime_bundle_sha256: str = ""

    def validate(self) -> None:
        if os.geteuid() != 0 or not re.fullmatch(r"[a-f0-9]{32}", self.machine_id):
            raise SupervisorError("DESIGNATED_WORKER_REQUIRED")
        if Path("/etc/machine-id").read_text().strip() != self.machine_id:
            raise SupervisorError("WRONG_WORKER_HOST")
        if any(not re.fullmatch(r"[a-f0-9]{64}", digest)
               for digest in (self.runsc_sha256, self.image_sha256, self.rootfs_sha256,
                              self.runtime_bundle_sha256)):
            raise SupervisorError("INVALID_RUNTIME_PIN")
        expected_rootfs = Path("/var/lib/proofflow-worker/images") / self.image_sha256 / "rootfs"
        if self.rootfs != expected_rootfs or self.runsc != Path("/usr/local/bin/runsc"):
            raise SupervisorError("UNAPPROVED_RUNTIME_PATH")
        validate_bundle(self.runtime_bundle_sha256, self.runsc_sha256)
        info = self.runsc.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1
                or info.st_mode & 0o022):
            raise SupervisorError("UNSAFE_RUNTIME_BINARY")
        with self.runsc.open("rb") as source:
            if hashlib.file_digest(source, "sha256").hexdigest() != self.runsc_sha256:
                raise SupervisorError("RUNTIME_DIGEST_MISMATCH")
        info = self.rootfs.lstat()
        if (not self.rootfs.is_absolute() or not stat.S_ISDIR(info.st_mode)
                or info.st_uid != 0 or info.st_mode & 0o022):
            raise SupervisorError("UNSAFE_RUNTIME_ROOTFS")
        from worker.rootfs import verify_mount
        verify_mount(self.rootfs.parent, self.image_sha256, self.rootfs_sha256)
        if not Path("/sys/fs/cgroup/cgroup.controllers").is_file():
            raise SupervisorError("CGROUP_V2_REQUIRED")


def oci_config(policy: RuntimePolicy, request: ExecutionRequest, path: Path) -> dict:
    environment = fixed_environment()
    return {
        "ociVersion": "1.0.2", "root": {"path": str(policy.rootfs), "readonly": True},
        "hostname": "proofflow-sandbox", "process": {
            "terminal": False, "user": {"uid": 10001, "gid": 10001, "additionalGids": []},
            "args": ["/usr/local/bin/python3", "-I", "-B", "/opt/proofflow/launcher.py"]
                    + (["--rollups"] if request.include_rollups else []),
            "env": [key + "=" + value for key, value in environment.items()],
            "cwd": "/scratch", "noNewPrivileges": True,
            "capabilities": {name: [] for name in ("bounding", "effective", "inheritable",
                                                   "permitted", "ambient")},
            "rlimits": [{"type": name, "hard": value, "soft": value}
                        for name, value in (("RLIMIT_NPROC", 64), ("RLIMIT_NOFILE", 64),
                                            ("RLIMIT_CORE", 0), ("RLIMIT_FSIZE", 67108864))],
        },
        "mounts": [
            {"destination": "/proc", "type": "proc", "source": "proc",
             "options": ["nosuid", "noexec", "nodev"]},
            {"destination": "/dev", "type": "tmpfs", "source": "tmpfs",
             "options": ["nosuid", "noexec", "mode=755", "size=65536", "nr_inodes=32"]},
            *[{"destination": destination, "type": "bind", "source": str(path / name),
               "options": ["bind", "ro" if name == "input" else "rw", "nosuid", "nodev", "noexec"]}
              for name, destination in (("input", "/input"), ("output", "/output"),
                                         ("scratch", "/scratch"),
                                         # Keep /tmp a real image directory: runsc resolves
                                         # symlinks before deciding whether /tmp is explicit.
                                         # All writable aliases share one host quota.
                                         ("scratch", "/tmp"),  # noqa: S108 - bounded guest mount
                                         ("scratch", "/dev/shm"))],  # noqa: S108 - bounded guest mount
        ],
        "linux": {"namespaces": [{"type": name} for name in
                                  ("pid", "network", "ipc", "uts", "mount")],
                  "maskedPaths": ["/proc/kcore", "/proc/keys", "/proc/timer_list", "/sys"],
                  "readonlyPaths": ["/proc/sys", "/proc/sysrq-trigger"]},
    }


class SystemdRunsc:
    def __init__(self, policy: RuntimePolicy):
        self.policy = policy

    def validate(self) -> None:
        self.policy.validate()

    def identity(self) -> dict:
        # Bind replay to the trusted implementation as well as the guest image/runtime.
        # Deployment must install these root-owned files immutably and restart on update.
        sources = {}
        for name in ("__init__", "runtime", "launcher", "host", "start_gate", "staging",
                     "collector", "protocol", "journal", "supervisor", "log_capture", "rootfs",
                     "wire", "service", "entrypoint", "metrics", "runtime_bundle"):
            source = Path(__file__).with_name(name + ".py")
            info = source.lstat()
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022
                    or info.st_nlink != 1):
                raise SupervisorError("UNSAFE_SUPERVISOR_INSTALL")
            sources[name] = hashlib.sha256(source.read_bytes()).hexdigest()
        return {"runtime": "runsc", "platform": "systrap",
                "runtime_sha256": self.policy.runsc_sha256,
                "runtime_bundle_sha256": self.policy.runtime_bundle_sha256,
                "image_sha256": self.policy.image_sha256,
                "rootfs_sha256": self.policy.rootfs_sha256,
                "supervisor_sha256": hashlib.sha256(
                    json.dumps(sources, sort_keys=True).encode()).hexdigest(),
                "host_tag": hashlib.sha256(self.policy.machine_id.encode()).hexdigest()}

    def _runtime_args(self, identifier: UUID, path: Path) -> list[str]:
        return [str(self.policy.runsc), "--root=" + str(path / "state"),
                "--platform=systrap", "--network=none", "--ignore-cgroups=true",
                "--allow-flag-override=false", "run", "--bundle=" + str(path),
                execution_name(identifier)]

    def write_config(self, request: ExecutionRequest, path: Path) -> None:
        synced_write(path / "config.json", json.dumps(oci_config(self.policy, request, path),
                                                     sort_keys=True).encode())

    def unit(self, identifier: UUID) -> str:
        return execution_name(identifier) + ".service"

    def show(self, identifier: UUID) -> dict[str, str]:
        text = command(["/usr/bin/systemctl", "show", self.unit(identifier),
                        "--property=" + ",".join(SHOW_PROPERTIES)], allow_failure=True)
        result = dict(line.split("=", 1) for line in text.splitlines() if "=" in line)
        if "LoadState" not in result or "ActiveState" not in result:
            raise SupervisorError("UNIT_STATE_UNAVAILABLE")
        return result

    def _start_args(self, identifier: UUID, path: Path) -> list[str]:
        gate = Path(__file__).with_name("start_gate.py").resolve()
        if any(not re.fullmatch(r"/[A-Za-z0-9_./-]+", str(item)) for item in (gate, path)):
            raise SupervisorError("UNSUPPORTED_HOST_INSTALL_PATH")
        return ["/usr/bin/systemd-run", "--quiet", "--no-ask-password", "--pipe", "--wait",
                "--expand-environment=no",
                "--setenv=GVISOR_SIDECAR_BINARIES_DIR=/usr/local/bin/gvisor-bin",
                "--unit=" + self.unit(identifier), "--slice=system.slice",
                *["--property=" + item for item in SYSTEMD_PROPERTIES],
                "--property=ExecStartPre=/usr/bin/python3 -I " + str(gate)
                + " " + str(path / "launch.ready"),
                "--", *self._runtime_args(identifier, path)]

    def execute(self, identifier: UUID, path: Path, cancelled) -> tuple[dict, tuple]:
        if cancelled():
            return {"outcome": "cancelled", "runtime_exit_code": None}, ()
        if self.show(identifier).get("LoadState") != "not-found":
            raise SupervisorError("EXECUTION_UNIT_ALREADY_EXISTS")
        process = subprocess.Popen(  # noqa: S603 - fixed systemd and pinned runsc arguments
            self._start_args(identifier, path), stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=HOST_ENV, start_new_session=True,
        )
        capture = BoundedLogCapture()
        deadline = time.monotonic() + WALL_SECONDS
        outcome = "exited"
        armed = False
        metrics = None
        sampled_at = 0.0
        try:
            with selectors.DefaultSelector() as selector:
                for name, pipe in (("stdout", process.stdout), ("stderr", process.stderr)):
                    os.set_blocking(pipe.fileno(), False)
                    selector.register(pipe, selectors.EVENT_READ, name)
                while selector.get_map():
                    if cancelled():
                        outcome = "cancelled"
                        break
                    if time.monotonic() >= deadline:
                        outcome = "timeout"
                        break
                    if not armed:
                        state = self.show(identifier)
                        if state.get("ActiveState") == "activating":
                            if (state.get("RuntimeMaxUSec") != "20s"
                                    or state.get("KillMode") != "control-group"
                                    or state.get("MemoryMax") != "805306368"
                                    or state.get("MemorySwapMax") != "0"
                                    or state.get("TasksMax") != "128"
                                    or state.get("Delegate") != "no"
                                    or state.get("CPUQuotaPerSecUSec") != "1s"
                                    or state.get("NoNewPrivileges") != "yes"
                                    or state.get("PrivateNetwork") != "yes"
                                    or state.get("Restart") != "no"
                                    or state.get("KillSignal") != "9"
                                    or state.get("SendSIGKILL") != "yes"
                                    or state.get("TimeoutStartUSec") != "20s"
                                    or state.get("TimeoutStopUSec") != "1s"):
                                raise SupervisorError("WATCHDOG_POLICY_MISMATCH")
                            metrics = CgroupMetrics(identifier)
                            synced_write(path / "launch.ready", identifier.hex.encode())
                            armed = True
                    if metrics is not None and time.monotonic() - sampled_at >= 0.1:
                        try:
                            metrics.sample()
                        except OSError:
                            pass  # Fast exit may remove the cgroup before the next sample.
                        sampled_at = time.monotonic()
                    for key, _ in selector.select(0.05):
                        chunk = os.read(key.fd, 4096)
                        if chunk:
                            capture.feed(key.data, chunk)
                        else:
                            selector.unregister(key.fileobj)
                self.stop_and_confirm(identifier)
                drain_deadline = time.monotonic() + 2
                while selector.get_map():
                    if time.monotonic() >= drain_deadline:
                        raise SupervisorError("LOG_DRAIN_UNCERTAIN")
                    for key, _ in selector.select(0.05):
                        chunk = os.read(key.fd, 4096)
                        if chunk:
                            capture.feed(key.data, chunk)
                        else:
                            selector.unregister(key.fileobj)
            try:
                client_code = process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                raise SupervisorError("RUNTIME_CLIENT_EXIT_UNCERTAIN") from None
            state = self.show(identifier)
            if state.get("Result") == "timeout":
                outcome = "timeout"
            if not armed and outcome == "exited":
                outcome = "infrastructure_failure"
            return {"outcome": outcome, "runtime_exit_code": state.get("ExecMainStatus"),
                    "runtime_client_exit_code": client_code,
                    "runtime_exit_kind": state.get("ExecMainCode"),
                    "unit_result": state.get("Result"), "invocation": state.get("InvocationID"),
                    "resource_observation": metrics.finish() if metrics else None}, \
                capture.snapshot()
        finally:
            # This is a second independent stop path for exceptions/caller cancellation.
            try:
                self.stop_and_confirm(identifier)
            finally:
                try:
                    if process.poll() is None:
                        try:
                            os.killpg(process.pid, signal.SIGKILL)  # Only our client group.
                        except ProcessLookupError:
                            pass  # Client exited between poll and signal.
                        try:
                            process.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            raise SupervisorError("RUNTIME_CLIENT_EXIT_UNCERTAIN") from None
                finally:
                    process.stdout.close()
                    process.stderr.close()
                    if metrics is not None:
                        metrics.close()

    def stop_and_confirm(self, identifier: UUID) -> dict:
        state = self.show(identifier)
        if state.get("LoadState") != "not-found":
            command(["/usr/bin/systemctl", "kill", "--kill-whom=all", "--signal=SIGKILL",
                     self.unit(identifier)], allow_failure=True)
            command(["/usr/bin/systemctl", "stop", self.unit(identifier)])
        # systemd may report stopped while SIGKILL recipients are still exiting.
        # Never collect until the kernel confirms zero writers; a bounded grace
        # period is for termination observation, not additional guest runtime.
        deadline = time.monotonic() + 2
        while True:
            try:
                return self.confirm_stopped(identifier)
            except SupervisorError as error:
                if (str(error) not in {"EXECUTION_WRITERS_REMAIN", "EXECUTION_WRITERS_UNCERTAIN"}
                        or time.monotonic() >= deadline):
                    raise
                time.sleep(0.02)

    def confirm_stopped(self, identifier: UUID) -> dict:
        state = self.show(identifier)
        if (state.get("ActiveState") not in ("inactive", "failed")
                or state.get("MainPID") not in (None, "0")):
            raise SupervisorError("EXECUTION_WRITERS_UNCERTAIN")
        expected = "/system.slice/" + self.unit(identifier)
        if state.get("ControlGroup") not in (None, "", expected):
            raise SupervisorError("UNEXPECTED_EXECUTION_CGROUP")
        path = Path("/sys/fs/cgroup" + expected)
        if path.exists():
            fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                events = os.open("cgroup.events", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
                try:
                    lines = os.read(events, 4096).decode().splitlines()
                    try:
                        fields = dict(line.split() for line in lines)
                    except ValueError:
                        raise SupervisorError("EXECUTION_WRITERS_UNCERTAIN") from None
                finally:
                    os.close(events)
                if fields.get("populated") != "0":
                    raise SupervisorError("EXECUTION_WRITERS_REMAIN")
            finally:
                os.close(fd)
        return {"unit": self.unit(identifier), "cgroup": expected,
                "kernel_writers": "absent_or_populated_zero", "state": state.get("ActiveState")}

    def delete_state(self, identifier: UUID, path: Path) -> None:
        state_path = path / "state" / execution_name(identifier)
        if state_path.exists():
            command([str(self.policy.runsc), "--root=" + str(path / "state"),
                     "delete", "--force", execution_name(identifier)])

    def forget(self, identifier: UUID) -> None:
        self.confirm_stopped(identifier)
        command(["/usr/bin/systemctl", "reset-failed", self.unit(identifier)], allow_failure=True)
