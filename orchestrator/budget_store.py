"""Trusted PostgreSQL dispatcher identity; never grant it reconciliation rights.

Connection settings and account come from operator configuration, never model data.
Every operation returns only after its own transaction has committed. Unknown
commit outcomes raise a fixed error and must not authorize a provider request.
"""

import asyncio
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import PurePosixPath
from uuid import UUID

import psycopg

from orchestrator.provider_setup import valid_secret


class BudgetUnavailable(Exception):
    """Fixed error without SQL, DSN, password or database diagnostic content."""


@dataclass(frozen=True)
class BudgetConnection:
    """Same-control-host Unix socket and SCRAM; no arbitrary libpq DSN."""

    password: str = field(repr=False)
    socket_directory: str = "/run/proofflow-budget"

    def __post_init__(self):
        path = PurePosixPath(self.socket_directory)
        if (not valid_secret(self.password) or not path.is_absolute()
                or str(path) != self.socket_directory or ".." in path.parts
                or any(char not in ("/abcdefghijklmnopqrstuvwxyz"
                                    "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
                       for char in self.socket_directory)
                or len(self.socket_directory) > 80):
            raise BudgetUnavailable("BUDGET_CONFIGURATION_INVALID")

    def parameters(self) -> dict:
        # libpq service files/environment can otherwise add hostaddr, options or auth
        # fallbacks. A dedicated service must start with no PG* environment settings.
        if any(name.upper().startswith("PG") for name in os.environ):
            raise BudgetUnavailable("BUDGET_ENVIRONMENT_UNSAFE")
        return dict(host=self.socket_directory, port=5432, dbname="proofflow_budget",
                    user="pf_budget_login", password=self.password, passfile="/dev/null",
                    require_auth="scram-sha-256", sslmode="disable", gssencmode="disable",
                    target_session_attrs="read-write", client_encoding="UTF8")


@dataclass(frozen=True)
class PostgresBudget:
    connection: BudgetConnection = field(repr=False)
    account_id: UUID

    async def _execute(self, statement: str, parameters: tuple) -> bool:
        try:
            async with asyncio.timeout(8):
                async with await psycopg.AsyncConnection.connect(
                    **self.connection.parameters(), autocommit=True, connect_timeout=3,
                    application_name="proofflow-budget-dispatch",
                    options="-c default_transaction_isolation=read\\ committed "
                            "-c synchronous_commit=on -c statement_timeout=5000 "
                            "-c lock_timeout=2000 -c search_path=pg_catalog",
                ) as connection:
                    async with connection.transaction():
                        cursor = await connection.execute("SHOW fsync")
                        if await cursor.fetchone() != ("on",):
                            raise BudgetUnavailable("BUDGET_DURABILITY_UNAVAILABLE")
                        cursor = await connection.execute("SHOW full_page_writes")
                        if await cursor.fetchone() != ("on",):
                            raise BudgetUnavailable("BUDGET_DURABILITY_UNAVAILABLE")
                        cursor = await connection.execute(statement, parameters)
                        row = await cursor.fetchone()
                        if row is None or len(row) != 1 or type(row[0]) is not bool:
                            raise BudgetUnavailable("BUDGET_INVALID_RESULT")
                    # Transaction context has acknowledged COMMIT before returning.
                    return row[0]
        except (psycopg.Error, OSError, TimeoutError):
            raise BudgetUnavailable("BUDGET_OPERATION_UNCERTAIN") from None

    async def reserve(
        self, request_id: UUID, request_hash: str, amount: int, valid_until: datetime,
    ) -> bool:
        return await self._execute(
            "SELECT pf_budget.reserve(%s,%s,%s,'probe',%s,%s)",
            (self.account_id, request_id, request_hash, amount, valid_until),
        )

    async def claim(self, request_id: UUID, request_hash: str) -> bool:
        return await self._execute(
            "SELECT pf_budget.claim(%s,%s,%s)",
            (self.account_id, request_id, request_hash),
        )
