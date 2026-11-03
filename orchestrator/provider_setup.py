"""Host-only credential loading. Loading never authorizes or sends a request."""

import os
import stat
import sys
from dataclasses import dataclass, field
from pathlib import PurePosixPath


class SetupError(Exception):
    """Fixed diagnostic with no path, secret or OS diagnostic."""


@dataclass(frozen=True)
class ProviderSecrets:
    database_password: str = field(repr=False)
    vultr_api_key: str = field(repr=False)


def valid_secret(value: str) -> bool:
    return (type(value) is str and 32 <= len(value) <= 512
            and all(33 <= ord(char) <= 126 for char in value))


def load_provider_secrets(directory: str = "/etc/proofflow/credentials") -> ProviderSecrets:
    """Pin every directory; accept only owner-readable, single-link regular files.

    Linux deployment only. Both files belong to the service UID, mode 0400/0600.
    Ancestors must be root/service-owned and not group/world writable. No env,
    command-line secret, symlink, device, FIFO, home-directory or password fallback.
    """
    if sys.platform != "linux":
        raise SetupError("SECRET_HOST_UNSUPPORTED")
    path = PurePosixPath(directory)
    if (not path.is_absolute() or str(path) != directory or ".." in path.parts
            or directory == "/"):
        raise SetupError("SECRET_DIRECTORY_INVALID")
    descriptors = []
    try:
        current = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        descriptors.append(current)
        for part in path.parts[1:]:
            current = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                              | os.O_CLOEXEC, dir_fd=current)
            descriptors.append(current)
            info = os.fstat(current)
            if info.st_uid not in (0, os.geteuid()) or info.st_mode & 0o022:
                raise SetupError("SECRET_DIRECTORY_UNSAFE")
        values = []
        for name in ("budget-password", "vultr-api-key"):
            # O_PATH inspects the inode before any device/FIFO can be opened for I/O.
            pinned = os.open(name, os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=current)
            descriptors.append(pinned)
            before = os.fstat(pinned)
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                    or before.st_uid != os.geteuid()
                    or stat.S_IMODE(before.st_mode) not in (0o400, 0o600)
                    or not 32 <= before.st_size <= 513):
                raise SetupError("SECRET_FILE_UNSAFE")
            reader = os.open(f"/proc/self/fd/{pinned}", os.O_RDONLY | os.O_CLOEXEC)
            descriptors.append(reader)
            raw = os.read(reader, 514)
            after = os.fstat(reader)
            if ((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
                 before.st_ctime_ns) != (after.st_dev, after.st_ino, after.st_size,
                                        after.st_mtime_ns, after.st_ctime_ns)):
                raise SetupError("SECRET_FILE_CHANGED")
            value = raw.removesuffix(b"\n").decode("ascii")
            if not valid_secret(value):
                raise SetupError("SECRET_VALUE_INVALID")
            values.append(value)
        return ProviderSecrets(*values)
    except (OSError, UnicodeError, ValueError):
        raise SetupError("SECRET_LOAD_FAILED") from None
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
