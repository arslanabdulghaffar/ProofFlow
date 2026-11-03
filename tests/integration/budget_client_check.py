"""Invoked inside an isolated trusted test image, never by the public service.

Real disposable PostgreSQL over a local Unix socket; mock provider transport only.
No network, real credential, cloud call or candidate execution. Account is a fixture.
"""

import asyncio
import base64
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import psycopg

from orchestrator import vultr_probe
from orchestrator.budget_store import BudgetConnection, BudgetUnavailable, PostgresBudget
from orchestrator.probe_journal import ProbeJournal, recover_response
from orchestrator.probe_plan import ProbePlan, RateQuote, prepare_json_probe


async def main():
    credentials = json.loads(sys.stdin.read(2048))
    connection = BudgetConnection(credentials["dispatch"], "/budgetdb")
    budget = PostgresBudget(connection, UUID(sys.argv[1]))
    journal = ProbeJournal(budget)
    if credentials.get("recover_after_crash"):
        saved = credentials["recover_after_crash"]
        plan = ProbePlan(saved["endpoint"], base64.b64decode(saved["payload"]),
                         saved["request_sha256"], saved["reserve_micro_usd"],
                         saved["quote_sha256"], base64.b64decode(saved["quote_payload"]))
        request = UUID(saved["request_id"])
        snapshot = await journal.snapshot(request)
        assert recover_response(snapshot, request, plan).content_json == b'{"answer":7}'
        assert not await journal.prepare(request, plan)
        assert not await budget.claim(request, plan.request_sha256)
        print(json.dumps({"crash_receipt_recovered_no_replay": True}))
        return
    if credentials.get("expect_trust_rejection"):
        try:
            async with await psycopg.AsyncConnection.connect(**connection.parameters()):
                raise AssertionError("SCRAM requirement downgraded to trust")
        except psycopg.OperationalError as error:
            assert "authentication method requirement" in str(error)
            print(json.dumps({"trust_rejected": True}))
            return
        raise AssertionError("SCRAM requirement downgraded to trust")
    for password in ("x" * 64, ""):
        try:
            async with await psycopg.AsyncConnection.connect(
                **(connection.parameters() | {"password": password}),
            ):
                raise AssertionError("Wrong/missing SCRAM password accepted")
        except psycopg.OperationalError:
            pass
        else:
            raise AssertionError("Wrong SCRAM password accepted")
    for user in ("postgres", "pf_budget_public"):
        options = connection.parameters() | {"user": user}
        try:
            async with await psycopg.AsyncConnection.connect(**options):
                raise AssertionError("Privileged/public socket identity accepted")
        except psycopg.OperationalError:
            pass
    async with await psycopg.AsyncConnection.connect(**connection.parameters(),
                                                    autocommit=True) as actual:
        for query in ("UPDATE pf_budget.accounts SET blocked=false",
                      "SELECT * FROM pf_budget.reservations", "SET ROLE pf_budget_owner",
                      "SELECT * FROM pf_budget.probe_receipts",
                      "DELETE FROM pf_budget.probe_receipts"):
            try:
                await actual.execute(query)
            except psycopg.errors.InsufficientPrivilege:
                pass
            else:
                raise AssertionError("Runtime identity escaped function-only grants")
    os.environ["PGHOSTADDR"] = "192.0.2.1"
    try:
        try:
            await budget.claim(uuid4(), "c" * 64)
        except BudgetUnavailable as error:
            assert str(error) == "BUDGET_ENVIRONMENT_UNSAFE"
        else:
            raise AssertionError("libpq environment override accepted")
    finally:
        del os.environ["PGHOSTADDR"]
    deadline = datetime.now(UTC) + timedelta(minutes=5)
    request = uuid4()
    digest = "c" * 64
    assert await budget.reserve(request, digest, 10, deadline)
    assert not await budget.reserve(request, digest, 10, deadline)
    results = await asyncio.gather(*(budget.claim(request, digest) for _ in range(8)))
    assert results.count(True) == 1 and results.count(False) == 7
    try:
        await budget.reserve(request, digest, 11, deadline)
    except BudgetUnavailable as error:
        assert str(error) == "BUDGET_OPERATION_UNCERTAIN"
    else:
        raise AssertionError("Changed intent accepted")

    real_client = httpx.AsyncClient
    count = 0

    async def mock_provider(request):
        nonlocal count
        count += 1
        # Independent connection observes the committed uncertain state before HTTP.
        async with await psycopg.AsyncConnection.connect(
            **(connection.parameters() | {"user": "pf_budget_observer",
                                          "password": credentials["observer"]}),
            autocommit=True,
        ) as observer:
            cursor = await observer.execute(
                "SELECT state FROM pf_budget.reservations WHERE id=%s", (probe_id,),
            )
            assert await cursor.fetchone() == ("uncertain",)
        return httpx.Response(503, content=b"synthetic outage; never a provider success")

    def fixture_client(**kwargs):
        return real_client(**kwargs, transport=httpx.MockTransport(mock_provider))

    vultr_probe.httpx.AsyncClient = fixture_client
    now = datetime.now(UTC)
    quote = RateQuote("qwen3.8-27b", 150000, 1000000, now - timedelta(minutes=1),
                      deadline, "b" * 64)
    probe_id = uuid4()
    args = dict(budget=budget, request_id=probe_id, prompt="Return JSON.", quote=quote,
                max_completion_tokens=512, api_key="synthetic-fixture-no-credential")
    try:
        await vultr_probe.run_json_probe(**args)
    except vultr_probe.ProbeDispatchError as error:
        assert str(error) == "PROVIDER_HTTP_REJECTED"
    else:
        raise AssertionError("Fixture outage claimed success")
    try:
        await vultr_probe.run_json_probe(**args)
    except vultr_probe.ProbeDispatchError as error:
        assert str(error) == "PROBE_ALREADY_RECORDED"
    else:
        raise AssertionError("Uncertain call replayed")
    assert count == 1
    assert (await journal.snapshot(probe_id))["outcome"] == "OUTCOME_UNKNOWN"

    raw = json.dumps({"id": "chatcmpl-synthetic", "object": "chat.completion",
                      "model": quote.model,
                      "choices": [{"index": 0, "finish_reason": "stop",
                                   "message": {"role": "assistant", "content": '{"answer":7}'}}],
                      "usage": {"prompt_tokens": 10, "completion_tokens": 5,
                                "total_tokens": 15}}).encode()

    class SyntheticStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield raw

    async def synthetic_success(request):
        nonlocal count
        count += 1
        return httpx.Response(200, headers={"content-type": "application/json"},
                              stream=SyntheticStream())

    vultr_probe.httpx.AsyncClient = lambda **kwargs: real_client(
        **kwargs, transport=httpx.MockTransport(synthetic_success))
    successful_id = uuid4()
    plan = prepare_json_probe("Return JSON.", quote, max_completion_tokens=512, now=now)
    real_record = ProbeJournal.record

    async def lost_ack(self, *values):
        result = await real_record(self, *values)
        if values[2] == "PARSED_RESPONSE":
            raise BudgetUnavailable("FIXTURE_LOST_COMMIT_ACK")
        return result

    ProbeJournal.record = lost_ack
    try:
        try:
            await vultr_probe.run_json_probe(**dict(args, request_id=successful_id))
        except vultr_probe.ProbeDispatchError as error:
            assert str(error) == "PROBE_RECEIPT_WRITE_UNCERTAIN"
        else:
            raise AssertionError("Lost evidence commit acknowledgement claimed success")
    finally:
        ProbeJournal.record = real_record
    stored = await journal.snapshot(successful_id)
    recovered = recover_response(stored, successful_id, plan)
    assert recovered.content_json == b'{"answer":7}'
    assert recovered.usage.total_tokens == 15
    assert not await journal.record(successful_id, plan, "PARSED_RESPONSE", raw, 200,
                                    stored["elapsed_ms"])
    try:
        await journal.record(successful_id, plan, "OUTCOME_UNKNOWN", raw, 200,
                             stored["elapsed_ms"])
    except BudgetUnavailable:
        pass
    else:
        raise AssertionError("Immutable result was rewritten")
    try:
        await vultr_probe.run_json_probe(**dict(args, request_id=successful_id))
    except vultr_probe.ProbeDispatchError as error:
        assert str(error) == "PROBE_ALREADY_RECORDED"
    else:
        raise AssertionError("Recovered provider call was resent")
    assert count == 2
    assert await ProbeJournal(PostgresBudget(connection, uuid4())).snapshot(successful_id) is None

    concurrent_id = uuid4()
    prepared = await asyncio.gather(*(journal.prepare(concurrent_id, plan) for _ in range(8)))
    assert prepared.count(True) == 1 and prepared.count(False) == 7
    # One account admits at most 100 evidence rows, including unfinished attempts.
    for _ in range(97):
        assert await journal.prepare(uuid4(), plan)
    try:
        await journal.prepare(uuid4(), plan)
    except BudgetUnavailable:
        pass
    else:
        raise AssertionError("Unbounded probe evidence admitted")
    assert not await journal.prepare(concurrent_id, plan)  # Replay works at capacity.

    recovery_fixture = {"request_id": str(successful_id), "endpoint": plan.endpoint,
                        "request_sha256": plan.request_sha256,
                        "reserve_micro_usd": plan.reserve_micro_usd,
                        "payload": base64.b64encode(plan.payload).decode(),
                        "quote_payload": base64.b64encode(plan.quote_payload).decode(),
                        "quote_sha256": plan.quote_sha256}
    print(json.dumps({"scope": "real_local_postgres_mock_http_only", "checks": [
        "scram_success_wrong_password_and_peer_admin_rejection",
        "authenticated_dispatcher_cannot_read_mutate_or_escalate",
        "libpq_environment_redirect_rejected_before_connect",
        "python_driver_committed_reserve_and_exact_replay",
        "eight_python_claims_exactly_one_committed",
        "driver_database_error_redacted",
        "independent_connection_observed_commit_before_mock_http",
        "failed_mock_http_retained_reservation_and_prevented_resend",
        "durable_receipt_recovery_after_lost_commit_ack_no_resend",
        "receipt_scope_immutable_outcome_and_function_only_permissions",
        "concurrent_receipt_intent_admission_and_bounded_capacity",
    ], "recovery_fixture": recovery_fixture}))


if __name__ == "__main__":
    asyncio.run(main())
