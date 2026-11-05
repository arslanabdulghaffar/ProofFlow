"""Private Linux pilot reservation journal, in addition to the global PostgreSQL cap.

Never release a reservation or replay an uncertain request. The finite manifest is
installed by the operator; neither model nor worker can access this directory.
"""

import json
import os
import stat
from pathlib import Path
from uuid import UUID

from contracts.codec import canonical_bytes


class PilotLimit(Exception):
    pass


def read_private(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_nlink != 1 or info.st_mode & 0o077 or info.st_size > 16384):
            raise PilotLimit("PILOT_JOURNAL_UNSAFE")
        return json.loads(os.read(fd, 16385))
    finally:
        os.close(fd)


class PilotJournal:
    def __init__(self, root: Path, job: str, durable):
        self.root, self.job, self.durable = root, str(UUID(job)), durable

    def hold(self, request_id, plan):
        import fcntl

        info = self.root.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise PilotLimit("PILOT_JOURNAL_UNSAFE")
        fd = os.open(self.root / "lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_nlink != 1 or info.st_mode & 0o077):
                raise PilotLimit("PILOT_JOURNAL_UNSAFE")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            config = read_private(self.root / "plan.json")
            if (len(config["jobs"]) != 12 or len(set(config["jobs"])) != 12
                    or self.job not in config["jobs"]):
                raise PilotLimit("PILOT_JOB_NOT_DECLARED")
            name = "call-" + UUID(str(request_id)).hex + ".json"
            row = {"job": self.job, "request": str(UUID(str(request_id))),
                   "sha256": plan.request_sha256, "reserve": plan.reserve_micro_usd}
            if type(row["reserve"]) is not int or not 1 <= row["reserve"] <= 100000:
                raise PilotLimit("PILOT_RESERVATION_INVALID")
            if (self.root / name).exists() or (self.root / name).is_symlink():
                if read_private(self.root / name) != row:
                    raise PilotLimit("PILOT_REQUEST_CONFLICT")
                return False
            paths = list(self.root.glob("call-*.json"))
            if len(paths) >= 36:
                raise PilotLimit("PILOT_CALL_LIMIT")
            rows = [read_private(p) for p in paths]
            if any(type(r.get("reserve")) is not int or not 1 <= r["reserve"] <= 100000
                   or r.get("job") not in config["jobs"] for r in rows):
                raise PilotLimit("PILOT_JOURNAL_INVALID")
            own = [r for r in rows if r["job"] == self.job]
            if (len(own) >= 3 or sum(r["reserve"] for r in own) + row["reserve"] > 100000
                    or sum(r["reserve"] for r in rows) + row["reserve"] > 1200000):
                raise PilotLimit("PILOT_BUDGET_EXHAUSTED")
            raw = canonical_bytes(row)
            out = os.open(self.root / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                          | os.O_NOFOLLOW, 0o600)
            try:
                with os.fdopen(out, "wb", closefd=False) as file:
                    file.write(raw)
                    file.flush()
                    os.fsync(file.fileno())
            finally:
                os.close(out)
            parent = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(parent)
            finally:
                os.close(parent)
            return True
        finally:
            os.close(fd)

    async def prepare(self, request_id, plan):
        if not self.hold(request_id, plan):
            return False
        return await self.durable.prepare(request_id, plan)

    async def record(self, *args):
        return await self.durable.record(*args)
