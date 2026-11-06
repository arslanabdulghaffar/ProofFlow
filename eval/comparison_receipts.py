"""Offline receipt reconciliation. Never executes source or changes an evaluation grade."""

import base64
import hashlib
import json
from datetime import datetime
from uuid import UUID

from eval.report import digest
from orchestrator.probe_plan import VULTR_CHAT_URL
from orchestrator.probe_response import parse_probe_response
from orchestrator.repair_proposal import (
    COMPLETION_TOKENS,
    PROMPT_TOKEN_RESERVE,
    RepairRejected,
    parse_proposal,
)


def require(value):
    if not value:
        raise ValueError("COMPARISON_RECEIPT_MISMATCH")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def call(intent, response, reservation, *, account_id):
    """Recompute request identity and costs from immutable bytes and the actual ledger.

    Prepared requests are not automatically confirmed HTTP calls. Uncertain usage
    stays unknown and local reservations remain conservative; no ledger settlement.
    """
    request = str(UUID(intent["request_id"]))
    payload = base64.b64decode(intent["payload_base64"], validate=True)
    quote_raw = base64.b64decode(intent["quote_base64"], validate=True)
    require(len(payload) <= 102400 and len(quote_raw) <= 4096)
    quoted, sent = json.loads(quote_raw), json.loads(payload)
    require(
        quoted["model"] == sent["model"] == "qwen3.8-flash-next"
        and quoted["input_rate"] == 100000
        and quoted["output_rate"] == 200000
        and quoted["input_token_bound"] == 262144
        and sent["max_completion_tokens"] == COMPLETION_TOKENS
        and sent["reasoning"] == {"enabled": False}
    )
    amount = (
        quoted["input_token_bound"] * quoted["input_rate"]
        + COMPLETION_TOKENS * quoted["output_rate"]
        + 999999
    ) // 1000000
    require(type(intent["reserve_micro_usd"]) is int and intent["reserve_micro_usd"] == amount)
    envelope = {
        "endpoint": VULTR_CHAT_URL,
        "method": "POST",
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "quote_sha256": hashlib.sha256(quote_raw).hexdigest(),
        "reserve_micro_usd": amount,
    }
    require(hashlib.sha256(canonical(envelope)).hexdigest() == intent["request_sha256"])
    result = {
        "request": request,
        "reserved_micro_usd": amount,
        "global_reserved_micro_usd": 0,
        "input_tokens": None,
        "output_tokens": None,
        "estimated_micro_usd": None,
        "confirmed_http": False,
        "claimed": False,
        "response_sha256": None,
        "proposal_kind": None,
        "candidate_sha256": None,
    }
    if reservation is not None:
        require(
            reservation["id"] == request
            and reservation["account_id"] == str(UUID(account_id))
            and reservation["request_hash"] == intent["request_sha256"]
            and reservation["purpose"] == "inference"
            and reservation["reserved_micro"] == amount
            and datetime.fromisoformat(reservation["valid_until"])
            == datetime.fromisoformat(quoted["valid_until"])
        )
        result.update(
            global_reserved_micro_usd=amount, claimed=reservation["claimed_at"] is not None
        )
    if response is None:
        return result
    require(response["request_sha256"] == intent["request_sha256"])
    body = (
        None
        if response["response_base64"] is None
        else base64.b64decode(response["response_base64"], validate=True)
    )
    require(body is None or len(body) <= 262144)
    require(
        response["response_sha256"] == (None if body is None else hashlib.sha256(body).hexdigest())
    )
    require(response["outcome"] in ("PARSED_RESPONSE", "OUTCOME_UNKNOWN"))
    if response["outcome"] != "PARSED_RESPONSE":
        return result
    require(response["http_status"] == 200 and result["claimed"])
    parsed = parse_probe_response(body, model=quoted["model"], completion_bound=COMPLETION_TOKENS)
    result.update(confirmed_http=True, response_sha256=parsed.response_sha256)
    try:
        proposal = parse_proposal(parsed.content_json)
        result.update(proposal_kind=proposal.kind, candidate_sha256=proposal.sha256)
    except RepairRejected:
        pass  # Invalid proposals still count as real calls, never as valid candidates.
    if parsed.usage is None or parsed.usage.prompt_tokens > PROMPT_TOKEN_RESERVE:
        return result
    usage = parsed.usage
    estimated = (
        usage.prompt_tokens * quoted["input_rate"]
        + usage.completion_tokens * quoted["output_rate"]
        + 999999
    ) // 1000000
    require(estimated <= amount)
    result.update(
        input_tokens=usage.prompt_tokens,
        output_tokens=usage.completion_tokens,
        estimated_micro_usd=estimated,
    )
    return result


def product_call(row):
    """Translate saved SQL bytea without reading credentials or executing proposals."""
    require(all(type(row[k]) is str and row[k].startswith("\\x") for k in ("payload", "quote")))
    require(
        row["response"] is None
        or (type(row["response"]) is str and row["response"].startswith("\\x"))
    )
    payload, quote = bytes.fromhex(row["payload"][2:]), bytes.fromhex(row["quote"][2:])
    intent = {
        "request_id": row["request_id"],
        "request_sha256": row["request_sha256"],
        "reserve_micro_usd": row["reserved_micro"],
        "payload_base64": base64.b64encode(payload).decode(),
        "quote_base64": base64.b64encode(quote).decode(),
    }
    if row["outcome"] is None:
        return intent, None
    raw = None if row["response"] is None else bytes.fromhex(row["response"][2:])
    response = {
        "request_sha256": row["request_sha256"],
        "outcome": row["outcome"],
        "response_base64": None if raw is None else base64.b64encode(raw).decode(),
        "response_sha256": None if raw is None else hashlib.sha256(raw).hexdigest(),
        "http_status": row["http_status"],
    }
    return intent, response


def record(plan, job, result, calls, evidence_hash, *, reconciled_cleanup=None):
    """Normalize measured fields only. Require a separate proof audit before scoring."""
    require(all(result[k] == job[k] for k in job))
    require(len(calls) <= 3 and len({c["request"] for c in calls}) == len(calls))
    known = all(c["estimated_micro_usd"] is not None for c in calls)
    # A prepared attempt may have failed before being persisted. Do not invent a call.
    require({c["request"] for c in calls} <= {c["request"] for c in result["calls"]})
    require(
        reconciled_cleanup is None or (result.get("critical") and reconciled_cleanup == "confirmed")
    )
    return {
        "plan_sha256": digest(plan),
        **job,
        "decision": result["decision"],
        "grade": result["grade"],
        "cleanup": reconciled_cleanup or result["cleanup"],
        "latency_ms": result["elapsed_ms"],
        "calls": len(calls),
        "input_tokens": sum(c["input_tokens"] for c in calls) if known else None,
        "output_tokens": sum(c["output_tokens"] for c in calls) if known else None,
        "reserved_micro_usd": sum(c["reserved_micro_usd"] for c in calls),
        "estimated_micro_usd": sum(c["estimated_micro_usd"] for c in calls) if known else None,
        "receipt_sha256": evidence_hash,
    }
