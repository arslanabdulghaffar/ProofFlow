"""Quote refresh cannot change model/account/prices or extend freshness."""

import copy
import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from scripts.install_provider_quote import validate

NOW = datetime(2026, 11, 6, tzinfo=UTC)


def configs():
    old = {
        "account_id": str(uuid4()),
        "quote": {
            "model": "qwen3.8-flash-next",
            "input_micro_usd_per_million": 100000,
            "output_micro_usd_per_million": 200000,
            "evidence_sha256": "a" * 64,
            "observed_at": (NOW - timedelta(days=1)).isoformat(),
            "valid_until": NOW.isoformat(),
        },
    }
    new = copy.deepcopy(old)
    new["quote"].update(
        observed_at=NOW.isoformat(), valid_until=(NOW + timedelta(hours=1)).isoformat()
    )
    return old, new


@pytest.mark.parametrize(
    "fault",
    [
        "account",
        "model",
        "rate",
        "boolean_rate",
        "old_rate",
        "expired",
        "future",
        "long",
        "extra",
        "evidence",
    ],
)
def test_refuses_unreviewed_authority_rate_and_time_changes(fault):
    old, new = configs()
    validate(old, new, NOW)
    if fault == "account":
        new["account_id"] = str(uuid4())
    elif fault == "model":
        new["quote"]["model"] = "foreign"
    elif fault == "rate":
        new["quote"]["input_micro_usd_per_million"] += 1
    elif fault == "boolean_rate":
        new["quote"]["input_micro_usd_per_million"] = True
    elif fault == "old_rate":
        old["quote"]["input_micro_usd_per_million"] += 1
    elif fault == "expired":
        new["quote"]["valid_until"] = NOW.isoformat()
    elif fault == "future":
        new["quote"]["observed_at"] = (NOW + timedelta(seconds=1)).isoformat()
    elif fault == "long":
        new["quote"]["valid_until"] = (NOW + timedelta(hours=2)).isoformat()
    elif fault == "extra":
        new["credentials"] = "forbidden"
    else:
        new["quote"]["evidence_sha256"] = "missing"
    with pytest.raises(RuntimeError):
        validate(old, new, NOW)


@pytest.mark.skipif(os.name != "posix", reason="Linux administrator owner/mode checks")
def test_exact_predecessor_preserved_and_retry_refused(tmp_path, monkeypatch):
    from scripts import install_provider_quote as module

    old, new = configs()
    target = tmp_path / "config.json"
    raw = json.dumps(old, sort_keys=True).encode()
    target.write_bytes(raw)
    target.chmod(0o444)
    monkeypatch.setattr(module, "TARGET", target)
    payload = {"old_sha256": hashlib.sha256(raw).hexdigest(), "new": new}
    module.install(payload, NOW, check_only=True)
    assert target.read_bytes() == raw
    module.install(payload, NOW)
    assert json.loads(target.read_bytes()) == new
    assert [p.read_bytes() for p in tmp_path.glob("*.previous-*")] == [raw]
    with pytest.raises(RuntimeError, match="PREDECESSOR_CHANGED"):
        module.install(payload, NOW)
