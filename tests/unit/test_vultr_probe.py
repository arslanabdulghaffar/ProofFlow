"""Explicit mock transport/ledger tests. No network, credentials or paid calls."""

import asyncio
import json
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest

from orchestrator import vultr_probe
from orchestrator.budget_store import BudgetUnavailable
from orchestrator.probe_plan import RateQuote
from orchestrator.probe_response import MAX_RESPONSE_BYTES
from tests.unit.test_probe_response import envelope


class FixtureBudget:
    def __init__(self, *, fail=None, claimed=False):
        self.events = []
        self.fail = fail
        self.claimed = claimed

    async def reserve(self, request_id, digest, amount, deadline):
        self.events.append("reserve_committed")
        if self.fail == "reserve":
            raise BudgetUnavailable("FIXTURE_RESERVE_UNCERTAIN")
        return True

    async def claim(self, request_id, digest):
        self.events.append("claim_committed")
        if self.fail == "claim":
            raise BudgetUnavailable("FIXTURE_COMMIT_ACK_LOST")
        if self.claimed:
            return False
        self.claimed = True
        return True


class FixtureJournal:
    def __init__(self, budget):
        self.budget = budget
        self.records = []
        self.fail = None
        self.prepared = False

    async def prepare(self, request_id, plan):
        if self.fail == "prepare":
            raise BudgetUnavailable("FIXTURE_RECEIPT_COMMIT_UNCERTAIN")
        if self.prepared:
            return False
        self.prepared = True
        return True

    async def record(self, *args):
        if self.fail == "record":
            raise BudgetUnavailable("FIXTURE_RECEIPT_COMMIT_UNCERTAIN")
        self.records.append(args)
        return True


class FixtureStream(httpx.AsyncByteStream):
    def __init__(self, chunks, delay=0):
        self.chunks, self.delay, self.closed = chunks, delay, False

    async def __aiter__(self):
        for chunk in self.chunks:
            if self.delay:
                await asyncio.sleep(self.delay)
            yield chunk

    async def aclose(self):
        self.closed = True


def install_transport(monkeypatch, budget, *, status=200, headers=None, stream=None, error=None):
    journal = FixtureJournal(budget)
    budget.journal = journal
    monkeypatch.setattr(vultr_probe, "ProbeJournal", lambda bound: journal)
    real_client = httpx.AsyncClient
    captured = []
    stream = stream or FixtureStream([json.dumps(envelope()).encode()])

    async def handler(request):
        assert budget.events == ["reserve_committed", "claim_committed"]
        captured.append(request)
        if error:
            raise error
        return httpx.Response(status, headers=headers or {"content-type": "application/json"},
                              stream=stream)

    def factory(**kwargs):
        assert kwargs["verify"] is True and kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        return real_client(**kwargs, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(vultr_probe.httpx, "AsyncClient", factory)
    return captured, stream


def run(budget, *, request_id=None, header_value="synthetic-fixture-no-credential"):
    now = datetime.now(UTC)
    quote = RateQuote("qwen3.8-27b", 150000, 1000000, now - timedelta(minutes=1),
                      now + timedelta(minutes=1), "a" * 64)
    return asyncio.run(vultr_probe.run_json_probe(
        budget=budget, request_id=request_id or uuid4(), prompt="Return a JSON object.",
        quote=quote, max_completion_tokens=512, api_key=header_value,
    ))


def test_committed_claim_precedes_one_fixed_endpoint_request(monkeypatch):
    budget = FixtureBudget()
    captured, stream = install_transport(monkeypatch, budget)
    result = run(budget)
    assert result.content_json == b'{"answer":7}' and stream.closed
    assert len(captured) == 1
    request = captured[0]
    assert str(request.url) == "https://api.vultrinference.com/v1/chat/completions"
    assert request.method == "POST" and request.headers["accept-encoding"] == "identity"
    assert json.loads(request.content)["max_completion_tokens"] == 512


@pytest.mark.parametrize("failure", ["reserve", "claim", "already_claimed"])
def test_budget_uncertainty_or_replay_never_sends(monkeypatch, failure):
    budget = FixtureBudget(fail=failure, claimed=failure == "already_claimed")
    captured, _ = install_transport(monkeypatch, budget)
    with pytest.raises((BudgetUnavailable, vultr_probe.ProbeDispatchError)):
        run(budget)
    assert captured == []


@pytest.mark.parametrize("status", [301, 307, 400, 401, 429, 500])
def test_rejection_never_follows_or_retries_or_exposes_body(monkeypatch, status):
    budget = FixtureBudget()
    captured, stream = install_transport(monkeypatch, budget, status=status,
                                        stream=FixtureStream([b"private-error-content"]))
    with pytest.raises(vultr_probe.ProbeDispatchError, match="^PROVIDER_HTTP_REJECTED$"):
        run(budget)
    assert len(captured) == 1 and stream.closed and budget.claimed


@pytest.mark.parametrize("headers", [
    {"content-type": "text/html"},
    {"content-type": "application/json", "content-encoding": "gzip"},
    {"content-type": "application/json", "content-length": "9999999"},
])
def test_unsupported_encoding_and_declared_oversize_fail(monkeypatch, headers):
    budget = FixtureBudget()
    _, stream = install_transport(monkeypatch, budget, headers=headers)
    with pytest.raises(vultr_probe.ProbeDispatchError):
        run(budget)
    assert stream.closed


def test_actual_body_bound_without_content_length(monkeypatch):
    budget = FixtureBudget()
    _, stream = install_transport(monkeypatch, budget,
                                  stream=FixtureStream([b"x" * 4096] * 65))
    assert 65 * 4096 > MAX_RESPONSE_BYTES
    with pytest.raises(vultr_probe.ProbeDispatchError, match="PROVIDER_RESPONSE_TOO_LARGE"):
        run(budget)
    assert stream.closed


def test_slow_stream_absolute_deadline_closes_and_retains_claim(monkeypatch):
    monkeypatch.setattr(vultr_probe, "MAX_REQUEST_SECONDS", 0.03)
    budget = FixtureBudget()
    captured, stream = install_transport(monkeypatch, budget,
                                        stream=FixtureStream([b"x"] * 100, delay=0.02))
    with pytest.raises(vultr_probe.ProbeDispatchError, match="PROVIDER_OUTCOME_UNCERTAIN"):
        run(budget)
    assert len(captured) == 1 and stream.closed and budget.claimed


def test_transport_error_is_fixed_and_not_retried(monkeypatch):
    budget = FixtureBudget()
    captured, _ = install_transport(monkeypatch, budget,
                                    error=httpx.ConnectError("private-error-content"))
    with pytest.raises(vultr_probe.ProbeDispatchError, match="^PROVIDER_OUTCOME_UNCERTAIN$"):
        run(budget)
    assert len(captured) == 1 and budget.claimed


def test_synchronous_parse_cannot_return_success_after_deadline(monkeypatch):
    original = vultr_probe.parse_probe_response

    def delayed_parse(*args, **kwargs):
        time.sleep(0.04)  # Explicit local fault injection, not a slow provider result.
        return original(*args, **kwargs)

    monkeypatch.setattr(vultr_probe, "MAX_REQUEST_SECONDS", 0.02)
    monkeypatch.setattr(vultr_probe, "parse_probe_response", delayed_parse)
    budget = FixtureBudget()
    _, stream = install_transport(monkeypatch, budget)
    with pytest.raises(vultr_probe.ProbeDispatchError, match="PROVIDER_OUTCOME_UNCERTAIN"):
        run(budget)
    assert stream.closed and budget.claimed


def test_header_injection_rejected_before_reservation(monkeypatch):
    budget = FixtureBudget()
    captured, _ = install_transport(monkeypatch, budget)
    with pytest.raises(vultr_probe.ProbeDispatchError, match="INVALID_PROVIDER_SECRET"):
        run(budget, header_value="fixture\r\nInjected: true")
    assert captured == [] and budget.events == []


def test_receipt_failure_before_dispatch_prevents_http(monkeypatch):
    budget = FixtureBudget()
    captured, _ = install_transport(monkeypatch, budget)
    budget.journal.fail = "prepare"
    with pytest.raises(BudgetUnavailable):
        run(budget)
    assert not captured and not budget.events


def test_success_waits_for_durable_result_and_write_failure_is_not_success(monkeypatch):
    budget = FixtureBudget()
    captured, _ = install_transport(monkeypatch, budget)
    budget.journal.fail = "record"
    with pytest.raises(vultr_probe.ProbeDispatchError, match="PROBE_RECEIPT_WRITE_UNCERTAIN"):
        run(budget)
    assert len(captured) == 1 and budget.claimed


def test_replay_is_recovery_only_and_never_resends(monkeypatch):
    budget = FixtureBudget()
    captured, _ = install_transport(monkeypatch, budget)
    run(budget)
    assert budget.journal.records[0][2] == "PARSED_RESPONSE"
    with pytest.raises(vultr_probe.ProbeDispatchError, match="PROBE_ALREADY_RECORDED"):
        run(budget)
    assert len(captured) == 1 and len(budget.journal.records) == 1
