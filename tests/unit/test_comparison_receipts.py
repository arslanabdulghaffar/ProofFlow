"""Synthetic immutable receipt/ledger tampering; no provider requests or source execution."""

import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from eval.comparison_receipts import call, product_call
from orchestrator.probe_plan import RateQuote
from orchestrator.repair_provider import prepare_repair_plan


def fixture():
    now = datetime.now(UTC)
    quote = RateQuote("qwen3.8-flash-next", 100000, 200000, now, now + timedelta(hours=1), "a" * 64)
    plan = prepare_repair_plan("inert synthetic prompt", quote, now)
    identifier, account = str(uuid4()), str(uuid4())
    intent = {
        "request_id": identifier,
        "request_sha256": plan.request_sha256,
        "reserve_micro_usd": plan.reserve_micro_usd,
        "payload_base64": base64.b64encode(plan.payload).decode(),
        "quote_base64": base64.b64encode(plan.quote_payload).decode(),
    }
    body = json.dumps(
        {
            "id": "chatcmpl-synthetic",
            "object": "chat.completion",
            "model": quote.model,
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "{}"},
                }
            ],
            "usage": {"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70},
        }
    ).encode()
    response = {
        "request_sha256": plan.request_sha256,
        "outcome": "PARSED_RESPONSE",
        "http_status": 200,
        "response_base64": base64.b64encode(body).decode(),
        "response_sha256": hashlib.sha256(body).hexdigest(),
    }
    reservation = {
        "id": identifier,
        "account_id": account,
        "request_hash": plan.request_sha256,
        "purpose": "inference",
        "reserved_micro": plan.reserve_micro_usd,
        "valid_until": quote.valid_until.isoformat(),
        "claimed_at": now.isoformat(),
    }
    return intent, response, reservation, account


def test_request_ledger_usage_bound_and_sql_translation():
    intent, response, reservation, account = fixture()
    checked = call(intent, response, reservation, account_id=account)
    assert checked["confirmed_http"] and checked["claimed"]
    assert checked["estimated_micro_usd"] == 9
    assert checked["reserved_micro_usd"] == checked["global_reserved_micro_usd"] == 27853
    row = {
        "request_id": intent["request_id"],
        "request_sha256": intent["request_sha256"],
        "reserved_micro": intent["reserve_micro_usd"],
        "outcome": response["outcome"],
        "http_status": 200,
        "payload": "\\x" + base64.b64decode(intent["payload_base64"]).hex(),
        "quote": "\\x" + base64.b64decode(intent["quote_base64"]).hex(),
        "response": "\\x" + base64.b64decode(response["response_base64"]).hex(),
    }
    translated = product_call(row)
    assert call(*translated, reservation, account_id=account) == checked


@pytest.mark.parametrize(
    "target,key,value",
    [
        ("intent", "request_sha256", "f" * 64),
        ("intent", "reserve_micro_usd", 1),
        ("intent", "payload_base64", "e30="),
        ("response", "response_sha256", "f" * 64),
        ("response", "request_sha256", "f" * 64),
        ("response", "http_status", 500),
        ("reservation", "purpose", "compute"),
        ("reservation", "request_hash", "f" * 64),
        ("reservation", "reserved_micro", 1),
        ("reservation", "claimed_at", None),
        ("reservation", "account_id", str(uuid4())),
    ],
)
def test_tampering_rejected(target, key, value):
    intent, response, reservation, account = fixture()
    {"intent": intent, "response": response, "reservation": reservation}[target][key] = value
    with pytest.raises((ValueError, KeyError)):
        call(intent, response, reservation, account_id=account)


def test_unknown_delivery_stays_unknown_without_settling_reservation():
    intent, response, reservation, account = fixture()
    response.update(
        outcome="OUTCOME_UNKNOWN", http_status=None, response_base64=None, response_sha256=None
    )
    checked = call(intent, response, reservation, account_id=account)
    assert checked["estimated_micro_usd"] is None and not checked["confirmed_http"]
    assert checked["global_reserved_micro_usd"] == 27853
    not_claimed = call(intent, response, None, account_id=account)
    assert not_claimed["global_reserved_micro_usd"] == 0 and not not_claimed["claimed"]
    assert not_claimed["reserved_micro_usd"] == 27853  # Conservative local book, not billing.


def test_missing_usage_does_not_become_zero():
    intent, response, reservation, account = fixture()
    body = json.loads(base64.b64decode(response["response_base64"]))
    del body["usage"]
    raw = json.dumps(body).encode()
    response.update(
        response_base64=base64.b64encode(raw).decode(),
        response_sha256=hashlib.sha256(raw).hexdigest(),
    )
    checked = call(intent, response, reservation, account_id=account)
    assert checked["confirmed_http"] and checked["input_tokens"] is None
    assert checked["estimated_micro_usd"] is None


def test_candidate_provenance_hash_is_data_only():
    intent, response, reservation, account = fixture()
    source = "deliberately inert non-Python source text"
    body = json.loads(base64.b64decode(response["response_base64"]))
    body["choices"][0]["message"]["content"] = json.dumps(
        {
            "kind": "propose_patch",
            "diagnosis": "synthetic",
            "changed_file": "pipeline.py",
            "candidate_source": source,
            "expected_effect": "synthetic",
            "uncertainties": [],
        }
    )
    raw = json.dumps(body).encode()
    response.update(
        response_base64=base64.b64encode(raw).decode(),
        response_sha256=hashlib.sha256(raw).hexdigest(),
    )
    checked = call(intent, response, reservation, account_id=account)
    assert checked["proposal_kind"] == "propose_patch"
    assert checked["candidate_sha256"] == hashlib.sha256(source.encode()).hexdigest()
