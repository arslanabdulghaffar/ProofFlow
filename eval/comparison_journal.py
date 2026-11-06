"""Finite private B/C comparison receipts, separate from infrastructure probe capacity.

This is an extra admission gate, never a replacement for the global PostgreSQL
reserve/claim. No refund, retry permission, provider call or candidate execution.
"""

import base64
import fcntl
import hashlib
import os
import re
import stat
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID

from contracts.codec import canonical_bytes, parse_object
from orchestrator.probe_plan import VULTR_CHAT_URL

MAX_FILE = 400000
MAX_CALLS = 144
JOB_CAP = 100000
CAMPAIGN_CAP = 4800000
VERSION = "proofflow-comparison-journal-v1"
CALL_FILE = re.compile(r"(request|response)-[a-f0-9]{32}\.json")


class ComparisonJournalError(Exception):
    pass


def require(value):
    if not value:
        raise ComparisonJournalError("COMPARISON_JOURNAL_INVALID")


def identifier(value):
    result = str(UUID(str(value)))
    require(str(value) == result)
    return result


def private_file(info):
    require(
        stat.S_ISREG(info.st_mode)
        and info.st_uid == os.geteuid()
        and info.st_nlink == 1
        and stat.S_IMODE(info.st_mode) == 0o600
    )


def read(directory, name):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    try:
        info = os.fstat(fd)
        private_file(info)
        require(0 < info.st_size <= MAX_FILE)
        with os.fdopen(fd, "rb", closefd=False) as source:
            raw = source.read(MAX_FILE + 1)
        after = os.fstat(fd)
        require(
            len(raw) == info.st_size
            and info.st_mtime_ns == after.st_mtime_ns
            and info.st_size == after.st_size
        )
        return parse_object(raw, max_bytes=MAX_FILE)
    finally:
        os.close(fd)


def write(directory, name, value):
    raw = canonical_bytes(value, max_bytes=MAX_FILE)
    fd = os.open(
        name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory
    )
    with os.fdopen(fd, "wb") as output:
        os.fchmod(output.fileno(), 0o600)
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())
    os.fsync(directory)


def directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        require(
            stat.S_ISDIR(info.st_mode)
            and info.st_uid == os.geteuid()
            and stat.S_IMODE(info.st_mode) == 0o700
        )
    except BaseException:
        os.close(fd)
        raise
    return fd


def validate_plan(plan, campaign):
    require(
        set(plan) == {"version", "campaign_sha256", "jobs"}
        and plan["version"] == VERSION
        and plan["campaign_sha256"] == campaign
        and type(plan["jobs"]) is dict
        and len(plan["jobs"]) == 48
    )
    require(all(identifier(job) == job and arm in ("B", "C") for job, arm in plan["jobs"].items()))
    require(
        list(plan["jobs"].values()).count("B") == 24
        and list(plan["jobs"].values()).count("C") == 24
    )


def initialize(root: Path, campaign: str, jobs: dict):
    require(type(campaign) is str and re.fullmatch("[a-f0-9]{64}", campaign) is not None)
    plan = {"version": VERSION, "campaign_sha256": campaign, "jobs": jobs}
    validate_plan(plan, campaign)
    root.mkdir(mode=0o700)  # No replay, eviction or overwrite of a partial campaign.
    fd = directory(root)
    try:
        write(fd, "plan.json", plan)
    finally:
        os.close(fd)
    parent = directory(root.parent)
    try:
        os.fsync(parent)
    finally:
        os.close(parent)


class ComparisonJournal:
    def __init__(self, root: Path, job: str, campaign: str):
        require(type(campaign) is str and re.fullmatch("[a-f0-9]{64}", campaign) is not None)
        self.root, self.job, self.campaign = root, identifier(job), campaign

    @contextmanager
    def locked(self):
        root = directory(self.root)
        lock = None
        try:
            lock = os.open(
                "lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=root
            )
            private_file(os.fstat(lock))
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            config = read(root, "plan.json")
            validate_plan(config, self.campaign)
            require(self.job in config["jobs"])
            names = set()
            with os.scandir(root) as entries:
                for entry in entries:
                    require(entry.name in ("plan.json", "lock") or CALL_FILE.fullmatch(entry.name))
                    info = entry.stat(follow_symlinks=False)
                    private_file(info)
                    require(info.st_size <= MAX_FILE)
                    names.add(entry.name)
                    require(len(names) <= 2 + 2 * MAX_CALLS)
            require(all("request-" + n[9:] in names for n in names if n.startswith("response-")))
            yield root, config, names
        finally:
            if lock is not None:
                os.close(lock)
            os.close(root)

    def intent(self, request_id, plan):
        request = identifier(request_id)
        require(
            plan.endpoint == VULTR_CHAT_URL
            and type(plan.reserve_micro_usd) is int
            and 0 < plan.reserve_micro_usd <= JOB_CAP
            and type(plan.payload) is bytes
            and 0 < len(plan.payload) <= 102400
            and type(plan.quote_payload) is bytes
            and 0 < len(plan.quote_payload) <= 4096
            and re.fullmatch("[a-f0-9]{64}", plan.request_sha256) is not None
        )
        return {
            "campaign_sha256": self.campaign,
            "job": self.job,
            "request_id": request,
            "request_sha256": plan.request_sha256,
            "reserve_micro_usd": plan.reserve_micro_usd,
            "payload_base64": base64.b64encode(plan.payload).decode(),
            "quote_base64": base64.b64encode(plan.quote_payload).decode(),
        }

    async def prepare(self, request_id, plan):
        value = self.intent(request_id, plan)
        name = "request-" + UUID(value["request_id"]).hex + ".json"
        with self.locked() as (root, config, names):
            if name in names:
                require(read(root, name) == value)
                return False  # An unanswered intent consumes capacity and cannot send again.
            rows = []
            for existing in names:
                if existing.startswith("request-"):
                    row = read(root, existing)
                    require(
                        set(row) == set(value)
                        and row["campaign_sha256"] == self.campaign
                        and row["job"] in config["jobs"]
                        and "request-" + UUID(identifier(row["request_id"])).hex + ".json"
                        == existing
                        and type(row["reserve_micro_usd"]) is int
                        and 0 < row["reserve_micro_usd"] <= JOB_CAP
                    )
                    rows.append(row)
            require(len(rows) < MAX_CALLS)
            own = [r for r in rows if r["job"] == self.job]
            require(
                len(own) < 3
                and sum(r["reserve_micro_usd"] for r in own) + value["reserve_micro_usd"] <= JOB_CAP
                and sum(r["reserve_micro_usd"] for r in rows) + value["reserve_micro_usd"]
                <= CAMPAIGN_CAP
            )
            write(root, name, value)
            return True

    async def record(self, request_id, plan, outcome, body, status, elapsed_ms):
        value = self.intent(request_id, plan)
        require(
            outcome in ("PARSED_RESPONSE", "OUTCOME_UNKNOWN")
            and (body is None or type(body) is bytes and len(body) <= 262144)
            and (status is None or type(status) is int and 100 <= status <= 599)
            and type(elapsed_ms) is int
            and 0 <= elapsed_ms <= 120000
        )
        require(outcome != "PARSED_RESPONSE" or body is not None and status == 200)
        result = {
            "request_sha256": plan.request_sha256,
            "outcome": outcome,
            "response_base64": None if body is None else base64.b64encode(body).decode(),
            "response_sha256": None if body is None else hashlib.sha256(body).hexdigest(),
            "http_status": status,
            "elapsed_ms": elapsed_ms,
        }
        suffix = UUID(value["request_id"]).hex + ".json"
        with self.locked() as (root, _, names):
            require(read(root, "request-" + suffix) == value)
            name = "response-" + suffix
            if name in names:
                require(read(root, name) == result)
                return False
            write(root, name, result)
            return True

    async def snapshot(self, request_id):
        suffix = UUID(identifier(request_id)).hex + ".json"
        with self.locked() as (root, _, names):
            if "request-" + suffix not in names:
                return None
            row = read(root, "request-" + suffix)
            require(
                row["job"] == self.job
                and row["campaign_sha256"] == self.campaign
                and row["request_id"] == identifier(request_id)
            )
            if "response-" + suffix not in names:
                return {**row, "state": "PREPARED"}
            response = read(root, "response-" + suffix)
            require(response["request_sha256"] == row["request_sha256"])
            return {**row, **response, "state": "RECORDED"}
