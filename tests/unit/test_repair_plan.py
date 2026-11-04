"""Inert request identity/cost checks; no HTTP or model execution."""

import json
from datetime import UTC, datetime, timedelta

import pytest

from orchestrator.probe_plan import RateQuote, prepare_json_probe
from orchestrator.repair_proposal import RepairRejected
from orchestrator.repair_provider import prepare_repair_plan


def test_reasoning_bound_is_hash_bound_inside_unchanged_output_and_cost_cap():
    now = datetime.now(UTC)
    quote = RateQuote("qwen3.8-flash-next", 100000, 200000, now, now + timedelta(hours=1), "a" * 64)
    before = prepare_json_probe("inert request", quote, max_completion_tokens=8192, now=now)
    after = prepare_repair_plan("inert request", quote, now)
    payload = json.loads(after.payload)
    assert payload["reasoning"] == {"enabled": False}
    assert payload["max_completion_tokens"] == 8192
    assert after.reserve_micro_usd == before.reserve_micro_usd == 27853
    assert after.request_sha256 != before.request_sha256
    assert after.quote_sha256 == before.quote_sha256
    assert after.endpoint == before.endpoint and "tools" not in payload
    with pytest.raises(RepairRejected):
        prepare_repair_plan(
            "inert",
            RateQuote("qwen3.8-27b", 150000, 1000000, now, now + timedelta(hours=1), "a" * 64),
            now,
        )
