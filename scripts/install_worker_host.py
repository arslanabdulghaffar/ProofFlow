"""Trusted administrator installer, only on the designated empty worker VM.

This is deployment code, never a candidate tool. The archive comes over pinned
administrator SSH and contains only pre-reviewed regular files and a manifest.
Guest rootfs content remains inside its immutable SquashFS, never host-extracted.
"""

import hashlib
import json
import os
import re
import stat
import subprocess
import tarfile
from pathlib import Path, PurePosixPath

BUNDLE = Path("/var/lib/proofflow-setup/worker-install.tar.gz")
RECEIPT = Path("/var/lib/proofflow-setup/worker-install.json")


def directory(path: Path, mode: int):
    path.mkdir(mode=mode, parents=True, exist_ok=True)
    for parent in (path, *path.parents):
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise RuntimeError("UNSAFE_INSTALL_DIRECTORY")
    os.chmod(path, mode)


def main():
    if os.geteuid() != 0 or not Path("/var/lib/proofflow-setup/cloud-init-ready").is_file():
        raise RuntimeError("DESIGNATED_BOOTSTRAPPED_WORKER_REQUIRED")
    os.umask(0o077)
    with tarfile.open(BUNDLE, "r:gz") as archive:
        members = archive.getmembers()
        names = [m.name for m in members]
        if len(names) != len(set(names)) or any(not m.isfile() for m in members):
            raise RuntimeError("INSTALL_ARCHIVE_NOT_REGULAR_UNIQUE")
        if sum(m.size for m in members) > 400 * 1024 * 1024:
            raise RuntimeError("INSTALL_ARCHIVE_TOO_LARGE")
        manifest = json.load(archive.extractfile("manifest.json"))
        if manifest["machine_id"] != Path("/etc/machine-id").read_text().strip():
            raise RuntimeError("WRONG_WORKER_HOST")
        if set(manifest["files"]) | {"manifest.json"} != set(names):
            raise RuntimeError("INSTALL_ARCHIVE_MANIFEST_MISMATCH")
        if RECEIPT.exists():
            old = json.loads(RECEIPT.read_text())
            if old != manifest:
                raise RuntimeError("EXISTING_INSTALL_REQUIRES_REVIEWED_UPDATE")
        for member in members:
            if member.name == "manifest.json":
                continue
            entry = manifest["files"][member.name]
            target = Path(entry["destination"])
            # Only this fixed, reviewed worker installation namespace is writable.
            prefixes = ("/opt/proofflow-worker/worker/", "/var/lib/proofflow-worker/images/",
                        "/etc/proofflow-worker/", "/usr/local/bin/gvisor-bin/")
            exact = {"/usr/local/bin/runsc", "/usr/local/bin/containerd-shim-runsc-v1",
                     "/etc/systemd/system/proofflow-worker.service"}
            if (str(target) not in exact and not str(target).startswith(prefixes)) or (
                    ".." in PurePosixPath(str(target)).parts or not target.is_absolute()):
                raise RuntimeError("UNAPPROVED_INSTALL_PATH")
            if not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]):
                raise RuntimeError("INVALID_INSTALL_DIGEST")
            if entry["mode"] not in (0o400, 0o600, 0o644, 0o755):
                raise RuntimeError("INVALID_INSTALL_MODE")
            directory(target.parent, 0o755 if str(target).startswith(
                ("/usr/local/", "/opt/", "/etc/systemd/")) else 0o700)
            if target.exists() or target.is_symlink():
                info = target.lstat()
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != 0:
                    raise RuntimeError("UNSAFE_EXISTING_INSTALL_FILE")
            temporary = target.with_name(target.name + ".install-pending")
            source = archive.extractfile(member)
            digest = hashlib.sha256()
            size = 0
            with temporary.open("xb") as output:
                while chunk := source.read(1024 * 1024):
                    size += len(chunk)
                    digest.update(chunk)
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            if digest.hexdigest() != entry["sha256"] or size != member.size:
                raise RuntimeError("INSTALL_DIGEST_MISMATCH")
            os.chmod(temporary, entry["mode"])
            os.replace(temporary, target)
        RECEIPT.write_text(json.dumps(manifest, sort_keys=True))
    subprocess.run(["/usr/bin/systemctl", "daemon-reload"], check=True, timeout=20)  # noqa: S603
    subprocess.run(["/usr/bin/systemctl", "enable", "--now", "proofflow-worker.service"],
                   check=True, timeout=30, capture_output=True)  # noqa: S603
    print(json.dumps({"installed": True, "files": len(manifest["files"]),
                      "acceptance": "NOT_RUN"}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("WORKER_INSTALL_FAILED_REQUIRES_DIAGNOSIS") from None
