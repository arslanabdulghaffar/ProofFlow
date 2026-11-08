# ruff: noqa: S608 - SQL interpolation uses parsed timestamps only
"""Fixed root timer: bounded judging admission and read-only provider quote refresh."""

import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from guest_demo_guard import BOOT, command, sql
from install_provider_quote import validate

ROOT = Path("/etc/proofflow-judging")
CONFIG = ROOT / "config.json"
QUOTE = Path("/etc/proofflow-repair/config.json")
FINAL = datetime(2026, 11, 23, tzinfo=UTC)


def allowed(config, now, boot):
    try:
        end = datetime.fromisoformat(config["funded_until"])
        start = datetime.fromisoformat(config["reviewed_at"])
        return (
            config["enabled"] is True
            and config["boot_id"] == boot
            and start <= now < end <= min(start + timedelta(hours=48), FINAL)
        )
    except (KeyError, TypeError, ValueError):
        return False


def close():
    sql("proofflow_product", "UPDATE pf_product.judge_admission SET available_until='-infinity';")
    sql("proofflow_budget", "UPDATE pf_budget.accounts SET blocked=true WHERE NOT blocked;")
    sql(
        "proofflow_product",
        "SELECT pf_product.configure_execution(runtime_sha256,"
        "verifier_sha256,false) FROM pf_product.execution_policy WHERE enabled;",
    )


def publish_quote(new):
    pending = QUOTE.with_suffix(".judging-pending")
    fd = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o444)
    with os.fdopen(fd, "wb") as stream:
        os.fchmod(stream.fileno(), 0o444)  # Root's 077 umask must not hide the public quote.
        stream.write(json.dumps(new, sort_keys=True).encode())
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(pending, QUOTE)
    parent = os.open(QUOTE.parent, os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(parent)
    finally:
        os.close(parent)


def run(now, *, arm=False):
    config = json.loads(CONFIG.read_bytes())
    if not allowed(config, now, BOOT.read_text().strip()):
        close()
        return {"judging": "closed", "reason": "FUNDED_WINDOW_OR_BOOT"}
    # Do not coexist with the manually armed single-guest window.
    manual = json.loads(Path("/etc/proofflow-guest-demo/window.json").read_bytes())
    if manual["state"] != "CLOSED":
        raise RuntimeError("MANUAL_WINDOW_ACTIVE")
    funded = datetime.fromisoformat(config["funded_until"]).isoformat()
    budget = sql(
        "proofflow_budget",
        "SELECT count(*)=1 AND bool_and(project_limit=150000000 AND inference_limit=25000000 "
        "AND "
        + ("blocked" if arm else "NOT blocked")
        + " AND expires_at='"
        + funded
        + "' AND expires_at>clock_timestamp()) FROM pf_budget.accounts;",
    )  # noqa: S608
    if budget != b"t":
        raise RuntimeError("JUDGING_BUDGET_CHANGED")
    old = json.loads(QUOTE.read_bytes())
    until = datetime.fromisoformat(old["quote"]["valid_until"])
    if until < now + timedelta(minutes=40):
        raw = command(
            [
                "/usr/bin/docker",
                "--host=unix:///var/run/docker.sock",
                "exec",
                "proofflow-product-dispatcher",
                "python",
                "-m",
                "orchestrator.judge_quote",
            ]
        )
        new = old | {"quote": json.loads(raw)}
        validate(old, new, datetime.now(UTC))
        publish_quote(new)
        until = datetime.fromisoformat(new["quote"]["valid_until"])
    if arm:
        sql("proofflow_budget", "UPDATE pf_budget.accounts SET blocked=false WHERE blocked;")
        sql(
            "proofflow_product",
            "SELECT pf_product.configure_execution(runtime_sha256,"
            "verifier_sha256,true) FROM pf_product.execution_policy WHERE NOT enabled;",
        )
    elif sql("proofflow_product", "SELECT enabled FROM pf_product.execution_policy;") != b"t":
        raise RuntimeError("JUDGING_EXECUTION_CLOSED")
    lease = min(
        now + timedelta(minutes=3),
        until - timedelta(minutes=35),
        datetime.fromisoformat(funded) - timedelta(minutes=35),
    ).isoformat()
    if config.get("draining", False):
        lease = now.isoformat()
    sql(
        "proofflow_product",
        "UPDATE pf_product.judge_admission SET available_until='"
        + lease
        + "',funded_until='"
        + funded
        + "' WHERE singleton;",
    )  # noqa: S608
    return {
        "judging": "draining" if config.get("draining", False) else "open",
        "admission_until": lease,
        "funded_until": funded,
        "quote_until": until.isoformat(),
        "completion_calls": 0,
    }


def main():
    import fcntl

    if os.geteuid() != 0 or sys.argv[1:] not in ([], ["close"], ["arm"], ["drain"]):
        raise RuntimeError("JUDGING_ROOT_REQUIRED")
    os.umask(0o077)
    with (ROOT / "guard.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            if sys.argv[1:] == ["close"]:
                config = json.loads(CONFIG.read_bytes())
                config["enabled"] = False
                CONFIG.write_text(json.dumps(config))
                close()
                result = {"judging": "closed"}
            else:
                if sys.argv[1:] == ["drain"]:
                    config = json.loads(CONFIG.read_bytes())
                    config["draining"] = True
                    CONFIG.write_text(json.dumps(config))
                result = run(datetime.now(UTC), arm=sys.argv[1:] == ["arm"])
            print(json.dumps(result))
        except Exception:
            # Never automatically clear a failed review/admission latch.
            try:
                try:
                    config = json.loads(CONFIG.read_bytes())
                    config["enabled"] = False
                    CONFIG.write_text(json.dumps(config))
                finally:
                    close()
            except Exception:
                command(["/usr/bin/systemctl", "stop", "proofflow-product-dispatcher.service"])
            raise SystemExit("JUDGING_GUARD_FAILED_CLOSED") from None


if __name__ == "__main__":
    main()
