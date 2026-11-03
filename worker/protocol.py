"""Internal authenticated-controller values; no public deserializer or commands."""

import hashlib
import json
from dataclasses import dataclass
from uuid import UUID

INPUT_NAMES = ("pipeline.py", "transactions.jsonl", "customers.jsonl", "requirements.json")


class SupervisorError(Exception):
    """Fixed diagnostics only; no candidate bytes, secrets or external paths."""


@dataclass(frozen=True)
class ExecutionRequest:
    execution_id: UUID
    job_id: UUID
    generation: int
    pipeline: bytes
    transactions: bytes
    customers: bytes
    requirements: bytes
    include_rollups: bool = False

    def inputs(self) -> tuple[bytes, ...]:
        return self.pipeline, self.transactions, self.customers, self.requirements

    def manifest_hash(self) -> str:
        if (type(self.execution_id) is not UUID or type(self.job_id) is not UUID
                or type(self.generation) is not int or not 1 <= self.generation <= 2147483647
                or type(self.include_rollups) is not bool
                or any(type(data) is not bytes for data in self.inputs())):
            raise SupervisorError("INVALID_EXECUTION_REQUEST")
        if (not 0 < len(self.pipeline) <= 16384 or not 0 < len(self.requirements) <= 32768
                or len(self.transactions) + len(self.customers) > 10 * 1024 * 1024):
            raise SupervisorError("STAGED_INPUT_LIMIT")
        manifest = {"execution": self.execution_id.hex, "job": self.job_id.hex,
                    "generation": self.generation, "rollups": self.include_rollups,
                    "inputs": {name: hashlib.sha256(data).hexdigest()
                               for name, data in zip(INPUT_NAMES, self.inputs(), strict=True)}}
        return hashlib.sha256(json.dumps(manifest, sort_keys=True,
                                         separators=(",", ":")).encode()).hexdigest()


def execution_name(identifier: UUID) -> str:
    if type(identifier) is not UUID:
        raise SupervisorError("INVALID_EXECUTION_ID")
    return "proofflow-exec-" + identifier.hex


def runtime_identity_digest(identity: dict) -> str:
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
