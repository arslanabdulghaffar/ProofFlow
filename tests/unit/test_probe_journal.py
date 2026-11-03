"""Inert saved-response recovery tests; no database or provider connection."""

import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from orchestrator.budget_store import BudgetUnavailable
from orchestrator.probe_journal import recover_response
from orchestrator.probe_plan import RateQuote, prepare_json_probe
from tests.unit.test_probe_response import envelope


def saved():
    now = datetime.now(UTC)
    quote = RateQuote("qwen3.8-27b", 150000, 1000000, now,
                      now + timedelta(minutes=2), "b" * 64)
    plan = prepare_json_probe("Return JSON", quote, max_completion_tokens=512, now=now)
    request = uuid4()
    raw = json.dumps(envelope()).encode()
    encode = lambda value: base64.encodebytes(value).decode()  # noqa: E731
    snapshot = dict(request_id=str(request), request_sha256=plan.request_sha256,
                    payload_base64=encode(plan.payload), quote_base64=encode(plan.quote_payload),
                    reserve_micro_usd=plan.reserve_micro_usd, state="RECORDED",
                    outcome="PARSED_RESPONSE", http_status=200, response_base64=encode(raw),
                    response_sha256=hashlib.sha256(raw).hexdigest())
    return snapshot, request, plan


def test_recover_rechecks_exact_saved_bytes_without_http():
    snapshot, request, plan = saved()
    assert recover_response(snapshot, request, plan).content_json == b'{"answer":7}'


@pytest.mark.parametrize("field,value", [
    ("request_id", str(uuid4())), ("request_sha256", "c" * 64), ("state", "PREPARED"),
    ("outcome", "OUTCOME_UNKNOWN"), ("http_status", 201), ("reserve_micro_usd", 1),
    ("response_sha256", "d" * 64), ("response_base64", "invalid!"),
    ("payload_base64", "e30="), ("quote_base64", "e30="),
    ("response_base64", "A" * 524289),
])
def test_tampered_or_incomplete_receipt_never_recovers(field, value):
    snapshot, request, plan = saved()
    snapshot[field] = value
    with pytest.raises(BudgetUnavailable, match="PROBE_RECEIPT_INVALID"):
        recover_response(snapshot, request, plan)
