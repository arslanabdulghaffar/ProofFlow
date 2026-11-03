"""Invoked inside an isolated trusted test image, never by the public service.

Real disposable PostgreSQL over a local Unix socket; mock provider transport only.
No network, real credential, cloud call or candidate execution. Account is a fixture.
"""

import asyncio
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import psycopg

from orchestrator import vultr_probe
from orchestrator.budget_store import BudgetConnection, BudgetUnavailable, PostgresBudget
from orchestrator.probe_plan import RateQuote


async def main():
    credentials = json.loads(sys.stdin.read(2048))
    connection = BudgetConnection(credentials["dispatch"], "/budgetdb")
    budget = PostgresBudget(connection, UUID(sys.argv[1]))
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
                      "SELECT * FROM pf_budget.reservations", "SET ROLE pf_budget_owner"):
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
        assert str(error) == "PROBE_ALREADY_CLAIMED"
    else:
        raise AssertionError("Uncertain call replayed")
    assert count == 1
    print(json.dumps({"scope": "real_local_postgres_mock_http_only", "checks": [
        "scram_success_wrong_password_and_peer_admin_rejection",
        "authenticated_dispatcher_cannot_read_mutate_or_escalate",
        "libpq_environment_redirect_rejected_before_connect",
        "python_driver_committed_reserve_and_exact_replay",
        "eight_python_claims_exactly_one_committed",
        "driver_database_error_redacted",
        "independent_connection_observed_commit_before_mock_http",
        "failed_mock_http_retained_reservation_and_prevented_resend",
    ]}))


if __name__ == "__main__":
    asyncio.run(main())
