"""Labeled database faults complement the real PostgreSQL integration check."""

import asyncio
from uuid import uuid4

import psycopg
import pytest

from orchestrator.budget_store import BudgetUnavailable, PostgresBudget


def fixture_connection(monkeypatch, *, fail=None, fsync="on"):
    events = []

    class Cursor:
        def __init__(self, result):
            self.result = result

        async def fetchone(self):
            return self.result

    class Transaction:
        async def __aenter__(self):
            events.append("begin")

        async def __aexit__(self, exc_type, *_):
            events.append("rollback" if exc_type else "commit")
            if fail == "commit":
                raise psycopg.OperationalError("fixture private database diagnostic")

    class Connection:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            events.append("close")

        def transaction(self):
            return Transaction()

        async def execute(self, statement, parameters=None):
            if statement == "SHOW fsync":
                return Cursor((fsync,))
            assert "%s" in statement and len(parameters) == 3
            events.append("function_returned_true")
            if fail == "execute":
                raise psycopg.OperationalError("fixture private database diagnostic")
            return Cursor((True,))

    async def connect(dsn, **options):
        assert options["autocommit"] is True and options["sslmode"] == "verify-full"
        assert "synchronous_commit=on" in options["options"]
        assert "read\\ committed" in options["options"]
        if fail == "connect":
            raise psycopg.OperationalError("fixture private database diagnostic")
        return Connection()

    monkeypatch.setattr(psycopg.AsyncConnection, "connect", connect)
    return events


def test_commit_and_close_precede_success(monkeypatch):
    events = fixture_connection(monkeypatch)
    store = PostgresBudget("fixture DSN never connected", uuid4())
    assert "fixture DSN" not in repr(store)
    assert asyncio.run(store.claim(uuid4(), "a" * 64))
    assert events == ["begin", "function_returned_true", "commit", "close"]


@pytest.mark.parametrize("failure", ["connect", "execute", "commit"])
def test_unknown_commit_or_database_fault_never_returns_authorization(monkeypatch, failure):
    events = fixture_connection(monkeypatch, fail=failure)
    store = PostgresBudget("fixture DSN never connected", uuid4())
    with pytest.raises(BudgetUnavailable, match="^BUDGET_OPERATION_UNCERTAIN$"):
        asyncio.run(store.claim(uuid4(), "a" * 64))
    if failure != "connect":
        assert events[-1] == "close"


def test_disabled_fsync_prevents_function_call(monkeypatch):
    events = fixture_connection(monkeypatch, fsync="off")
    with pytest.raises(BudgetUnavailable, match="BUDGET_DURABILITY_UNAVAILABLE"):
        asyncio.run(PostgresBudget("fixture DSN", uuid4()).claim(uuid4(), "a" * 64))
    assert events == ["begin", "rollback", "close"]
