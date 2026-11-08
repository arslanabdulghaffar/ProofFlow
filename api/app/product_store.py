"""Fixed functions-only product DB adapter; each return follows acknowledged COMMIT."""

import asyncio
import os
from dataclasses import dataclass, field

import psycopg

from orchestrator.budget_store import BudgetConnection, BudgetUnavailable

API_OPERATIONS = {
    "judge_claim": ("SELECT pf_product.claim_judge(%s,%s,%s)", 3),
    "batch_event": ("SELECT pf_product.accept_batch_event(%s,%s,%s,%s,%s,%s)", 6),
    "batch_connection_revoke": ("SELECT pf_product.revoke_batch_connection(%s,%s,%s,%s)", 4),
    "pr_request": ("SELECT pf_product.request_pr_preview(%s,%s,%s,%s,%s)", 5),
    "pr_get": ("SELECT pf_product.get_pr_intent(%s,%s,%s)", 3),
    "pr_approve": ("SELECT pf_product.approve_pr(%s,%s,%s,%s,%s)", 5),
    "version_prepare": ("SELECT pf_product.prepare_version(%s,%s,%s,%s,%s)", 5),
    "version_get": ("SELECT pf_product.get_version(%s,%s,%s)", 3),
    "version_preview": ("SELECT pf_product.preview_version(%s,%s,%s,%s,%s)", 5),
    "version_approve": ("SELECT pf_product.approve_version(%s,%s,%s,%s,%s,%s)", 6),
    "version_revoke": ("SELECT pf_product.revoke_version(%s,%s,%s,%s,%s)", 5),
    "batch_enqueue": ("SELECT pf_product.enqueue_batch(%s,%s,%s,%s,%s,%s,%s,%s,%s)", 9),
    "batch_get": ("SELECT pf_product.get_batch(%s,%s,%s)", 3),
    "repair_enqueue": ("SELECT pf_product.enqueue_repair(%s,%s,%s,%s,%s,%s)", 6),
    "repair_bundle": ("SELECT pf_product.repair_bundle(%s,%s,%s)", 3),
    "repair_export": ("SELECT pf_product.export_repair(%s,%s,%s)", 3),
    "repair_get": ("SELECT pf_product.get_repair(%s,%s,%s)", 3),
    "repair_cancel": ("SELECT pf_product.cancel_repair(%s,%s,%s,%s)", 4),
    "browser_session": ("SELECT * FROM pf_product.browser_session(%s,%s)", 2),
    "delete": ("SELECT pf_product.request_deletion(%s,%s,%s)", 3),
    "session": ("SELECT * FROM pf_product.session_context(%s)", 1),
    "asset": ("SELECT * FROM pf_product.get_asset(%s,%s,%s)", 3),
    "reserve": ("SELECT pf_product.reserve_upload(%s,%s,%s,%s,%s,%s,%s)", 7),
    "publish": ("SELECT pf_product.complete_upload(%s,%s,%s,%s,%s,%s,%s)", 7),
    "approve": ("SELECT pf_product.approve_contract(%s,%s,%s,%s,%s)", 5),
    "revoke_contract": ("SELECT pf_product.revoke_contract(%s,%s,%s,%s)", 4),
    "enqueue": ("SELECT pf_product.enqueue_original(%s,%s,%s,%s,%s,%s,%s,%s,%s)", 9),
    "job": ("SELECT pf_product.get_job(%s,%s,%s)", 3),
    "events": ("SELECT pf_product.read_job_events(%s,%s,%s,%s)", 4),
    "cancel": ("SELECT pf_product.cancel_job(%s,%s,%s,%s)", 4),
    "logout": ("SELECT pf_product.revoke_session(%s,%s,%s)", 3),
}
DISPATCH_OPERATIONS = {
    "review_failure": ("SELECT pf_product.review_original_failure(%s,%s,%s,%s,%s)", 5),
    "pr_claim": ("SELECT pf_product.claim_pr(%s)", 1),
    "pr_preview_record": ("SELECT pf_product.record_pr_preview(%s,%s,%s,%s,%s)", 5),
    "pr_begin": ("SELECT pf_product.begin_pr_write(%s,%s,%s,%s,%s)", 5),
    "pr_readback": ("SELECT pf_product.record_pr_readback(%s,%s,%s,%s,%s,%s)", 6),
    "pr_defer": ("SELECT pf_product.defer_pr(%s,%s,%s,%s,%s,%s)", 6),
    "repair_original": ("SELECT pf_product.original_repair_candidate(%s,%s,%s,%s,%s)", 5),
    "repair_claim": ("SELECT pf_product.claim_repair(%s)", 1),
    "repair_heartbeat": ("SELECT pf_product.heartbeat_repair(%s,%s,%s,%s,%s)", 5),
    "repair_assets": ("SELECT pf_product.repair_assets(%s,%s,%s,%s)", 4),
    "repair_prepare": ("SELECT pf_product.prepare_repair_call(%s,%s,%s,%s,%s,%s,%s,%s,%s)", 9),
    "repair_response": ("SELECT pf_product.record_repair_call(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", 10),
    "repair_proposal": ("SELECT pf_product.repair_proposal(%s,%s,%s,%s,%s,%s)", 6),
    "repair_begin": ("SELECT pf_product.begin_repair_execution(%s,%s,%s,%s,%s,%s,%s)", 7),
    "repair_execution": ("SELECT pf_product.record_repair_execution(%s,%s,%s,%s,%s,%s)", 6),
    "repair_finish": ("SELECT pf_product.finish_repair(%s,%s,%s,%s,%s)", 5),
    "claim": ("SELECT pf_product.claim_original(%s)", 1),
    "heartbeat": ("SELECT pf_product.heartbeat_original(%s,%s,%s,%s)", 4),
    "assets": ("SELECT pf_product.dispatch_assets(%s,%s,%s,%s)", 4),
    "begin": ("SELECT pf_product.begin_original(%s,%s,%s,%s,%s,%s)", 6),
    "reject_input": ("SELECT pf_product.reject_original_input(%s,%s,%s,%s)", 4),
    "collected": ("SELECT pf_product.original_collected(%s,%s,%s,%s,%s,%s)", 6),
    "finish": ("SELECT pf_product.finish_original(%s,%s,%s,%s,%s)", 5),
    "fail": ("SELECT pf_product.fail_original(%s,%s,%s,%s,%s)", 5),
}
KNOWN_ERRORS = frozenset({
    "BATCH_CONNECTION_UNAVAILABLE", "BATCH_CONNECTION_INVALID", "BATCH_DELIVERY_INVALID",
    "BATCH_DELIVERY_CONFLICT", "BATCH_CONNECTION_CAPACITY", "BATCH_DELIVERY_CAPACITY",
    "GITHUB_NOT_CONFIGURED", "GITHUB_CONFIGURATION_INVALID", "PR_CONFLICT", "PR_CAPACITY",
    "EXACT_PR_APPROVAL_REQUIRED", "PR_AUTHORITY_REVOKED", "STALE_PR_LEASE", "PR_PREVIEW_INVALID",
    "PR_WRITE_ALREADY_PREPARED", "PR_READBACK_INVALID", "PR_DIAGNOSTIC_INVALID",
    "PR_RECONCILIATION_REQUIRED",
    "VERSION_NOT_ELIGIBLE", "VERSION_ASSET_MISMATCH", "VERSION_CONFLICT", "VERSION_CAPACITY",
    "EXACT_VERSION_APPROVAL_REQUIRED", "VERSION_NOT_FOUND",
    "REPAIR_PARENT_INVALID", "REPAIR_CALL_ALREADY_PREPARED", "REPAIR_BUDGET_EXHAUSTED",
    "REPAIR_OUTCOME_UNCERTAIN", "REPAIR_DEVELOPMENT_ALLOCATION", "REPAIR_RECEIPT_CONFLICT",
    "REPAIR_PROPOSAL_INVALID", "REPAIR_OUTCOME_INVALID", "REPAIR_PROOF_INCOMPLETE",
    "ACCESS_DENIED", "ASSET_QUOTA", "INVALID_ASSET", "ASSET_IDEMPOTENCY_CONFLICT",
    "UPLOAD_RESERVATION_REQUIRED", "EXACT_CONTRACT_REQUIRED", "CONTRACT_REVOKED",
    "ADMISSION_CLOSED", "INVALID_JOB", "JOB_IDEMPOTENCY_CONFLICT", "JOB_ASSETS_INVALID",
    "JOB_CAPACITY", "JOB_NOT_FOUND", "INVALID_EVENT_CURSOR", "STALE_JOB_LEASE",
    "JOB_AUTHORITY_REVOKED",
    "EXECUTION_INTENT_CONFLICT", "COLLECTED_EXECUTION_MISMATCH", "CLEANUP_REQUIRED",
    "ORIGINAL_REPORT_INVALID", "ORIGINAL_REPORT_BINDING_MISMATCH", "ORIGINAL_SOURCE_HASH_MISMATCH",
    "ORIGINAL_CONTRACT_HASH_MISMATCH", "ORIGINAL_OUTPUT_BINDING_MISMATCH",
})


class ProductFailure(Exception):
    """Fixed diagnostic only, never native SQL/DSN/credential text."""


@dataclass(frozen=True)
class ProductConnection:
    password: str = field(repr=False)
    role: str = "api"
    socket_directory: str = "/run/proofflow-budget"

    def parameters(self):
        if (self.role not in ("api", "dispatcher")
                or any(k.upper().startswith("PG") for k in os.environ)):
            raise ProductFailure("PRODUCT_CONFIGURATION_INVALID")
        try:
            parameters = BudgetConnection(self.password, self.socket_directory).parameters()
        except BudgetUnavailable:
            raise ProductFailure("PRODUCT_CONFIGURATION_INVALID") from None
        return {**parameters, "dbname": "proofflow_product",
                "user": "pf_product_" + self.role + "_login"}


@dataclass(frozen=True)
class ProductStore:
    connection: ProductConnection = field(repr=False)

    async def call(self, operation: str, *values):
        operations = API_OPERATIONS if self.connection.role == "api" else DISPATCH_OPERATIONS
        if operation not in operations or len(values) != operations[operation][1]:
            raise ProductFailure("PRODUCT_OPERATION_INVALID")
        try:
            async with asyncio.timeout(8):
                async with await psycopg.AsyncConnection.connect(
                    **self.connection.parameters(), autocommit=True, connect_timeout=3,
                    application_name="proofflow-product-" + self.connection.role,
                    options="-c default_transaction_isolation=read\\ committed "
                            "-c synchronous_commit=on "
                            "-c statement_timeout=5000 -c lock_timeout=2000 "
                            "-c idle_in_transaction_session_timeout=5000 -c search_path=pg_catalog",
                ) as connection:
                    async with connection.transaction():
                        for name in ("fsync", "full_page_writes"):
                            cursor = await connection.execute("SHOW " + name)
                            if await cursor.fetchone() != ("on",):
                                raise ProductFailure("PRODUCT_DURABILITY_UNAVAILABLE")
                        cursor = await connection.execute(operations[operation][0], values)
                        rows = await cursor.fetchmany(2)
                        if len(rows) > 1:
                            raise ProductFailure("PRODUCT_RESULT_INVALID")
                    return rows[0] if rows else None
        except psycopg.Error as error:
            code = error.diag.message_primary
            if code in KNOWN_ERRORS:
                raise ProductFailure(code) from None
            raise ProductFailure("PRODUCT_OPERATION_UNCERTAIN") from None
        except (OSError, TimeoutError):
            raise ProductFailure("PRODUCT_OPERATION_UNCERTAIN") from None
