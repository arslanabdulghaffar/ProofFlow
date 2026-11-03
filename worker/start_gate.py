"""Host-only systemd ExecStartPre gate; no candidate import or execution.

A late/uncertain start cannot launch runsc after its private staging is removed.
Only the supervisor creates the root-owned ready file after observing this unit.
"""

import os
import stat
import sys
import time
from pathlib import Path


def wait_for_ready(path: Path) -> int:
    if (path.name != "launch.ready" or len(path.parent.name) != 32
            or any(c not in "0123456789abcdef" for c in path.parent.name)
            or path.parent.parent.name != "executions"):
        return 78
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                info = os.fstat(descriptor)
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0
                        or info.st_mode & 0o077 or info.st_nlink != 1):
                    return 78
                return 0 if os.read(descriptor, 33) == path.parent.name.encode() else 78
            finally:
                os.close(descriptor)
        except FileNotFoundError:
            if not path.parent.is_dir():
                return 78
            time.sleep(0.02)
    return 78


if __name__ == "__main__":
    raise SystemExit(wait_for_ready(Path(sys.argv[1])) if len(sys.argv) == 2 else 78)
