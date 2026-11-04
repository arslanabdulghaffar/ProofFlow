"""Linux controller doubles only. These tests NEVER execute candidate source."""

import asyncio
import hashlib
import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Linux worker client import")


@pytest.mark.parametrize(
    "responses,expected,calls",
    [
        ([None, None, None], "attempts_exhausted", 3),
        (["clarify"], "needs_clarification", 1),
        (["provider_failure"], "provider_unavailable", 1),
        (["usage_unknown"], "usage_unknown", 1),
    ],
)
def test_bounds_abstention_and_uncertain_provider_no_retry(tmp_path, responses, expected, calls):
    from orchestrator.repair_dispatcher import RepairDispatcher
    from orchestrator.repair_proposal import Proposal, RepairRejected
    from orchestrator.vultr_probe import ProbeDispatchError

    raw = {"pipeline": b"inert source", "contract": b"{}", "transactions": b"t", "customers": b"c"}
    by_hash = {hashlib.sha256(v).hexdigest(): v for v in raw.values()}
    job = {
        "workspace_id": str(uuid4()),
        "id": str(uuid4()),
        "generation": 1,
        "state": "RUNNING",
        "deadline": (datetime.now(UTC) + timedelta(seconds=299)).isoformat(),
        "parent": {
            "runtime_sha256": "r",
            "verifier_sha256": "v",
            "report": {"semantic": {"report": {"result": {"findings": []}}}},
        },
    }
    operations = []

    class Store:
        async def call(self, op, *values):
            operations.append((op, values))
            if op == "repair_claim":
                return (job,)
            if op == "repair_assets":
                return (
                    [
                        {"kind": k, "sha256": hashlib.sha256(v).hexdigest(), "bytes": len(v)}
                        for k, v in raw.items()
                    ],
                )
            return (None,)

    class Provider:
        count = 0

        async def propose(self, binding, attempt, prompt):
            self.count += 1
            response = responses[attempt - 1]
            if response == "provider_failure":
                raise ProbeDispatchError("PROVIDER_OUTCOME_UNCERTAIN")
            if response == "usage_unknown":
                raise RepairRejected("REPAIR_USAGE_UNKNOWN")
            if response == "clarify":
                return Proposal("needs_clarification", {"questions": ["Which unit?"]}, None)
            return None

    provider = Provider()
    dispatcher = RepairDispatcher(
        Store(),
        SimpleNamespace(read=lambda w, h: by_hash[h]),
        SimpleNamespace(runtime_digest="r"),
        provider,
        verifier_sha256="v",
        journal=tmp_path,
    )
    assert asyncio.run(dispatcher.once()) is True
    assert provider.count == calls
    assert operations[-1][0] == "repair_finish" and operations[-1][1][-1] == expected
    assert not any(op == "repair_begin" for op, _ in operations)


@pytest.mark.parametrize(
    "sequence,expected,attempts",
    [
        (["mismatch", "match", "match", "held"], "candidate_passed", 2),
        (["match", "mismatch", "match", "match", "held"], "candidate_passed", 2),
        (["mismatch", "mismatch", "mismatch"], "attempts_exhausted", 3),
        (["match", "match", "held"], "candidate_passed", 0),
    ],
)
def test_retry_fresh_canaries_and_proof_binding(
    monkeypatch, tmp_path, sequence, expected, attempts
):
    from orchestrator import repair_dispatcher as module
    from orchestrator.repair_proposal import Proposal
    from tests.unit.test_repair_evidence import receipt
    from verifier.protocol import encode
    from worker.protocol import runtime_identity_digest

    original = {
        "pipeline": b"inert original",
        "contract": b"{}",
        "transactions": b"t",
        "customers": b"c",
    }
    hashes = {hashlib.sha256(v).hexdigest(): v for v in original.values()}
    runtime = runtime_identity_digest({})
    job = {
        "workspace_id": str(uuid4()),
        "id": str(uuid4()),
        "generation": 1,
        "state": "RUNNING",
        "deadline": (datetime.now(UTC) + timedelta(seconds=299)).isoformat(),
        "parent": {
            "outcome": "match" if attempts == 0 else "mismatch",
            "runtime_sha256": runtime,
            "verifier_sha256": "3" * 64,
            "report": {"semantic": {"report": {"result": {"findings": []}}}},
        },
    }
    operations, identities, prompts = [], [], []
    outcomes = iter(sequence)

    class Store:
        async def call(self, operation, *values):
            operations.append((operation, values))
            if operation == "repair_claim":
                return (job,)
            if operation == "repair_assets":
                return (
                    [
                        {"kind": k, "sha256": hashlib.sha256(v).hexdigest(), "bytes": len(v)}
                        for k, v in original.items()
                    ],
                )
            return (True,)

    class Provider:
        async def propose(self, binding, attempt, prompt):
            prompts.append(prompt)
            return Proposal("propose_patch", {}, b"inert model source")

    class Runner:
        def __init__(self, *args, before_dispatch=None, **kwargs):
            self.before = before_dispatch

        def canary(self, contract, case):
            return {
                "report": {
                    "result": {
                        "transactions_csv": encode(b"SECRET_CANARY_TX"),
                        "customers_csv": encode(b"SECRET_CANARY_CUSTOMER"),
                    }
                }
            }

        def execute(
            self,
            *,
            execution,
            job,
            generation,
            pipeline,
            contract,
            transactions,
            customers,
            purpose,
        ):
            decision = next(outcomes)
            intent, result = receipt(
                purpose,
                "mismatch" if decision == "mismatch" else "match",
                blocking=int(decision == "held"),
            )
            intent.update(
                execution=execution.hex,
                job=job.hex,
                generation=generation,
                runtime_sha256=runtime,
                verifier_rootfs="3" * 64,
                pipeline_sha256=hashlib.sha256(pipeline).hexdigest(),
                contract_raw_sha256=hashlib.sha256(contract).hexdigest(),
                transactions_sha256=hashlib.sha256(transactions).hexdigest(),
                customers_sha256=hashlib.sha256(customers).hexdigest(),
            )
            if purpose == "candidate" and decision == "mismatch":
                result["semantic"]["report"]["result"]["ownership_witnesses"] = [
                    {"expected_owner": "public_source_owner"}
                ]
            self.before(
                SimpleNamespace(execution_id=execution, job_id=job, generation=generation), intent
            )
            identities.append((execution, generation, purpose))
            result["intent"] = intent
            result["worker"].update(execution=execution.hex, job=job.hex, generation=generation)
            result["semantic"]["report"]["result"].update(
                {
                    key: intent[key]
                    for key in ("contract_sha256", "transactions_sha256", "customers_sha256")
                }
            )
            return result

    monkeypatch.setattr(module, "VerificationRun", Runner)
    worker = SimpleNamespace(runtime_digest=runtime)
    dispatcher = module.RepairDispatcher(
        Store(),
        SimpleNamespace(read=lambda w, h: hashes[h]),
        worker,
        Provider(),
        verifier_sha256="3" * 64,
        journal=tmp_path,
    )
    assert asyncio.run(dispatcher.once()) is True
    assert len(prompts) == attempts
    assert all(
        "inert original" in prompt and "inert model source" not in prompt for prompt in prompts
    )
    assert operations[-1][1][-1] == expected
    assert len({identity[0] for identity in identities}) == len(sequence)
    assert [identity[1] for identity in identities] == list(range(1, len(sequence) + 1))
    assert not any(
        "SECRET_CANARY" in prompt or "secret_canary_owner" in prompt for prompt in prompts
    )
    if expected == "candidate_passed":
        assert [identity[2] for identity in identities[-3:]] == [
            "candidate",
            "canary_ownership",
            "canary_quarantine",
        ]
