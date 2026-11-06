"""Private single-worker queue consumer. Fixed worker/verifier only; no provider calls."""

import asyncio
from pathlib import Path
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from api.app.product_store import ProductFailure
from orchestrator.verification_run import VerificationRun, retained_receipt
from orchestrator.verifier_client import VerifierClient
from worker.protocol import SupervisorError, authority_id, runtime_identity_digest


class ProductDispatcher:
    def __init__(self, store, assets, worker, *, verifier_sha256: str, journal: Path):
        self.store, self.assets, self.worker = store, assets, worker
        self.verifier_sha256, self.journal = verifier_sha256, journal
        self.controller = uuid4()

    async def once(self):
        row = await self.store.call("claim", self.controller)
        if row is None or row[0] is None:
            return False
        job = row[0]
        workspace, job_id = UUID(job["workspace_id"]), UUID(job["id"])
        binding = (workspace, job_id, self.controller, job["generation"])
        stop, lost = asyncio.Event(), asyncio.Event()
        active = []

        async def heartbeat():
            while not stop.is_set():
                try:
                    await asyncio.wait_for(stop.wait(), timeout=10)
                    return
                except TimeoutError:
                    try:
                        await self.store.call("heartbeat", *binding)
                    except ProductFailure:
                        lost.set()
                        if active:
                            request = active[0]
                            try:
                                await asyncio.to_thread(
                                    self.worker.call,
                                    {
                                        "v": 1,
                                        "op": "cancel",
                                        "execution": request.execution_id.hex,
                                        "job": request.job_id.hex,
                                        "generation": request.generation,
                                    },
                                )
                            except SupervisorError:
                                pass  # Unknown cancellation; worker deadline still applies.
                        return

        heart = asyncio.create_task(heartbeat())
        try:
            if job["state"] == "RECONCILING":
                await self._reconcile(job, binding)
                return True
            if (
                job["runtime_sha256"] != self.worker.runtime_digest
                or job["verifier_sha256"] != self.verifier_sha256
            ):
                await self.store.call("fail", *binding, Jsonb({"not_dispatched": True}))
                return True
            metadata = (await self.store.call("assets", *binding))[0]
            if type(metadata) is not list or len(metadata) != 4:
                raise ProductFailure("PRODUCT_ASSET_MANIFEST_INVALID")
            values = {}
            for asset in metadata:
                raw = await asyncio.to_thread(self.assets.read, workspace, asset["sha256"])
                if len(raw) != asset["bytes"]:
                    raise ProductFailure("PRODUCT_ASSET_BYTES_CHANGED")
                values[asset["kind"]] = raw
            if set(values) != {"pipeline", "transactions", "customers", "contract"}:
                raise ProductFailure("PRODUCT_ASSET_MANIFEST_INVALID")
            loop = asyncio.get_running_loop()

            def committed(operation, *arguments):
                if lost.is_set():
                    raise ProductFailure("STALE_JOB_LEASE")
                future = asyncio.run_coroutine_threadsafe(
                    self.store.call(operation, *arguments), loop
                )
                return future.result(timeout=10)

            def before(request, _intent):
                committed("begin", *binding, request.execution_id, request.manifest_hash())
                active.append(request)

            def captured(request, receipt):
                committed("collected", *binding, request.execution_id, Jsonb(receipt))

            runner = VerificationRun(
                self.worker,
                Path("/unused-administrator-image"),
                self.verifier_sha256,
                self.journal,
                verifier=VerifierClient(self.verifier_sha256),
                before_dispatch=before,
                after_capture=captured,
            )
            try:
                result = await asyncio.to_thread(
                    runner.execute,
                    execution=authority_id(),
                    job=job_id,
                    generation=job["generation"],
                    pipeline=values["pipeline"],
                    contract=values["contract"],
                    transactions=values["transactions"],
                    customers=values["customers"],
                    purpose="original",
                )
            except SupervisorError as error:
                if str(error) == "SOURCE_PREPARATION_REJECTED" and not active and not lost.is_set():
                    await self.store.call("reject_input", *binding)
                    return True
                raise
            if lost.is_set():
                # No stale write. Next leased controller fences/reconciles the stored execution.
                return True
            if result["semantic"] is None:
                if result.get("source", {}).get("report", {}).get("status") == "processed":
                    await self.store.call("review_failure", *binding, Jsonb(result))
                else:
                    await self.store.call("fail", *binding, Jsonb(result["worker"]))
            elif result["semantic"]["report"]["status"] != "processed":
                await self.store.call("fail", *binding, Jsonb(result["worker"]))
            else:
                await self.store.call("finish", *binding, Jsonb(result))
            return True
        finally:
            stop.set()
            await heart

    async def _reconcile(self, job, binding):
        # Raising/unknown state preserves the job and worker capacity. No replacement.
        job_id, execution = UUID(job["id"]), UUID(job["execution_id"])
        fenced = await asyncio.to_thread(
            self.worker.call,
            {"v": 1, "op": "fence", "job": job_id.hex, "generation": job["generation"]},
        )
        if fenced != {"fenced": True}:
            raise SupervisorError("WORKER_FENCE_UNCERTAIN")
        for _ in range(25):
            status = await asyncio.to_thread(
                self.worker.call,
                {
                    "v": 1,
                    "op": "status",
                    "job": job_id.hex,
                    "execution": execution.hex,
                    "generation": job["execution_generation"],
                },
            )
            if status.get("state") == "CLEANED":
                receipt = status.get("receipt")
                if type(receipt) is not dict or receipt.get("cleanup") != "confirmed":
                    raise SupervisorError("RECONCILIATION_RECEIPT_INVALID")
                if runtime_identity_digest(receipt.get("runtime", {})) != job["runtime_sha256"]:
                    raise SupervisorError("RECONCILIATION_RECEIPT_INVALID")
                await self.store.call("fail", *binding, Jsonb(retained_receipt(receipt)))
                return
            await asyncio.sleep(1)
        raise SupervisorError("RECONCILIATION_CLEANUP_UNCERTAIN")
