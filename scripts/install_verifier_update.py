"""Two fixed configuration replacements, exact predecessor preserved; trusted admin only."""

import base64
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

PATHS = {
    "/etc/proofflow-product-dispatcher/worker/worker.json": (10003, 0o400),
    "/etc/systemd/system/proofflow-verifier-helper.service": (0, 0o644),
}


def replace(path, raw, uid, mode):
    pending = path.with_name(path.name + ".verifier-pending")
    fd = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, "wb") as output:
        output.write(raw)
        output.flush()
        os.fchown(output.fileno(), uid, uid)
        os.fchmod(output.fileno(), mode)
        os.fsync(output.fileno())
    os.replace(pending, path)
    fd = os.open(path.parent, os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def install(value, *, check_only=False):
    if set(value) != set(PATHS):
        raise RuntimeError("VERIFIER_UPDATE_PATHS_INVALID")
    updates = []
    for name, (uid, mode) in PATHS.items():
        path = Path(name)
        info = path.lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid != uid
            or stat.S_IMODE(info.st_mode) != mode
        ):
            raise RuntimeError("VERIFIER_UPDATE_FILE_UNSAFE")
        old = base64.b64decode(value[name]["old"], validate=True)
        new = base64.b64decode(value[name]["new"], validate=True)
        if not 0 < len(new) <= 16384 or path.read_bytes() != old:
            raise RuntimeError("VERIFIER_UPDATE_PREDECESSOR_CHANGED")
        updates.append((path, uid, mode, old, new))
    if check_only:
        return
    for path, uid, mode, old, new in updates:
        backup = path.with_name(path.name + ".previous-" + hashlib.sha256(old).hexdigest())
        fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
        with os.fdopen(fd, "wb") as output:
            output.write(old)
            output.flush()
            os.fsync(output.fileno())
        replace(path, new, uid, mode)


if __name__ == "__main__":
    try:
        if os.geteuid() != 0 or sys.argv[1:] not in ([], ["--check-only"]):
            raise RuntimeError("VERIFIER_UPDATE_ADMIN_REQUIRED")
        install(json.load(sys.stdin), check_only=sys.argv[1:] == ["--check-only"])
        print("VERIFIER_CONFIGURATION_CHECKED")
    except Exception:
        raise SystemExit("VERIFIER_UPDATE_STOPPED_RECONCILE_NO_RETRY") from None
