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


class RepairRequest(Wire):
    parent_id: Identifier
    idempotency_key: Identifier


class RepairResponse(Wire):
    repair_id: Identifier
    status_url: Annotated[str, Field(pattern=r"^/v1/repairs/[0-9a-f-]{36}$")]


class PatchProposal(Wire):
    kind: Literal["propose_patch"]
    diagnosis: Annotated[str, Field(min_length=1, max_length=2048)]
    changed_file: Literal["pipeline.py"]
    candidate_source: Annotated[str, Field(min_length=1, max_length=16384)]
    expected_effect: Annotated[str, Field(min_length=1, max_length=2048)]
    uncertainties: Annotated[list[str], Field(max_length=5)]


class ClarificationProposal(Wire):
    kind: Literal["needs_clarification"]
    questions: Annotated[list[str], Field(min_length=1, max_length=5)]


class RejectedProposal(Wire):
    kind: Literal["rejected"]
    code: Literal["INVALID_PROPOSAL"]


class RepairAttempt(Wire):
    ordinal: Annotated[int, Field(ge=1, le=3)]
    request_id: Identifier
    outcome: Literal["PARSED_RESPONSE", "OUTCOME_UNKNOWN"] | None
    proposal: PatchProposal | ClarificationProposal | RejectedProposal | None


class RepairCheck(Wire):
    generation: Annotated[int, Field(ge=1, le=9)]
    attempt: Annotated[int, Field(ge=0, le=3)]
    purpose: Literal["candidate", "canary_ownership", "canary_quarantine"]
    comparison: Literal["match", "mismatch"] | None
    cleanup_confirmed: bool


class RepairEvent(Wire):
    sequence: Annotated[int, Field(ge=1, le=64)]
    occurred_at: str
    event: Annotated[str, Field(pattern=r"^[a-z_]{1,64}$")]


class RepairSummary(Wire):
    events: Annotated[list[RepairEvent], Field(max_length=64)]
    mode: Literal["original", "ai_repair"]
    checks: Annotated[list[RepairCheck], Field(max_length=9)]
    id: Identifier
    parent_id: Identifier
    state: Literal[
        "QUEUED",
        "RUNNING",
        "RECONCILING",
        "AWAITING_APPROVAL",
        "NEEDS_REVIEW",
        "FAILED_INFRA",
        "CANCELLED",
    ]
    outcome: str | None
    calls: Annotated[int, Field(ge=0, le=3)]
    reserved_micro: Annotated[int, Field(ge=0, le=500000)]
    created_at: str
    deadline: str | None
    attempts: Annotated[list[RepairAttempt], Field(max_length=3)]


class RepairExport(Wire):
    repair_id: Identifier
    candidate_sha256: Digest
    candidate_source: Annotated[str, Field(max_length=16384)]
    diff: Annotated[str, Field(max_length=131072)]
    activation_approved: Literal[False]


class VersionPrepareRequest(Wire):
    prepare_verified_source: Literal[True]


class VersionPrepared(Wire):
    version_id: Identifier
    pipeline_id: Identifier


class VersionPreviewRequest(Wire):
    intent_id: Identifier


class ApprovalBundle(Wire):
    schema_version: Literal["proofflow-approval-v1"]
    workspace_id: Identifier
    pipeline_id: Identifier
    version_id: Identifier
    repair_id: Identifier
    candidate_sha256: Digest
    contract_id: Identifier
    contract_sha256: Digest
    evidence_sha256: Digest
    runtime_sha256: Digest
    verifier_sha256: Digest
    verification_epoch: Sequence
    expected_active_version: Identifier | None
    pipeline_revision: Sequence
    revocation_epoch: Sequence
    actor_sha256: Digest
    intent_id: Identifier
    action: Literal["activate_exact_version"]
    created_at: str


class VersionPreview(Wire):
    intent_id: Identifier
    bundle: ApprovalBundle
    bundle_sha256: Digest
    expires_at: str


class VersionApprovalRequest(Wire):
    intent_id: Identifier
    bundle_sha256: Digest
    confirm: Literal[True]


class VersionApprovalResponse(Wire):
    version_id: Identifier
    approved: Literal[True]
    already_applied: bool


class VersionRevokeRequest(Wire):
    expected_revision: Sequence
    confirm: Literal[True]


class BatchRequest(Wire):
    version_id: Identifier
    transactions_id: Identifier
    customers_id: Identifier
    idempotency_key: Identifier


class BatchResponse(Wire):
    batch_id: Identifier
    status_url: Annotated[str, Field(pattern=r"^/v1/batches/[0-9a-f-]{36}$")]


MODELS = (
    VersionPrepareRequest,
    VersionPrepared,
    VersionPreviewRequest,
    VersionPreview,
    VersionApprovalRequest,
    VersionApprovalResponse,
    VersionRevokeRequest,
    BatchRequest,
    BatchResponse,
    RepairRequest,
    RepairResponse,
    RepairSummary,
    RepairExport,
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
