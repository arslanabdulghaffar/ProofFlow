"""Worker-only durable admission, fencing, cancellation and cleanup journal."""

import hashlib
import json
import os
import sqlite3
import stat
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID

from worker.protocol import ExecutionRequest, SupervisorError


def private_directory(path: Path) -> None:
    info = path.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
            or info.st_mode & 0o077):
        raise SupervisorError("UNSAFE_WORKER_DIRECTORY")


class Journal:
    def __init__(self, root: Path):
        private_directory(root)
        self.root = root
        self.path = root / "journal.sqlite3"
        if self.path.exists() or self.path.is_symlink():
            info = self.path.lstat()
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or info.st_uid != os.geteuid() or info.st_mode & 0o077):
                raise SupervisorError("UNSAFE_WORKER_JOURNAL")
        else:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS executions (
                    id TEXT PRIMARY KEY, job TEXT NOT NULL, generation INTEGER NOT NULL,
                    manifest TEXT NOT NULL, state TEXT NOT NULL, cancel INTEGER NOT NULL DEFAULT 0,
                    receipt TEXT, UNIQUE(job,generation));
                CREATE TABLE IF NOT EXISTS fences (
                    job TEXT PRIMARY KEY, generation INTEGER NOT NULL);
            """)

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=3, isolation_level=None)
        try:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            yield db
            if db.in_transaction:
                db.commit()
        except BaseException:
            if db.in_transaction:
                db.rollback()
            raise
        finally:
            db.close()

    def admit(self, request: ExecutionRequest, runtime_digest: str,
              *, retained_slots: int = 0) -> bool:
        if len(runtime_digest) != 64 or any(c not in "0123456789abcdef" for c in runtime_digest):
            raise SupervisorError("INVALID_RUNTIME_IDENTITY")
        digest = hashlib.sha256((request.manifest_hash() + runtime_digest).encode()).hexdigest()
        with self._db() as db:
            old = db.execute("SELECT manifest FROM executions WHERE id=?",
                             (request.execution_id.hex,)).fetchone()
            if old:
                if old[0] != digest:
                    raise SupervisorError("EXECUTION_CONFLICT")
                return False  # Existing IDs are reconciled, never re-executed.
            if retained_slots >= 20:
                raise SupervisorError("RESULT_RETENTION_CAPACITY")
            fence = db.execute("SELECT generation FROM fences WHERE job=?",
                               (request.job_id.hex,)).fetchone()
            if fence and request.generation < fence[0]:
                raise SupervisorError("STALE_EXECUTION_GENERATION")
            if db.execute("SELECT 1 FROM executions WHERE state='QUARANTINED'").fetchone():
                raise SupervisorError("WORKER_QUARANTINED")
            query = "SELECT count(*) FROM executions WHERE state!='CLEANED'"
            count = db.execute(query).fetchone()[0]
            if count >= 2:
                raise SupervisorError("WORKER_CAPACITY_EXHAUSTED")
            if db.execute("SELECT 1 FROM executions WHERE job=? AND state!='CLEANED'",
                          (request.job_id.hex,)).fetchone():
                raise SupervisorError("JOB_ALREADY_RUNNING")
            db.execute("INSERT INTO fences VALUES (?,?) ON CONFLICT(job) DO UPDATE "
                       "SET generation=max(generation,excluded.generation)",
                       (request.job_id.hex, request.generation))
            try:
                db.execute("INSERT INTO executions(id,job,generation,manifest,state) "
                           "VALUES(?,?,?,?,'PREPARING')",
                           (request.execution_id.hex, request.job_id.hex,
                            request.generation, digest))
            except sqlite3.IntegrityError:
                raise SupervisorError("EXECUTION_GENERATION_REUSED") from None
        return True

    def running(self, identifier: UUID) -> None:
        with self._db() as db:
            if db.execute("UPDATE executions SET state='RUNNING' WHERE id=? AND state='PREPARING'",
                          (identifier.hex,)).rowcount != 1:
                raise SupervisorError("INVALID_EXECUTION_TRANSITION")

    def cancel(self, identifier: UUID, job: UUID, generation: int) -> None:
        with self._db() as db:
            if db.execute("UPDATE executions SET cancel=1 WHERE id=? AND job=? AND generation=? "
                          "AND state!='CLEANED'",
                          (identifier.hex, job.hex, generation)).rowcount != 1:
                raise SupervisorError("EXECUTION_SCOPE_MISMATCH")

    def fence(self, job: UUID, generation: int) -> None:
        if type(generation) is not int or not 1 <= generation <= 2147483647:
            raise SupervisorError("INVALID_EXECUTION_GENERATION")
        with self._db() as db:
            old = db.execute("SELECT generation FROM fences WHERE job=?", (job.hex,)).fetchone()
            if old and generation <= old[0]:
                raise SupervisorError("STALE_EXECUTION_GENERATION")
            db.execute("INSERT INTO fences VALUES (?,?) ON CONFLICT(job) DO UPDATE "
                       "SET generation=excluded.generation", (job.hex, generation))
            db.execute("UPDATE executions SET cancel=1 WHERE job=? AND generation<? "
                       "AND state!='CLEANED'",
                       (job.hex, generation))

    def cancelled(self, identifier: UUID) -> bool:
        with self._db() as db:
            row = db.execute("SELECT cancel FROM executions WHERE id=?",
                             (identifier.hex,)).fetchone()
            if row is None:
                raise SupervisorError("UNKNOWN_EXECUTION")
            return bool(row[0])

    def finish(self, identifier: UUID, receipt: dict, *, cleaned: bool) -> None:
        with self._db() as db:
            cancelled = db.execute("SELECT cancel FROM executions WHERE id=?",
                                   (identifier.hex,)).fetchone()
            if cancelled and cancelled[0] and cleaned:
                receipt["outcome"] = "cancelled"
            if db.execute("UPDATE executions SET state=?,receipt=? WHERE id=? AND state!='CLEANED'",
                          ("CLEANED" if cleaned else "QUARANTINED",
                           json.dumps(receipt, sort_keys=True), identifier.hex)).rowcount != 1:
                raise SupervisorError("INVALID_EXECUTION_TRANSITION")

    def unfinished(self) -> list[UUID]:
        with self._db() as db:
            return [UUID(hex=row[0]) for row in
                    db.execute("SELECT id FROM executions WHERE state!='CLEANED'")]

    def receipt(self, identifier: UUID) -> dict | None:
        with self._db() as db:
            row = db.execute("SELECT receipt FROM executions WHERE id=?",
                             (identifier.hex,)).fetchone()
            return json.loads(row[0]) if row and row[0] else None

    def scoped_status(self, identifier: UUID, job: UUID, generation: int) -> dict:
        with self._db() as db:
            row = db.execute("SELECT state,receipt FROM executions WHERE id=? AND job=? "
                             "AND generation=?", (identifier.hex, job.hex, generation)).fetchone()
            if row is None:
                raise SupervisorError("EXECUTION_SCOPE_MISMATCH")
            return {"execution": identifier.hex, "job": job.hex, "generation": generation,
                    "state": row[0], "receipt": json.loads(row[1]) if row[1] else None}
