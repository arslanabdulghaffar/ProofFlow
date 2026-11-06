"""Exact reviewed quote refresh on a stopped dispatcher; never changes credentials/account/rates."""

import hashlib
import json
import os
import re
import stat
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

TARGET = Path("/etc/proofflow-repair/config.json")


def validate(old, new, now):
    if (
        set(old) != {"account_id", "quote"}
        or set(new) != set(old)
        or str(UUID(new["account_id"])) != old["account_id"]
    ):
        raise RuntimeError("QUOTE_ACCOUNT_CHANGED")
    quote = new["quote"]
    fields = {
        "model",
        "input_micro_usd_per_million",
        "output_micro_usd_per_million",
        "observed_at",
        "valid_until",
        "evidence_sha256",
    }
    if (
        set(quote) != fields
        or quote["model"] != old["quote"]["model"]
        or quote["model"] != "qwen3.8-flash-next"
        or type(quote["input_micro_usd_per_million"]) is not int
        or type(quote["output_micro_usd_per_million"]) is not int
        or quote["input_micro_usd_per_million"] != 100000
        or quote["output_micro_usd_per_million"] != 200000
        or any(
            quote[k] != old["quote"][k]
            for k in ("input_micro_usd_per_million", "output_micro_usd_per_million")
        )
        or re.fullmatch("[a-f0-9]{64}", quote["evidence_sha256"]) is None
    ):
        raise RuntimeError("QUOTE_MODEL_OR_RATE_CHANGED")
    observed = datetime.fromisoformat(quote["observed_at"])
    until = datetime.fromisoformat(quote["valid_until"])
    if not now - timedelta(minutes=5) <= observed <= now < until <= observed + timedelta(hours=1):
        raise RuntimeError("QUOTE_FRESHNESS_INVALID")


def install(value, now, *, check_only=False):
    if set(value) != {"old_sha256", "new"}:
        raise RuntimeError("QUOTE_UPDATE_FIELDS_INVALID")
    info = TARGET.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or info.st_uid != 0
        or stat.S_IMODE(info.st_mode) != 0o444
    ):
        raise RuntimeError("QUOTE_FILE_UNSAFE")
    raw = TARGET.read_bytes()
    if hashlib.sha256(raw).hexdigest() != value["old_sha256"]:
        raise RuntimeError("QUOTE_PREDECESSOR_CHANGED")
    validate(json.loads(raw), value["new"], now)
    if check_only:
        return
    backup = TARGET.with_name(TARGET.name + ".previous-" + value["old_sha256"])
    fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
    with os.fdopen(fd, "wb") as output:
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())
    pending = TARGET.with_name(TARGET.name + ".quote-pending")
    fd = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o444)
    with os.fdopen(fd, "wb") as output:
        output.write(json.dumps(value["new"], sort_keys=True).encode())
        output.flush()
        os.fchmod(output.fileno(), 0o444)
        os.fsync(output.fileno())
    os.replace(pending, TARGET)
    fd = os.open(TARGET.parent, os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


if __name__ == "__main__":
    try:
        if os.geteuid() != 0 or sys.argv[1:] not in ([], ["--check-only"]):
            raise RuntimeError("QUOTE_UPDATE_ADMIN_REQUIRED")
        install(
            json.load(sys.stdin), datetime.now(UTC), check_only=sys.argv[1:] == ["--check-only"]
        )
        print("QUOTE_CONFIGURATION_CHECKED")
    except Exception:
        raise SystemExit("QUOTE_UPDATE_STOPPED_RECONCILE_NO_RETRY") from None
