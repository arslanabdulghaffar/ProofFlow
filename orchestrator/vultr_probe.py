"""Internal Phase 1 client. No route, CLI, secret loading or activation switch.

Only a trusted deployment composition may call this after billing/account gates.
No retry, fallback, arbitrary URL, tool dispatch, candidate execution or settlement.
"""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import httpx

from orchestrator.budget_store import PostgresBudget
from orchestrator.probe_journal import ProbeJournal
from orchestrator.probe_plan import VULTR_CHAT_URL, RateQuote, prepare_json_probe
from orchestrator.probe_response import MAX_RESPONSE_BYTES, ProbeResponse, parse_probe_response

MAX_REQUEST_SECONDS = 60


class ProbeDispatchError(Exception):
    """Fixed diagnostic; request secrets and provider bodies are never included."""


async def run_json_probe(
    *, budget: PostgresBudget, request_id: UUID, prompt: str, quote: RateQuote,
    max_completion_tokens: int, api_key: str,
) -> ProbeResponse:
    if (type(api_key) is not str or not 1 <= len(api_key) <= 512
            or any(not 33 <= ord(char) <= 126 for char in api_key)):
        raise ProbeDispatchError("INVALID_PROVIDER_SECRET")
    now = datetime.now(UTC)
    plan = prepare_json_probe(prompt, quote, max_completion_tokens=max_completion_tokens, now=now)
    seconds = min(MAX_REQUEST_SECONDS, (quote.valid_until - now).total_seconds())
    loop = asyncio.get_running_loop()
    started = loop.time()
    deadline = started + seconds
    journal = ProbeJournal(budget)
    prepared = False
    raw_body = None
    http_status = None
    try:
        # Covers budget operations, DNS/TLS, headers and entire response drain.
        async with asyncio.timeout_at(deadline):
            if not await journal.prepare(request_id, plan):
                raise ProbeDispatchError("PROBE_ALREADY_RECORDED")
            prepared = True
            await budget.reserve(request_id, plan.request_sha256, plan.reserve_micro_usd,
                                 quote.valid_until)
            if not await budget.claim(request_id, plan.request_sha256):
                raise ProbeDispatchError("PROBE_ALREADY_CLAIMED")
            # Claims are consumed even if the quote expires just before transport.
            remaining = (quote.valid_until - datetime.now(UTC)).total_seconds()
            if remaining <= 0:
                raise ProbeDispatchError("QUOTE_EXPIRED_BEFORE_SEND")
            async with httpx.AsyncClient(
                verify=True, trust_env=False, follow_redirects=False,
                timeout=httpx.Timeout(min(seconds, remaining), connect=min(5, remaining)),
                limits=httpx.Limits(max_connections=1, max_keepalive_connections=0),
            ) as client:
                async with client.stream(
                    "POST", VULTR_CHAT_URL, content=plan.payload,
                    headers={"Authorization": "Bearer " + api_key,
                             "Content-Type": "application/json", "Accept": "application/json",
                             "Accept-Encoding": "identity"},
                ) as response:
                    http_status = response.status_code
                    if response.status_code != 200:
                        raise ProbeDispatchError("PROVIDER_HTTP_REJECTED")
                    if (response.headers.get("content-type", "").split(";")[0].strip().lower()
                            != "application/json"
                            or response.headers.get("content-encoding", "identity").lower()
                            != "identity"):
                        raise ProbeDispatchError("UNSUPPORTED_PROVIDER_ENCODING")
                    length = response.headers.get("content-length")
                    if length is not None and (not length.isascii() or not length.isdecimal()
                                               or len(length) > 9
                                               or int(length) > MAX_RESPONSE_BYTES):
                        raise ProbeDispatchError("PROVIDER_RESPONSE_TOO_LARGE")
                    body = bytearray()
                    async for chunk in response.aiter_raw(chunk_size=4096):
                        if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                            raise ProbeDispatchError("PROVIDER_RESPONSE_TOO_LARGE")
                        body.extend(chunk)
            raw_body = bytes(body)
            parsed = parse_probe_response(raw_body, model=quote.model,
                                          completion_bound=max_completion_tokens)
            # Synchronous bounded parsing cannot yield to asyncio's timeout callback.
            if loop.time() >= deadline or datetime.now(UTC) >= quote.valid_until:
                raise ProbeDispatchError("PROVIDER_OUTCOME_UNCERTAIN")
            await journal.record(request_id, plan, "PARSED_RESPONSE", raw_body,
                                 http_status, int((loop.time() - started) * 1000))
            return parsed
    except BaseException as error:
        if prepared:
            # Unknown/lost result commit may already have persisted PARSED_RESPONSE.
            # Immutable record rejects a contradictory rewrite; recovery reads it,
            # never repeats a network request. No body/exception text enters errors.
            try:
                await journal.record(request_id, plan, "OUTCOME_UNKNOWN", raw_body,
                                     http_status, int((loop.time() - started) * 1000))
            except Exception:
                raise ProbeDispatchError("PROBE_RECEIPT_WRITE_UNCERTAIN") from None
        if isinstance(error, (httpx.HTTPError, OSError, TimeoutError)):
            raise ProbeDispatchError("PROVIDER_OUTCOME_UNCERTAIN") from None
        raise
