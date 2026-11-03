"""Designated-worker service composition; fixed configuration, no development fallback."""

import os
import signal
import stat
import sys
from pathlib import Path

# -I execution requires an explicit trusted installation path, never cwd/PYTHONPATH.
if __name__ == "__main__":
    if Path(__file__).resolve() != Path("/opt/proofflow-worker/worker/entrypoint.py"):
        raise SystemExit("UNAPPROVED_SERVICE_INSTALL")
    installation = Path("/opt/proofflow-worker/worker")
    if any(path.suffix != ".py" for path in installation.iterdir()):
        raise SystemExit("UNSAFE_SERVICE_INSTALL_CONTENTS")
    for path in [installation, *installation.parents, *installation.glob("*.py")]:
        info = path.lstat()
        if (info.st_uid != 0 or info.st_mode & 0o022
                or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode))):
            raise SystemExit("UNSAFE_SERVICE_INSTALL")
    sys.path.insert(0, "/opt/proofflow-worker")

from worker.journal import private_directory  # noqa: E402
from worker.protocol import SupervisorError  # noqa: E402
from worker.rootfs import mount_image  # noqa: E402
from worker.runtime import RuntimePolicy, SystemdRunsc  # noqa: E402
from worker.service import WorkerServer, WorkerService  # noqa: E402
from worker.supervisor import Supervisor  # noqa: E402
from worker.wire import digest, keys, private_address, strict_json, tls_context  # noqa: E402


def protected_file(path: Path, *, secret: bool = False) -> None:
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1
            or info.st_mode & (0o077 if secret else 0o022) or info.st_size > 65536):
        raise SupervisorError("UNSAFE_SERVICE_CONFIGURATION")
    for parent in path.parents:
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise SupervisorError("UNSAFE_SERVICE_CONFIGURATION")


def main() -> None:
    if os.geteuid() != 0:
        raise SupervisorError("DESIGNATED_WORKER_REQUIRED")
    config_path = Path("/etc/proofflow-worker/service.json")
    protected_file(config_path, secret=True)
    config = strict_json(config_path.read_bytes())
    keys(config, {"machine_id", "runsc_sha256", "image_sha256", "rootfs_sha256",
                  "bind_address", "controller_certificate_sha256", "runtime_bundle_sha256"})
    if config["machine_id"] != Path("/etc/machine-id").read_text().strip():
        raise SupervisorError("WRONG_WORKER_HOST")
    address = private_address(config["bind_address"])
    image, rootfs = digest(config["image_sha256"]), digest(config["rootfs_sha256"])
    private_directory(Path("/var/lib/proofflow-worker"))
    private_directory(Path("/var/lib/proofflow-worker/images"))
    directory = Path("/var/lib/proofflow-worker/images") / image
    certs = Path("/etc/proofflow-worker/tls")
    for name in ("ca.pem", "worker.pem", "worker.key"):
        protected_file(certs / name, secret=name.endswith(".key"))
    context = tls_context(certs / "ca.pem", certs / "worker.pem", certs / "worker.key", server=True)
    mount_image(directory, image, rootfs)
    policy = RuntimePolicy(config["machine_id"], digest(config["runsc_sha256"]), image,
                           directory / "rootfs", rootfs_sha256=rootfs,
                           runtime_bundle_sha256=digest(config["runtime_bundle_sha256"]))
    runtime = SystemdRunsc(policy)
    runtime.validate()
    runtime.identity()  # Reject unsafe code installation before binding any socket.
    state = Path("/var/lib/proofflow-worker/state")
    state.mkdir(mode=0o700, exist_ok=True)
    supervisor = Supervisor(state, runtime)
    server = None
    try:
        supervisor.recover()
        server = WorkerServer((address, 9443), context,
                              digest(config["controller_certificate_sha256"]),
                              WorkerService(supervisor))
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_: server.stop.set())
        server.serve()
    finally:
        supervisor.pause_admission()
        if server:
            server.stop.set()
            server.drain()
        supervisor.close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("WORKER_SERVICE_START_OR_SHUTDOWN_FAILED") from None
