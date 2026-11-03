"""Trusted PostgreSQL dispatcher identity; never grant it reconciliation rights.

The DSN and account come from operator configuration, never uploaded/model data.
Every operation returns only after its own transaction has committed. Unknown
commit outcomes raise a fixed error and must not authorize a provider request.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

import psycopg


class BudgetUnavailable(Exception):
    """Fixed error without SQL, DSN, password or database diagnostic content."""


@dataclass(frozen=True)
class PostgresBudget:
    dsn: str = field(repr=False)
    account_id: UUID

    async def _execute(self, statement: str, parameters: tuple) -> bool:
        try:
            async with asyncio.timeout(8):
                async with await psycopg.AsyncConnection.connect(
                    self.dsn, autocommit=True, connect_timeout=3,
                    sslmode="verify-full", application_name="proofflow-budget-dispatch",
                    options="-c default_transaction_isolation=read\\ committed "
                            "-c synchronous_commit=on -c statement_timeout=5000 "
                            "-c lock_timeout=2000",
                ) as connection:
                    async with connection.transaction():
                        cursor = await connection.execute("SHOW fsync")
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
