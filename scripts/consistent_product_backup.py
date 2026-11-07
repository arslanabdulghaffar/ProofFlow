"""Bounded trusted Linux DB capture; no candidate execution or plaintext disk writes.

The inventory, asset registry and pg_dump share one exported MVCC snapshot.
Only fixed local Docker/Unix-socket PostgreSQL commands are used. Callers must
authenticate immutable asset bytes and use fresh deletion authority on recovery.
This does not schedule backups, export roles/secrets, or authorize live promotion.
"""

import hashlib
import json
import os
import re
import selectors
import shutil
import subprocess
import time
from contextlib import contextmanager

from orchestrator.restore_guard import CURRENT_AUTHORITY_SQL, check_dump, inventory

LIMIT = 16 * 1024 * 1024
REGISTRY_SQL = """SELECT COALESCE(jsonb_agg(to_jsonb(a) ORDER BY a.workspace_id,a.id),'[]')
FROM (SELECT a.workspace_id,a.id,a.sha256,a.created_at,a.byte_size
 FROM pf_product.assets a JOIN pf_product.workspaces w ON w.id=a.workspace_id
 WHERE w.revoked_at IS NULL
 AND w.expires_at>current_setting('proofflow.backup_at')::timestamptz
 AND NOT EXISTS (SELECT 1 FROM pf_product.deletions d WHERE d.workspace_id=w.id)
 LIMIT 257) a;"""


class CaptureError(ValueError):
    pass


def command(container, executable, *arguments):
    if os.name != "posix" or not re.fullmatch(
        r"proofflow-budget|proofflow-queue-test-[a-f0-9]{32}", container
    ):
        raise CaptureError("BACKUP_TARGET_INVALID")
    docker = shutil.which("docker")
    if not docker or executable not in ("psql", "pg_dump"):
        raise CaptureError("BACKUP_TOOL_UNAVAILABLE")
    socket = "/run/proofflow-budget" if container == "proofflow-budget" else "/var/run/postgresql"
    return [docker, "--host=unix:///var/run/docker.sock", "exec", "-i", "--user=70:70",
            "-e", "PGOPTIONS=-c statement_timeout=45000 -c lock_timeout=3000 "
            "-c idle_in_transaction_session_timeout=60000", container,
            "timeout", "-s", "KILL", "55", executable,
            "-h", socket, "-U", "postgres", *arguments]


class Reader:
    """Drain both pipes with a shared deadline and bounded memory, including errors."""

    def __init__(self, process, limit, deadline):
        self.selector = selectors.DefaultSelector()
        for stream in (process.stdout, process.stderr):
            self.selector.register(stream, selectors.EVENT_READ)
        self.process, self.limit, self.deadline = process, limit, deadline
        self.pending = bytearray()
        self.total = 0

    def pump(self):
        left = self.deadline - time.monotonic()
        if left <= 0:
            raise CaptureError("BACKUP_TIMEOUT")
        events = self.selector.select(left)
        if not events:
            raise CaptureError("BACKUP_TIMEOUT")
        for key, _ in events:
            raw = os.read(key.fileobj.fileno(), min(65536, self.limit - self.total + 1))
            if not raw:
                self.selector.unregister(key.fileobj)
                continue
            self.total += len(raw)
            if self.total > self.limit:
                raise CaptureError("BACKUP_OUTPUT_LIMIT")
            if key.fileobj is self.process.stderr:
                # Warnings are not silently discarded; keep diagnostics out of logs.
                raise CaptureError("BACKUP_TOOL_DIAGNOSTIC")
            self.pending.extend(raw)

    def line(self):
        while b"\n" not in self.pending:
            if not self.selector.get_map():
                raise CaptureError("BACKUP_UNEXPECTED_EOF")
            self.pump()
        raw, _, rest = self.pending.partition(b"\n")
        self.pending = bytearray(rest)
        return bytes(raw)

    def all(self):
        while self.selector.get_map():
            self.pump()
        if self.process.wait(timeout=max(0.01, self.deadline-time.monotonic())) != 0:
            raise CaptureError("BACKUP_TOOL_FAILED")
        return bytes(self.pending)

    def close(self):
        self.selector.close()


@contextmanager
def running(argv, limit, deadline):
    with subprocess.Popen(  # noqa: S603 - fixed trusted DB argv; no shell or candidate
        argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ) as process:
        reader = Reader(process, limit, deadline)
        try:
            yield process, reader
        finally:
            reader.close()
            # Closing the exporter rolls back. Container-owned timeout also kills
            # a client stuck writing after its SQL ends; SQL timeout alone cannot.
            # Server timeouts bound abandoned transactions independently of Docker.
            try:
                process.stdin.close()
            except BrokenPipeError:
                pass  # Preserve bounded kill/wait even if the tool already closed input.
            if process.poll() is None:
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)


@contextmanager
def snapshot(container):
    """Hold only the fixed read-only exporter; caller cannot supply SQL/commands."""
    deadline = time.monotonic() + 50
    args = command(container, "psql", "-X", "-qAt", "--set", "ON_ERROR_STOP=1",
                   "-d", "proofflow_product")
    with running(args, 128 * 1024, deadline) as (process, reader):
        process.stdin.write(("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;\n"
                             "SELECT pg_export_snapshot();\n"
                             "DO $$ BEGIN PERFORM set_config('proofflow.backup_at',"
                             "clock_timestamp()::text,true); END $$;\n"
                             + CURRENT_AUTHORITY_SQL.replace("clock_timestamp()",
                                 "current_setting('proofflow.backup_at')::timestamptz")
                             .replace("json_build_object", "jsonb_build_object")
                             .replace("json_agg", "jsonb_agg").replace("::json", "::jsonb")
                             + "\n" + REGISTRY_SQL + "\n").encode())
        process.stdin.flush()
        identity = reader.line().decode("ascii")
        if not re.fullmatch(r"[A-F0-9]{8}-[A-F0-9]{8}-[0-9]+", identity):
            raise CaptureError("BACKUP_SNAPSHOT_INVALID")
        authority, assets = json.loads(reader.line()), json.loads(reader.line())
        inventory(authority)
        if len(assets) > 256:
            raise CaptureError("BACKUP_ASSET_LIMIT")
        yield Snapshot(container, identity, authority, assets, deadline)
        process.stdin.write(b"ROLLBACK;\n\\q\n")
        process.stdin.flush()
        if reader.all():
            raise CaptureError("BACKUP_UNEXPECTED_TRAILING_OUTPUT")


class Snapshot:
    def __init__(self, container, identity, inventory, assets, deadline):
        self.container, self.identity = container, identity
        self.inventory, self.assets, self.deadline = inventory, assets, deadline

    def dump(self):
        args = command(self.container, "pg_dump", "--snapshot=" + self.identity,
                       "--no-owner", "--no-privileges", "proofflow_product")
        with running(args, LIMIT, self.deadline) as (process, reader):
            process.stdin.close()
            raw = reader.all()
        check_dump(raw, hashlib.sha256(raw).hexdigest())
        return raw
