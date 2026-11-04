"""Fixed Vultr adapter composition with product-owned, erasable request evidence."""

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import uuid4

from psycopg.types.json import Jsonb

from orchestrator.budget_store import PostgresBudget
from orchestrator.probe_plan import prepare_json_probe
from orchestrator.probe_response import ProviderResponseError
from orchestrator.repair_proposal import (
    COMPLETION_TOKENS,
    PROMPT_TOKEN_RESERVE,
    RepairRejected,
    parse_proposal,
)
from orchestrator.vultr_probe import _run_prepared


def prepare_repair_plan(prompt, quote, now):
    """Fixed non-thinking text generation; total output and monetary caps stay unchanged."""
    if quote.model != "qwen3.8-flash-next":
        raise RepairRejected("REPAIR_MODEL_NOT_APPROVED")
    plan = prepare_json_probe(prompt, quote, max_completion_tokens=COMPLETION_TOKENS, now=now)
    value = json.loads(plan.payload)
    value["reasoning"] = {"enabled": False}
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    envelope = json.dumps(
        {
            "endpoint": plan.endpoint,
            "method": "POST",
            "payload_sha256": hashlib.sha256(payload).hexdigest(),
            "quote_sha256": plan.quote_sha256,
            "reserve_micro_usd": plan.reserve_micro_usd,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode()
    return replace(plan, payload=payload, request_sha256=hashlib.sha256(envelope).hexdigest())


@dataclass(frozen=True)
class RepairBudget(PostgresBudget):
    async def reserve(self, request_id, request_hash, amount, valid_until):
        return await self._execute(
            "SELECT pf_budget.reserve(%s,%s,%s,'inference',%s,%s)",
            (self.account_id, request_id, request_hash, amount, valid_until),
        )


class RepairJournal:
    def __init__(self, store, binding):
        self.store, self.binding = store, binding

    async def prepare(self, request_id, plan):
        row = await self.store.call(
            "repair_prepare",
            *self.binding,
            request_id,
            plan.request_sha256,
            plan.payload,
            plan.quote_payload,
            plan.reserve_micro_usd,
        )
        return row[0]

    async def record(self, request_id, plan, outcome, body, status, elapsed):
        row = await self.store.call(
            "repair_response",
            *self.binding,
            request_id,
            plan.request_sha256,
            outcome,
            body,
            status,
            elapsed,
        )
        return row[0]


class RepairProvider:
    def __init__(self, *, store, budget, quote, api_key):
        self.store, self.budget, self.quote, self.api_key = store, budget, quote, api_key

    async def propose(self, binding, attempt, prompt):
        plan = prepare_repair_plan(prompt, self.quote, datetime.now(UTC))
        response = await _run_prepared(
            budget=self.budget,
            request_id=uuid4(),
            plan=plan,
            quote=self.quote,
            max_completion_tokens=COMPLETION_TOKENS,
            api_key=self.api_key,
            journal=RepairJournal(self.store, binding),
        )
        # Missing/oversized usage consumes its reservation and ends this job. No
        # unsupported assumption that missing reported usage was zero.
        if response.usage is None or response.usage.prompt_tokens > PROMPT_TOKEN_RESERVE:
            raise RepairRejected("REPAIR_USAGE_UNKNOWN")
        try:
            proposal = parse_proposal(response.content_json)
        except (RepairRejected, ProviderResponseError):
            await self.store.call(
                "repair_proposal",
                *binding,
                attempt,
                Jsonb({"kind": "rejected", "code": "INVALID_PROPOSAL"}),
            )
            return None
        await self.store.call("repair_proposal", *binding, attempt, Jsonb(proposal.data))
        return proposal
