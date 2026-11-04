"""Trusted original/canary orchestration, with immutable intent before worker I/O.

This primitive does not grant product approvals or mutate job state. A durable
queue dispatcher must authorize/fence each invocation. It never executes code.
"""

import fcntl
import os
import secrets
import stat
from pathlib import Path
from uuid import UUID

from contracts.codec import canonical_bytes
from orchestrator.worker_client import WorkerClient
from verifier.host import run
from verifier.protocol import MAX_REQUEST, decode, encode, sha
from worker.host import sync_directory, synced_write
from worker.journal import private_directory
from worker.protocol import ExecutionRequest, SupervisorError


class VerificationRun:
    def __init__(self, client: WorkerClient, image: Path, image_sha256: str, journal: Path):
        self.client, self.image = client, image
        self.image_sha256, self.journal = image_sha256, journal
        private_directory(journal)

    def bounded(self, message):
        raw = canonical_bytes(message, max_bytes=MAX_REQUEST)
        receipt = run(raw, image=self.image, image_sha256=self.image_sha256)
        if receipt["cleanup_confirmed"] is not True:
            raise SupervisorError("VERIFIER_CLEANUP_UNCERTAIN")
        return receipt

    def canary(self, contract: bytes, case: str):
        # Seed is never taken from an API, candidate or model. Persist the generated
        # CSV/manifest in the execution intent for exact replay, not in prompts.
        result = self.bounded({"operation": "canary", "contract": encode(contract),
                               "seed": secrets.token_hex(32), "case": case})
        if result["report"]["status"] != "processed":
            raise SupervisorError("CANARY_GENERATION_REJECTED")
        return result

    def execute(self, *, execution: UUID, job: UUID, generation: int, pipeline: bytes,
                contract: bytes, transactions: bytes, customers: bytes, purpose: str):
        if purpose not in ("original", "canary_ownership", "canary_quarantine"):
            raise SupervisorError("VERIFICATION_PURPOSE_INVALID")
        prepared = self.bounded({"operation": "prepare", "contract": encode(contract),
                                 "transactions": encode(transactions),
                                 "customers": encode(customers)})
        if prepared["report"]["status"] != "processed":
            raise SupervisorError("SOURCE_PREPARATION_REJECTED")
        data = prepared["report"]["result"]
        request = ExecutionRequest(execution, job, generation, pipeline,
                                   decode(data["transactions_jsonl"], 10 * 1024 * 1024),
                                   decode(data["customers_jsonl"], 10 * 1024 * 1024),
                                   decode(data["requirements"], 32768), data["include_rollups"])
        manifest = request.manifest_hash()
        intent = {"execution": execution.hex, "job": job.hex, "generation": generation,
                  "purpose": purpose, "manifest_sha256": manifest, "pipeline_sha256": sha(pipeline),
                  "contract_raw_sha256": sha(contract), "contract_sha256": data["contract_sha256"],
                  "transactions_sha256": sha(transactions), "customers_sha256": sha(customers),
                  "runtime_sha256": self.client.runtime_digest,
                  "verifier_rootfs": self.image_sha256}
        # The intent and exact sources survive uncertain delivery. Existing IDs are
        # never retried here: recovery must reconcile worker state explicitly.
        directory = self.journal / execution.hex
        fd = os.open(self.journal / "lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1:
                raise SupervisorError("VERIFICATION_JOURNAL_LOCK_INVALID")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # Includes failed/uncertain intents. No eviction or hidden retry to
            # reclaim capacity; later retention must reconcile worker ownership.
            if len(list(self.journal.iterdir())) >= 65:
                raise SupervisorError("VERIFICATION_JOURNAL_CAPACITY")
            directory.mkdir(mode=0o700)
            sync_directory(self.journal)
        finally:
            os.close(fd)
        synced_write(directory / "intent.json", canonical_bytes(intent))
        for name, raw in (("transactions.csv", transactions), ("customers.csv", customers),
                          ("contract.json", contract), ("pipeline.py.txt", pipeline)):
            synced_write(directory / name, raw)
        sync_directory(directory)
        sync_directory(self.journal)
        worker = self.client.create(request)
        synced_write(directory / "worker.json", canonical_bytes(worker, max_bytes=65536))
        sync_directory(directory)
        good = (worker.get("collected") is True and worker.get("cleanup") == "confirmed"
                and type(worker.get("runtime_client_exit_code")) is int
                and worker.get("runtime_client_exit_code") == 0
                and worker.get("unit_result") == "success")
        result = {"intent": intent, "worker": worker, "semantic": None}
        if good:
            captures = directory / "captures"
            captures.mkdir(mode=0o700)
            captured = self.client.capture_to(captures, execution, job, generation, manifest)
            names = ["ledger.jsonl", "unresolved.jsonl"]
            if request.include_rollups:
                names.append("rollups.jsonl")
            files = {}
            for name in names:
                with (captured / name).open("rb") as source:
                    raw = source.read(10 * 1024 * 1024 + 1)
                if len(raw) > 10 * 1024 * 1024:
                    raise SupervisorError("VERIFICATION_OUTPUT_LIMIT")
                files[name] = raw
            if sum(map(len, files.values())) > 10 * 1024 * 1024:
                raise SupervisorError("VERIFICATION_OUTPUT_LIMIT")
            result["semantic"] = self.bounded({"operation": "verify", "contract": encode(contract),
                "transactions": encode(transactions), "customers": encode(customers),
                "outputs": {name: encode(raw) for name, raw in files.items()}})
        synced_write(directory / "result.json", canonical_bytes(result, max_bytes=131072))
        sync_directory(directory)
        return result
