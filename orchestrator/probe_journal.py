"""Durable private probe evidence; never authorization, verification or settlement."""

import base64
import hashlib
import json
from dataclasses import dataclass
from uuid import UUID

from orchestrator.budget_store import BudgetUnavailable, PostgresBudget
from orchestrator.probe_plan import ProbePlan
from orchestrator.probe_response import ProbeResponse, parse_probe_response


@dataclass(frozen=True)
class ProbeJournal:
    budget: PostgresBudget

    async def prepare(self, request_id: UUID, plan: ProbePlan) -> bool:
        return await self.budget._execute(
            "SELECT pf_budget.prepare_probe(%s,%s,%s,%s,%s,%s)",
            (self.budget.account_id, request_id, plan.request_sha256, plan.payload,
             plan.quote_payload, plan.reserve_micro_usd),
        )

    async def record(self, request_id: UUID, plan: ProbePlan, outcome: str,
                     body: bytes | None, status: int | None, elapsed_ms: int) -> bool:
        return await self.budget._execute(
            "SELECT pf_budget.record_probe(%s,%s,%s,%s,%s,%s,%s)",
            (self.budget.account_id, request_id, plan.request_sha256, outcome,
             body, status, elapsed_ms),
        )

    async def snapshot(self, request_id: UUID) -> dict | None:
        row = await self.budget._query("SELECT pf_budget.read_probe(%s,%s)",
                                       (self.budget.account_id, request_id))
        if row[0] is not None and type(row[0]) is not dict:
            raise BudgetUnavailable("PROBE_RECEIPT_INVALID")
        return row[0]


def recover_response(snapshot: dict, request_id: UUID, plan: ProbePlan) -> ProbeResponse:
    """Validate stored bytes against the caller's exact reviewed plan. Never sends."""
    try:
        if (snapshot["request_id"] != str(request_id)
                or snapshot["request_sha256"] != plan.request_sha256
                or snapshot["state"] != "RECORDED" or snapshot["outcome"] != "PARSED_RESPONSE"
                or snapshot["http_status"] != 200
                or snapshot["reserve_micro_usd"] != plan.reserve_micro_usd):
            raise ValueError("identity")
        # PostgreSQL's base64 encoder inserts LF; no other whitespace is accepted.
        def decode(value: str, limit: int) -> bytes:
            if type(value) is not str or len(value) > limit * 2:
                raise ValueError("bound")
            result = base64.b64decode(value.replace("\n", ""), validate=True)
            if len(result) > limit:
                raise ValueError("bound")
            return result

        if (decode(snapshot["payload_base64"], 102400) != plan.payload
                or decode(snapshot["quote_base64"], 4096) != plan.quote_payload):
            raise ValueError("payload")
        body = decode(snapshot["response_base64"], 262144)
        if hashlib.sha256(body).hexdigest() != snapshot["response_sha256"]:
            raise ValueError("hash")
        payload = json.loads(plan.payload)
        return parse_probe_response(body, model=payload["model"],
                                    completion_bound=payload["max_completion_tokens"])
    except (KeyError, TypeError, ValueError):
        raise BudgetUnavailable("PROBE_RECEIPT_INVALID") from None
