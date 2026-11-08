"""Root administrator: one expiring guest window, no caller-selected commands/paths."""

import json
import os
import re
import stat
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

ROOT = Path("/etc/proofflow-guest-demo")
STATE = ROOT / "window.json"
BOOT = Path("/proc/sys/kernel/random/boot_id")


def valid_window(value, now, boot):
    try:
        start = datetime.fromisoformat(value["started_at"])
        end = datetime.fromisoformat(value["expires_at"])
        funded = datetime.fromisoformat(value["funded_until"])
        quote = datetime.fromisoformat(value["quote_until"])
        return (
            str(UUID(value["workspace_id"])) == value["workspace_id"]
            and str(UUID(value["window_id"])) == value["window_id"]
            and value["boot_id"] == boot
            and value["state"] == "ACTIVE"
            and start <= now < end <= min(quote, funded)
            and timedelta(0) < end - start <= timedelta(minutes=30)
        )
    except (KeyError, TypeError, ValueError):
        return False


def command(args, raw=None):
    r = subprocess.run(  # noqa: S603 - fixed administrative argv, never guest input
        args,
        input=raw,
        capture_output=True,
        timeout=20,  # noqa: S603
        env={"PATH": "/usr/bin:/usr/sbin:/bin", "LANG": "C"},
    )
    if r.returncode:
        raise RuntimeError("DEMO_ADMIN_COMMAND_FAILED")
    return r.stdout.strip()


def sql(database, statement):
    if database not in ("proofflow_product", "proofflow_budget"):
        raise RuntimeError("DEMO_DATABASE_INVALID")
    return command(
        [
            "/usr/bin/docker",
            "--host=unix:///var/run/docker.sock",
            "exec",
            "-i",
            "--user=70:70",
            "proofflow-budget",
            "psql",
            "-X",
            "-qAt",
            "-h",
            "/run/proofflow-budget",
            "-U",
            "postgres",
            "-d",
            database,
            "--set",
            "ON_ERROR_STOP=1",
        ],
        statement.encode(),
    )


def load():
    try:
        fd = os.open(STATE, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    with os.fdopen(fd, "rb") as f:
        info = os.fstat(f.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != 0
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o600
            or not 1 <= info.st_size <= 4096
        ):
            raise RuntimeError("DEMO_STATE_UNSAFE")
        return json.loads(f.read(4097))


def save(value):
    pending = ROOT / "window.pending"
    fd = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(json.dumps(value, sort_keys=True).encode())
        f.flush()
        os.fsync(f.fileno())
    os.replace(pending, STATE)
    fd = os.open(ROOT, os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def close(value, reason):
    # Block new inference before changing execution policy. Neither operation
    # edits job outcomes, settlements, business rules or quota limits.
    sql("proofflow_budget", "UPDATE pf_budget.accounts SET blocked=true WHERE NOT blocked;")
    sql(
        "proofflow_product",
        "SELECT pf_product.configure_execution(runtime_sha256,"
        "verifier_sha256,false) FROM pf_product.execution_policy WHERE enabled;",
    )
    if value is not None:
        value.update(state="CLOSED", closed_at=datetime.now(UTC).isoformat(), reason=reason)
        save(value)
    return {"state": "CLOSED", "reason": reason}


def arm(value, now, boot):
    fields = {
        "window_id",
        "workspace_id",
        "started_at",
        "expires_at",
        "funded_until",
        "quote_until",
        "boot_id",
        "state",
    }
    if (
        set(value) != fields
        or not valid_window(value, now, boot)
        or now - datetime.fromisoformat(value["started_at"]) > timedelta(minutes=2)
    ):
        raise RuntimeError("DEMO_WINDOW_INVALID")
    old = load()
    if old and old.get("state") != "CLOSED":
        raise RuntimeError("DEMO_PREVIOUS_WINDOW_REQUIRES_CLOSE")
    quote = json.loads(Path("/etc/proofflow-repair/config.json").read_bytes())["quote"]
    if (
        quote["valid_until"] != value["quote_until"]
        or quote["model"] != "qwen3.8-flash-next"
        or quote["input_micro_usd_per_million"] != 100000
        or quote["output_micro_usd_per_million"] != 200000
    ):
        raise RuntimeError("DEMO_QUOTE_CHANGED")
    w = str(UUID(value["workspace_id"]))
    end = datetime.fromisoformat(value["expires_at"]).isoformat()
    ready = sql(
        "proofflow_product",  # noqa: S608 - parsed UUID/timestamp only
        "SELECT count(*)=1 AND bool_and(id='" + w + "' AND kind='guest' "  # noqa: S608
        "AND revoked_at IS NULL AND expires_at='" + end + "') FROM pf_product.workspaces;",
    )
    idle = sql(
        "proofflow_product",
        "SELECT NOT EXISTS(SELECT 1 FROM pf_product.execution_policy "
        "WHERE enabled) AND NOT EXISTS(SELECT 1 FROM pf_product.jobs WHERE state NOT IN "
        "('NEEDS_REVIEW','FAILED_INFRA','CANCELLED')) AND NOT EXISTS(SELECT 1 FROM "
        "pf_product.repairs WHERE state IN ('QUEUED','RUNNING','RECONCILING')) "
        "AND NOT EXISTS(SELECT 1 FROM pf_product.pr_intents WHERE lease_owner IS NOT NULL "
        "OR state IN ('BRANCH_PENDING','COMMIT_PENDING','PR_PENDING'));",
    )
    budget = sql(
        "proofflow_budget",
        "SELECT count(*)=1 AND bool_and(blocked AND "
        "project_limit=150000000 AND inference_limit=25000000) FROM pf_budget.accounts;",
    )
    if ready != b"t" or idle != b"t" or budget != b"t":
        raise RuntimeError("DEMO_REQUIRES_EXCLUSIVE_GUEST_CLOSED_IDLE_CAPS")
    policy = json.loads(
        sql("proofflow_product", "SELECT row_to_json(p) FROM pf_product.execution_policy p;")
    )
    if any(
        re.fullmatch("[0-9a-f]{64}", policy[k]) is None
        for k in ("runtime_sha256", "verifier_sha256")
    ):
        raise RuntimeError("DEMO_POLICY_IDENTITY_INVALID")
    save(value | {"state": "OPENING"})  # Durable intent before either admission opens.
    sql(
        "proofflow_product",
        "SELECT pf_product.configure_execution('"  # noqa: S608
        + policy["runtime_sha256"]
        + "','"
        + policy["verifier_sha256"]
        + "',true);",
    )
    sql(
        "proofflow_budget",
        "UPDATE pf_budget.accounts SET blocked=false WHERE blocked "
        "AND project_limit=150000000 AND inference_limit=25000000;",
    )
    save(value)
    return {"state": "ACTIVE", "expires_at": value["expires_at"]}


def main():
    import fcntl

    if os.geteuid() != 0 or sys.argv[1:] not in (["check"], ["arm"], ["close"]):
        raise RuntimeError("DEMO_ROOT_OPERATION_REQUIRED")
    os.umask(0o077)
    info = ROOT.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o700:
        raise RuntimeError("DEMO_ROOT_UNSAFE")
    fd = os.open(ROOT / "guard.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            now, boot = datetime.now(UTC), BOOT.read_text().strip()
            value = load()
            if sys.argv[1] == "arm":
                value = json.loads(sys.stdin.buffer.read(4097))
                result = arm(value, now, boot)
            elif sys.argv[1] == "close":
                result = close(value, "OPERATOR_CLOSED")
            elif value is None:
                result = {"state": "UNCONFIGURED"}
            elif value.get("state") == "CLOSED":
                result = {"state": "CLOSED"}
            elif not valid_window(value, now, boot):
                result = close(value, "EXPIRED_REBOOTED_OR_INVALID")
            else:
                result = {"state": "ACTIVE", "expires_at": value["expires_at"]}
            print(json.dumps(result))
        except Exception:
            try:
                close(None, "GUARD_FAILURE")
            except Exception:
                command(["/usr/bin/systemctl", "stop", "proofflow-product-dispatcher.service"])
            raise RuntimeError("DEMO_GUARD_FAILED_ADMISSION_STOPPED") from None


if __name__ == "__main__":
    main()
