"""Linux-only private immutable byte store. A digest is NOT download permission.

The caller provides an administrator-opened directory descriptor and performs
workspace registry authorization before reads. This primitive has no API route,
candidate path, archive extraction, code execution, retention policy or DB commit.
"""

import hashlib
import os
import re
import secrets
import stat
import sys
from contextlib import contextmanager

MAX_ASSET_BYTES = 10 * 1024 * 1024
CHUNK_BYTES = 64 * 1024
DIGEST = re.compile(r"[0-9a-f]{64}", re.ASCII)


class AssetError(Exception):
    """Fixed diagnostics, never private paths or uploaded contents."""


@contextmanager
def _directory(directory_fd: int, *, write: bool):
    if sys.platform != "linux":
        raise AssetError("ASSET_PLATFORM_UNSUPPORTED")
    if type(directory_fd) is not int or directory_fd < 0:
        raise AssetError("ASSET_DIRECTORY_INVALID")
    import fcntl

    root = None
    try:
        # A new open description is essential: flock on dup() would share locks
        # among callers using the same retained directory descriptor.
        root = os.open(".", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC, dir_fd=directory_fd)
        info = os.fstat(root)
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise AssetError("ASSET_DIRECTORY_UNSAFE")
        fcntl.flock(root, fcntl.LOCK_EX if write else fcntl.LOCK_SH)
        yield root, info.st_dev
    except OSError:
        raise AssetError("ASSET_IO_FAILED") from None
    finally:
        if root is not None:
            os.close(root)


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _read(root, device, digest):
    pin = reader = None
    try:
        pin = os.open(digest, os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=root)
        info = os.fstat(pin)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_dev != device
                or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o400
                or info.st_size > MAX_ASSET_BYTES):
            raise AssetError("ASSET_OBJECT_UNSAFE")
        reader = os.open(f"/proc/self/fd/{pin}", os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK)
        if _identity(info) != _identity(os.fstat(reader)):
            raise AssetError("ASSET_OBJECT_CHANGED")
        chunks, size = [], 0
        content_hash = hashlib.sha256()
        while True:
            chunk = os.read(reader, min(CHUNK_BYTES, MAX_ASSET_BYTES + 1 - size))
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_ASSET_BYTES:
                raise AssetError("ASSET_BYTE_LIMIT")
            content_hash.update(chunk)
            chunks.append(chunk)
        if (size != info.st_size or _identity(info) != _identity(os.fstat(reader))
                or _identity(info) != _identity(os.stat(digest, dir_fd=root,
                                                       follow_symlinks=False))):
            raise AssetError("ASSET_OBJECT_CHANGED")
        if content_hash.hexdigest() != digest:
            raise AssetError("ASSET_DIGEST_MISMATCH")
        return b"".join(chunks)
    finally:
        if reader is not None:
            os.close(reader)
        if pin is not None:
            os.close(pin)


def read_asset(directory_fd: int, digest: str) -> bytes:
    """Caller must authorize this exact asset through its workspace registry."""
    if type(digest) is not str or DIGEST.fullmatch(digest) is None:
        raise AssetError("ASSET_DIGEST_INVALID")
    with _directory(directory_fd, write=False) as (root, device):
        return _read(root, device, digest)


def put_asset(directory_fd: int, content: bytes) -> str:
    """Return a hash only after durable content and directory publication.

    A crash can leave an orphan temp/blob, never an authorized DB reference.
    Recovery/retention needs a separate bounded registry-aware reconciler.
    """
    if type(content) is not bytes or len(content) > MAX_ASSET_BYTES:
        raise AssetError("ASSET_BYTE_LIMIT")
    digest = hashlib.sha256(content).hexdigest()
    with _directory(directory_fd, write=True) as (root, device):
        try:
            os.stat(digest, dir_fd=root, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            if _read(root, device, digest) != content:
                raise AssetError("ASSET_CONTENT_CONFLICT")
            os.fsync(root)
            return digest
        temporary = ".pending-" + secrets.token_hex(16)
        writer = None
        created = False
        try:
            writer = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
                             | os.O_CLOEXEC, 0o600, dir_fd=root)
            created = True
            view = memoryview(content)
            while view:
                written = os.write(writer, view[:CHUNK_BYTES])
                if written <= 0:
                    raise AssetError("ASSET_WRITE_INCOMPLETE")
                view = view[written:]
            os.fchmod(writer, 0o400)
            os.fsync(writer)
            os.close(writer)
            writer = None
            # Every trusted store user holds this directory's flock. There is
            # no untrusted writer in this mode0700 control-owned directory.
            os.rename(temporary, digest, src_dir_fd=root, dst_dir_fd=root)
            created = False
            os.fsync(root)
            return digest
        finally:
            if writer is not None:
                os.close(writer)
            if created:
                os.unlink(temporary, dir_fd=root)
