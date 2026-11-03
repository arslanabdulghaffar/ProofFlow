"""Trusted offline image import and read-only mount verification. Never starts an image."""

import hashlib
import json
import os
import re
import stat
import subprocess
import tarfile
from pathlib import Path, PurePosixPath
from uuid import uuid4

from worker.host import HOST_ENV, command, sync_directory, synced_write
from worker.journal import private_directory
from worker.protocol import SupervisorError
from worker.staging import mount_inventory
from worker.wire import digest, keys, strict_json

MAX_IMAGE = 1024 * 1024 * 1024
DOCKER = ["/usr/bin/docker", "--host=unix:///var/run/docker.sock"]


def regular_hash(path: Path) -> str:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as source:
        before = os.fstat(source.fileno())
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_uid != 0 or before.st_mode & 0o022
                or not 0 < before.st_size <= MAX_IMAGE):
            raise SupervisorError("UNSAFE_IMAGE_FILE")
        result = hashlib.file_digest(source, "sha256").hexdigest()
        after = os.fstat(source.fileno())
        def identity(s):
            return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns
        if identity(before) != identity(after):
            raise SupervisorError("IMAGE_CHANGED_DURING_READ")
        return result


def inspect_tar(path: Path) -> dict:
    """Validate a pinned Docker export without extracting any path onto the host."""
    if path.stat().st_size > MAX_IMAGE:
        raise SupervisorError("IMAGE_ARCHIVE_LIMIT")
    entries = {}
    size = 0
    with tarfile.open(path, "r:") as archive:
        for member in archive:
            name = member.name.rstrip("/")
            parts = PurePosixPath(name).parts
            if (not parts or name.startswith("/") or ".." in parts or "." in parts
                    or "\\" in name or str(PurePosixPath(name)) != name
                    or len(name) > 4096 or any(ord(c) < 32 for c in name)
                    or name in entries or len(entries) >= 50000 or member.issparse()
                    or (member.mode & 0o6000 and not member.isdir())
                    or not (member.isfile() or member.isdir() or member.issym() or member.islnk())):
                raise SupervisorError("UNSAFE_IMAGE_ARCHIVE")
            size += member.size
            if size > MAX_IMAGE:
                raise SupervisorError("IMAGE_ARCHIVE_LIMIT")
            entries[name] = member
        # No entry may traverse a link or regular file. Symlink text is guest data,
        # never followed by the importer. Hardlinks must point directly to a file.
        for name, member in entries.items():
            for parent in PurePosixPath(name).parents:
                item = entries.get(str(parent))
                if item and not item.isdir():
                    raise SupervisorError("IMAGE_LINK_TRAVERSAL")
            if member.islnk():
                target = entries.get(member.linkname)
                if not target or not target.isfile():
                    raise SupervisorError("UNSAFE_IMAGE_HARDLINK")
    return {"entries": len(entries), "declared_bytes": size}


def build_image(image_id: str, destination: Path) -> dict:
    """Administrator-only build on a trusted Linux build host, including development."""
    image = digest(image_id)
    if os.geteuid() != 0 or not destination.is_absolute():
        raise SupervisorError("TRUSTED_LINUX_BUILD_HOST_REQUIRED")
    destination.mkdir(mode=0o700)  # Refuse reuse/overwrite, including failed partial imports.
    private_directory(destination)
    metadata = json.loads(command([*DOCKER, "image", "inspect", "sha256:" + image]))[0]
    if (metadata["Id"] != "sha256:" + image or metadata["Os"] != "linux"
            or metadata["Architecture"] != "amd64" or metadata["Config"].get("Volumes")):
        raise SupervisorError("UNAPPROVED_IMAGE_CONFIG")
    name = "proofflow-import-" + uuid4().hex
    cid = None
    archive, blob = destination / "export.tar", destination / "rootfs.squashfs"
    try:
        cid = command([*DOCKER, "create", "--pull=never", "--name=" + name,
                       "--label=proofflow.purpose=offline-image-import", "--network=none",
                       "--hostname=proofflow-sandbox", "--entrypoint=/bin/false",
                       "sha256:" + image]).strip()
        if not re.fullmatch("[0-9a-f]{64}", cid):
            raise SupervisorError("IMPORT_CONTAINER_ID_UNCERTAIN")
        command([*DOCKER, "export", "--output=" + str(archive), cid], timeout=120)
        os.chmod(archive, 0o600)
        state = json.loads(command([*DOCKER, "inspect", cid]))[0]
        if (state["State"]["Status"] != "created" or state["State"]["Pid"] != 0
                or state["Image"] != "sha256:" + image):
            raise SupervisorError("IMAGE_IMPORT_STATE_CHANGED")
        inventory = inspect_tar(archive)
        archive_hash = regular_hash(archive)
        with archive.open("rb") as source:
            result = subprocess.run(  # noqa: S603 - fixed trusted builder; no archive extraction
                ["/usr/bin/mksquashfs", "-", str(blob), "-tar", "-noappend", "-no-xattrs",
                 "-processors", "2", "-mem", "256M", "-mkfs-time", "0", "-root-mode", "755",
                 "-exit-on-error", "-no-progress", "-quiet"], stdin=source,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=HOST_ENV, timeout=120,
            )
        if result.returncode:
            raise SupervisorError("IMAGE_CONVERSION_FAILED")
        os.chmod(blob, 0o400)
        with blob.open("rb") as source:
            os.fsync(source.fileno())
        receipt = {"version": 1, "docker_image_sha256": image,
                   "export_sha256": archive_hash, "rootfs_sha256": regular_hash(blob),
                   "builder_sha256": regular_hash(Path("/usr/bin/mksquashfs")),
                   "inventory": inventory, "image_started": False}
        synced_write(destination / "import.json", json.dumps(receipt, sort_keys=True).encode())
        archive.unlink()
        sync_directory(destination)
        sync_directory(destination.parent)
        return receipt
    finally:
        if cid and re.fullmatch("[0-9a-f]{64}", cid):
            # No force: a surprising started container must not be silently killed.
            command([*DOCKER, "rm", cid])
            remaining = command([*DOCKER, "ps", "-aq", "--filter=id=" + cid]).strip()
            if remaining:
                raise SupervisorError("IMPORT_CONTAINER_CLEANUP_UNCERTAIN")


def validate_import(directory: Path, image: str, rootfs: str) -> None:
    digest(image)
    digest(rootfs)
    private_directory(directory)
    receipt_path = directory / "import.json"
    regular_hash(receipt_path)
    if receipt_path.stat().st_size > 4096:
        raise SupervisorError("IMPORT_RECEIPT_LIMIT")
    receipt = strict_json(receipt_path.read_bytes())
    keys(receipt, {"version", "docker_image_sha256", "export_sha256", "rootfs_sha256",
                   "builder_sha256", "inventory", "image_started"})
    if (type(receipt["version"]) is not int or receipt["version"] != 1
            or receipt["image_started"] is not False or receipt["docker_image_sha256"] != image
            or receipt["rootfs_sha256"] != rootfs
            or regular_hash(directory / "rootfs.squashfs") != rootfs):
        raise SupervisorError("ROOTFS_IDENTITY_MISMATCH")


def verify_mount(directory: Path, image: str, rootfs: str) -> None:
    validate_import(directory, image, rootfs)
    mount = mount_inventory().get(str(directory / "rootfs"))
    if (not mount or mount[0] != "squashfs" or not {"ro", "nodev", "nosuid"} <= mount[2]
            or not re.fullmatch(r"/dev/loop[0-9]+", mount[1])):
        raise SupervisorError("IMMUTABLE_ROOTFS_MOUNT_REQUIRED")
    loop = Path("/sys/block") / Path(mount[1]).name
    backing = (loop / "loop/backing_file").read_text().strip()
    if ((loop / "ro").read_text().strip() != "1"
            or backing != str(directory / "rootfs.squashfs")):
        raise SupervisorError("ROOTFS_BACKING_FILE_MISMATCH")


def mount_image(directory: Path, image: str, rootfs: str) -> None:
    validate_import(directory, image, rootfs)
    target = directory / "rootfs"
    if str(target) not in mount_inventory():
        target.mkdir(mode=0o700, exist_ok=True)
        private_directory(target)
        if list(target.iterdir()):
            raise SupervisorError("ROOTFS_MOUNTPOINT_NOT_EMPTY")
        command(["/usr/bin/mount", "-t", "squashfs", "-o", "loop,ro,nodev,nosuid",
                 str(directory / "rootfs.squashfs"), str(target)])
    verify_mount(directory, image, rootfs)
