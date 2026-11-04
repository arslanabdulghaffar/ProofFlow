"""Fixed private product credential path, never supplied by HTTP/model content."""

import os
import stat

from api.app.product_store import ProductFailure
from orchestrator.provider_setup import valid_secret


def database_password():
    descriptors = []
    try:
        root = os.open("/etc/proofflow-product/credentials",
                       os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(root)
        info = os.fstat(root)
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise ProductFailure("PRODUCT_SECRET_DIRECTORY_UNSAFE")
        pin = os.open("database-password", os.O_PATH | os.O_NOFOLLOW, dir_fd=root)
        descriptors.append(pin)
        before = os.fstat(pin)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid()
                or before.st_nlink != 1
                or stat.S_IMODE(before.st_mode) != 0o400 or not 32 <= before.st_size <= 512):
            raise ProductFailure("PRODUCT_SECRET_FILE_UNSAFE")
        reader = os.open(f"/proc/self/fd/{pin}", os.O_RDONLY | os.O_CLOEXEC)
        descriptors.append(reader)
        raw = os.read(reader, 513)
        after = os.fstat(reader)
        def identity(s):
            return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if identity(before) != identity(after):
            raise ProductFailure("PRODUCT_SECRET_CHANGED")
        value = raw.decode("ascii")
        if len(raw) != before.st_size or not valid_secret(value):
            raise ProductFailure("PRODUCT_SECRET_INVALID")
        return value
    except (OSError, UnicodeError):
        raise ProductFailure("PRODUCT_SECRET_UNAVAILABLE") from None
    finally:
        for fd in reversed(descriptors):
            os.close(fd)
