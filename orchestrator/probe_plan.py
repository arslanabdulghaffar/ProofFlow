"""Offline Vultr JSON-probe preparation, never network or spending authorization.

Rates/validity are supplied by trusted reviewed configuration, not a user/model.
The billing gate and a committed single-use ledger claim are still prerequisites
for a future dispatcher. This module does not attest that a quote is genuine.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime

VULTR_CHAT_URL = "https://api.vultrinference.com/v1/chat/completions"
PROBE_MODELS = ("qwen3.8-27b", "qwen3.8-flash-next")
MAX_PROMPT_BYTES = 16 * 1024
MAX_COMPLETION_TOKENS = 8192
# Conservative full 256 Ki-token context allowance, not a token-count estimate.
INPUT_TOKEN_BOUND = 262144
SYSTEM_PROMPT = "Return one JSON object answering the request. Do not use tools."


@dataclass(frozen=True)
class RateQuote:
    model: str
    input_micro_usd_per_million: int
    output_micro_usd_per_million: int
    observed_at: datetime
    valid_until: datetime
    evidence_sha256: str


@dataclass(frozen=True)
class ProbePlan:
    endpoint: str
    payload: bytes
    request_sha256: str
    reserve_micro_usd: int
    quote_sha256: str
    quote_payload: bytes


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _aware(value: datetime) -> bool:
    return (isinstance(value, datetime) and value.tzinfo is not None
            and value.utcoffset() is not None)


def prepare_json_probe(
    prompt: str, quote: RateQuote, *, max_completion_tokens: int, now: datetime,
) -> ProbePlan:
    """Bound an inert JSON request and its worst-case token charge using integers."""
    if type(prompt) is not str or not prompt or len(prompt.encode("utf-8")) > MAX_PROMPT_BYTES:
        raise ValueError("INVALID_PROBE_PROMPT")
    if quote.model not in PROBE_MODELS:
        raise ValueError("UNAPPROVED_PROBE_MODEL")
    if (type(max_completion_tokens) is not int
            or not 1 <= max_completion_tokens <= MAX_COMPLETION_TOKENS):
        raise ValueError("INVALID_COMPLETION_BOUND")
    for rate in (quote.input_micro_usd_per_million, quote.output_micro_usd_per_million):
        if type(rate) is not int or not 1 <= rate <= 1_000_000_000:
            raise ValueError("INVALID_RATE")
    if (not all(_aware(t) for t in (now, quote.observed_at, quote.valid_until))
            or not quote.observed_at <= now < quote.valid_until):
        raise ValueError("QUOTE_NOT_CURRENT")
    if not re.fullmatch("[a-f0-9]{64}", quote.evidence_sha256):
        raise ValueError("INVALID_QUOTE_EVIDENCE")
    quote_bytes = _canonical({
        "model": quote.model, "input_rate": quote.input_micro_usd_per_million,
        "output_rate": quote.output_micro_usd_per_million,
        "observed_at": quote.observed_at.astimezone(UTC).isoformat(),
        "valid_until": quote.valid_until.astimezone(UTC).isoformat(),
        "evidence_sha256": quote.evidence_sha256, "input_token_bound": INPUT_TOKEN_BOUND,
    })
    quote_digest = hashlib.sha256(quote_bytes).hexdigest()
    cost_numerator = (INPUT_TOKEN_BOUND * quote.input_micro_usd_per_million
                      + max_completion_tokens * quote.output_micro_usd_per_million)
    reserve = (cost_numerator + 999999) // 1000000
    if reserve > 2_000_000:
        raise ValueError("PROBE_ALLOCATION_EXCEEDED")
    payload = _canonical({
        "model": quote.model,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                     {"role": "user", "content": prompt}],
        "n": 1, "stream": False, "temperature": 0,
        "response_format": {"type": "json_object"},
        "max_completion_tokens": max_completion_tokens,
    })
    envelope = _canonical({
        "endpoint": VULTR_CHAT_URL, "method": "POST",
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "quote_sha256": quote_digest, "reserve_micro_usd": reserve,
    })
    return ProbePlan(VULTR_CHAT_URL, payload, hashlib.sha256(envelope).hexdigest(),
                     reserve, quote_digest, quote_bytes)
