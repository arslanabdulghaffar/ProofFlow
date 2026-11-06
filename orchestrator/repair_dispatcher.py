"""Bounded repair controller. Model code is only data sent to the isolated worker."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from api.app.product_store import ProductFailure
from orchestrator.budget_store import BudgetUnavailable
from orchestrator.probe_response import ProviderResponseError
from orchestrator.repair_evidence import bind_sources, classify
from orchestrator.repair_proposal import (
    INTERFACE,
    MAX_ATTEMPTS,
    Proposal,
    RepairRejected,
    build_prompt,
)
from orchestrator.verification_run import VerificationRun, retained_receipt
from orchestrator.verifier_client import VerifierClient
from orchestrator.vultr_probe import ProbeDispatchError
from verifier.protocol import decode
from worker.protocol import SupervisorError, runtime_identity_digest


class RepairDispatcher:
    def __init__(self, store, assets, worker, provider, *, verifier_sha256, journal):
        self.store, self.assets, self.worker, self.provider = store, assets, worker, provider
        self.verifier_sha256, self.journal = verifier_sha256, journal
        self.controller = uuid4()

    async def once(self):
        row = await self.store.call("repair_claim", self.controller)
        if row is None or row[0] is None:
            return False
        job = row[0]
        workspace, identity = UUID(job["workspace_id"]), UUID(job["id"])
        binding = (workspace, identity, self.controller, job["generation"])
        stop, lost = asyncio.Event(), asyncio.Event()
        active = []
        cleanup = job["state"] == "RECONCILING"

        async def heartbeat():
            while not stop.is_set():
                try:
                    await asyncio.wait_for(stop.wait(), 10)
                    return
                except TimeoutError:
                    try:
                        await self.store.call("repair_heartbeat", *binding, cleanup)
                    except ProductFailure:
                        lost.set()
                        if active:
                            request = active[-1]
                            try:
                                await asyncio.to_thread(
                                    self.worker.call,
                                    {
                                        "v": 1,
                                        "op": "cancel",
                                        "execution": request.execution_id.hex,
                                        "job": identity.hex,
                                        "generation": request.generation,
                                    },
                                )
                            except SupervisorError:
                                pass
                        return

        heart = asyncio.create_task(heartbeat())
        try:
            if cleanup:
                await self.reconcile(job, binding)
                return True
            parent = job["parent"]
            if (
                parent["runtime_sha256"] != self.worker.runtime_digest
                or parent["verifier_sha256"] != self.verifier_sha256
            ):
                await self.store.call("repair_finish", *binding, "infrastructure_failed")
                return True
            values = {}
            for asset in (await self.store.call("repair_assets", *binding))[0]:
                raw = await asyncio.to_thread(self.assets.read, workspace, asset["sha256"])
                if len(raw) != asset["bytes"]:
                    raise ProductFailure("PRODUCT_ASSET_BYTES_CHANGED")
                values[asset["kind"]] = raw
            if set(values) != {"pipeline", "transactions", "customers", "contract"}:
                raise ProductFailure("PRODUCT_ASSET_MANIFEST_INVALID")
            feedback = ({"code": "ORIGINAL_EXECUTION_FAILED", "output_verified": False}
                        if parent.get("outcome") == "execution_failed"
                        else parent["report"]["semantic"]["report"]["result"])
            history = []
            generation = 0
            loop = asyncio.get_running_loop()

            def committed(operation, *arguments):
                if lost.is_set():
                    raise ProductFailure("STALE_JOB_LEASE")
                return asyncio.run_coroutine_threadsafe(
                    self.store.call(operation, *arguments), loop
                ).result(timeout=10)

            async def execute(source, tx, cs, purpose, attempt):
                nonlocal generation
                if (
                    datetime.fromisoformat(job["deadline"]) - datetime.now(UTC)
                ).total_seconds() < 135:
                    return "deadline", {}
                generation += 1
                captured_intent = []

                def before(request, intent):
                    bind_sources(
                        intent,
                        source=source,
                        contract=values["contract"],
                        transactions=tx,
                        customers=cs,
                        runtime=self.worker.runtime_digest,
                        verifier=self.verifier_sha256,
                        purpose=purpose,
                    )
                    committed(
                        "repair_begin", *binding, attempt, request.execution_id, Jsonb(intent)
                    )
                    captured_intent.append(intent)
                    active.append(request)

                runner = VerificationRun(
                    self.worker,
                    Path("/unused-administrator-image"),
                    self.verifier_sha256,
                    self.journal,
                    verifier=VerifierClient(self.verifier_sha256),
                    before_dispatch=before,
                )
                result = await asyncio.to_thread(
                    runner.execute,
                    execution=uuid4(),
                    job=identity,
                    generation=generation,
                    pipeline=source,
                    contract=values["contract"],
                    transactions=tx,
                    customers=cs,
                    purpose=purpose,
                )
                decision, explanation = classify(
                    result, captured_intent[0], self.worker.runtime_digest, self.verifier_sha256
                )
                await self.store.call(
                    "repair_execution", *binding, UUID(result["intent"]["execution"]), Jsonb(result)
                )
                active.clear()
                return decision, explanation

            outcome = "attempts_exhausted"
            unchanged = parent.get("outcome") == "match"
            if unchanged:
                await self.store.call("repair_original", *binding, values["pipeline"])
            for attempt in [0] if unchanged else range(1, MAX_ATTEMPTS + 1):
                if lost.is_set():
                    return True
                remaining = (
                    datetime.fromisoformat(job["deadline"]) - datetime.now(UTC)
                ).total_seconds()
                if remaining < 65:
                    outcome = "deadline_exceeded"
                    break
                if unchanged:
                    proposal = Proposal("propose_patch", {}, values["pipeline"])
                else:
                    try:
                        prompt = build_prompt(
                            pipeline=values["pipeline"],
                            contract=values["contract"],
                            interface=INTERFACE,
                            feedback=feedback,
                            previous=history,
                        )
                    except (RepairRejected, UnicodeError):
                        outcome = "context_limit"
                        break
                    try:
                        proposal = await self.provider.propose(binding, attempt, prompt)
                    except ProductFailure as error:
                        if str(error) not in (
                            "REPAIR_BUDGET_EXHAUSTED",
                            "REPAIR_DEVELOPMENT_ALLOCATION",
                        ):
                            raise
                        outcome = "budget_exhausted"
                        break
                    except RepairRejected:
                        outcome = "usage_unknown"
                        break
                    except (
                        BudgetUnavailable,
                        ProbeDispatchError,
                        ProviderResponseError,
                        ValueError,
                    ):
                        outcome = "provider_unavailable"
                        break
                if proposal is None:
                    feedback = {"code": "INVALID_PROPOSAL"}
                    history.append(
                        {"attempt": attempt, "code": "INVALID_PROPOSAL", "candidate_sha256": None}
                    )
                    continue
                if proposal.kind == "needs_clarification":
                    outcome = "needs_clarification"
                    break
                decision, feedback = await execute(
                    proposal.source,
                    values["transactions"],
                    values["customers"],
                    "candidate",
                    attempt,
                )
                if decision == "deadline":
                    outcome = "deadline_exceeded"
                    break
                if decision == "held":
                    outcome = "input_held"
                    break
                if decision == "match":
                    for case in ("ownership", "quarantine"):
                        runner = VerificationRun(
                            self.worker,
                            Path("/unused-administrator-image"),
                            self.verifier_sha256,
                            self.journal,
                            verifier=VerifierClient(self.verifier_sha256),
                        )
                        canary = await asyncio.to_thread(runner.canary, values["contract"], case)
                        data = canary["report"]["result"]
                        decision, feedback = await execute(
                            proposal.source,
                            decode(data["transactions_csv"], 5242880),
                            decode(data["customers_csv"], 5242880),
                            "canary_" + case,
                            attempt,
                        )
                        # Correct quarantine is intentionally held. Only its exact
                        # comparison, never permission to process the batch, counts.
                        if decision not in (
                            ("match", "held") if case == "quarantine" else ("match",)
                        ):
                            break
                    else:
                        outcome = "candidate_passed"
                        break
                if decision == "deadline":
                    outcome = "deadline_exceeded"
                    break
                history.append(
                    {
                        "attempt": attempt,
                        "code": feedback.get("code", "REJECTED"),
                        "candidate_sha256": proposal.sha256,
                    }
                )
            if not lost.is_set():
                await self.store.call("repair_finish", *binding, outcome)
            return True
        finally:
            stop.set()
            await heart

    async def reconcile(self, job, binding):
        identity = UUID(job["id"])
        # Recovery never calls the provider or executes another candidate. The
        # terminal fence is above every permitted productive generation.
        fenced = await asyncio.to_thread(
            self.worker.call, {"v": 1, "op": "fence", "job": identity.hex, "generation": 1000}
        )
        if fenced != {"fenced": True}:
            raise SupervisorError("WORKER_FENCE_UNCERTAIN")
        for execution in job["executions"]:
            if execution["result"] is not None:
                continue
            for _ in range(25):
                status = await asyncio.to_thread(
                    self.worker.call,
                    {
                        "v": 1,
                        "op": "status",
                        "job": identity.hex,
                        "execution": UUID(execution["execution_id"]).hex,
                        "generation": execution["generation"],
                    },
                )
                if status.get("state") == "CLEANED":
                    receipt = retained_receipt(status.get("receipt", {}))
                    if (
                        runtime_identity_digest(receipt.get("runtime", {}))
                        != self.worker.runtime_digest
                    ):
                        raise SupervisorError("RECONCILIATION_RECEIPT_INVALID")
                    await self.store.call(
                        "repair_execution",
                        *binding,
                        UUID(execution["execution_id"]),
                        Jsonb({"intent": execution["intent"], "worker": receipt, "semantic": None}),
                    )
                    break
                await asyncio.sleep(1)
            else:
                raise SupervisorError("RECONCILIATION_CLEANUP_UNCERTAIN")
        await self.store.call(
            "repair_finish",
            *binding,
            "cancelled" if job["cancel_requested"] else "infrastructure_failed",
        )
