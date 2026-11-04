"""Frozen browser wire v1. Strict structural types; DB authority remains separate."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Identifier = Annotated[str, Field(pattern=r"^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$")]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Sequence = Annotated[str, Field(pattern=r"^(0|[1-9][0-9]{0,18})$")]
Kind = Literal["pipeline", "transactions", "customers", "contract"]
State = Literal[
    "QUEUED",
    "BASELINE_RUNNING",
    "BASELINE_VERIFYING",
    "RECONCILING",
    "NEEDS_REVIEW",
    "FAILED_INFRA",
    "CANCELLED",
]
Outcome = Literal[
    "match", "mismatch", "held", "input_rejected", "infrastructure_failed", "cancelled"
]


class Wire(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class BrowserSessionRequest(Wire):
    session_token: Annotated[str, Field(pattern=r"^pf_s_[0-9a-f]{64}$")]
    csrf_token: Annotated[str, Field(pattern=r"^pf_c_[0-9a-f]{64}$")]


class SessionResponse(Wire):
    workspace_id: Identifier
    kind: Literal["guest", "operator"]
    expires_at: str


class AssetResponse(Wire):
    asset_id: Identifier
    kind: Kind
    sha256: Digest
    bytes: Annotated[int, Field(ge=1, le=5242880)]
    validation: Literal["unvalidated"]


class ApprovalRequest(Wire):
    expected_sha256: Digest
    confirm: Literal[True]


class ApprovalResponse(Wire):
    asset_id: Identifier
    raw_sha256: Digest
    canonical_sha256: Digest
    approved: Literal[True]


class EnqueueRequest(Wire):
    idempotency_key: Identifier
    pipeline_id: Identifier
    transactions_id: Identifier
    customers_id: Identifier
    contract_id: Identifier


class EnqueueResponse(Wire):
    job_id: Identifier
    status_url: Annotated[str, Field(pattern=r"^/v1/jobs/[0-9a-f-]{36}$")]


class Finding(Wire):
    check: Annotated[str, Field(pattern=r"^V(0[1-9]|10)$")]
    code: Annotated[str, Field(pattern=r"^[A-Z_]{1,80}$")]
    source: str | None


class OwnershipWitness(Wire):
    check: Literal["V04"]
    source_row_id: str
    merchant_id: str
    customer_id: str
    expected_owner: str
    actual_owner: str


class JobSummary(Wire):
    wire_version: Literal["proofflow-browser-v1"]
    job_id: Identifier
    state: State
    outcome: Outcome | None
    created_at: str
    sequence: Sequence
    blocking_occurrences: Annotated[int, Field(ge=0, le=10000)] | None
    finding_count: Annotated[int, Field(ge=0)] | None
    findings: Annotated[list[Finding], Field(max_length=20)]
    ownership_witnesses: Annotated[list[OwnershipWitness], Field(max_length=3)]


class JobEvent(Wire):
    sequence: Sequence
    state: State
    event: Annotated[str, Field(pattern=r"^[a-z_]{1,80}$")]
    occurred_at: str


class ErrorDetail(Wire):
    code: Annotated[str, Field(pattern=r"^[A-Z_]{1,80}$")]
    message: str
    retryable: bool
    request_id: Identifier


class ErrorResponse(Wire):
    error: ErrorDetail


class CancellationResponse(Wire):
    cancellation_requested: Literal[True]


class RevocationResponse(Wire):
    revoked: Literal[True]


class DeleteRequest(Wire):
    workspace_id: Identifier
    confirm: Literal[True]


class DeleteResponse(Wire):
    access_revoked: Literal[True]
    deletion: Literal["queued"]


MODELS = (
    BrowserSessionRequest,
    SessionResponse,
    AssetResponse,
    ApprovalRequest,
    ApprovalResponse,
    EnqueueRequest,
    EnqueueResponse,
    JobSummary,
    JobEvent,
    ErrorResponse,
    CancellationResponse,
    RevocationResponse,
    DeleteRequest,
    DeleteResponse,
)
