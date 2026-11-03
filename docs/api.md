# API and protocol plan

Public routes remain design-only; Phase2 now has local opaque-session/request parsing and PostgreSQL workspace/asset authorization components. Complete policy/schema freeze still awaits Q08; generated frontend types and route integration are unfinished. All lookups/mutations, streams, exports and downloads enforce workspace authorization; opaque IDs alone confer no access. Unknown fields fail. Browser gets no infrastructure secret or filesystem path.

The public API below remains planned. Phase 1 now implements a separate private TLS-framed worker protocol on fixed port 9443, with exact certificate/runtime identities, closed operations and durable transfer; it is not exposed to browsers. Its source and field rules are in worker/service.py, worker/wire.py and orchestrator/worker_client.py; setup/tests/limitations are documented in [sandbox](sandbox.md#authenticated-service-and-immutable-image-import--nov-4-follow-up). No private RPC result is a verifier or approval verdict.

| Endpoint | Planned contract |
| --- | --- |
| POST /v1/guest-sessions | Rate-limited expiring isolated workspace and secure cookie |
| POST /v1/assets | Stream multipart within byte cap; hash/quarantine; return asset ID and validation state |
| POST /v1/contracts | Validate declarative policy, explicit owner confirmation, immutable version |
| POST /v1/jobs | Asset IDs, approved contract, objective, Idempotency-Key; 202 + status URL |
| GET /v1/jobs/{id} | Durable state, attempts, budget, safe error, evidence references |
| GET /v1/jobs/{id}/events | SSE monotonic sequence, Last-Event-ID resume, 15s heartbeat |
| POST /v1/jobs/{id}/cancel | Idempotent durable cancellation; cleanup before terminal confirmation |
| POST /v1/versions/{id}/approve | Exact server bundle, action intent, expected active version, CAS |
| POST /v1/versions/{id}/revoke | Owner action with expected policy/version epoch and reason; audit/cancel guards |
| POST /v1/pipelines/{id}/batches | Fresh owned assets, scoped idempotency, bind active immutable version |
| POST /v1/integrations/batch-events | Scoped signed webhook; atomic delivery receipt and batch |
| POST /v1/versions/{id}/draft-pr | Operator approved concrete repo/base/path/diff preview; outbox status |
| GET /v1/artifacts/{id}/download | Fresh authorization, bounded attachment, sanitized filename, nosniff |
| GET /health/live and /health/ready | Process liveness vs dependencies; no secrets/stack traces |

Errors use error.code/retryable/message/request_id; restricted logs hold technical details. HTTP 400 malformed, 401/403 auth, 404 inaccessible object, 409 version/idempotency conflict, 413 size, 422 unsupported semantics, 429 quota, 503 transient dependency. Stable codes: INVALID_INPUT, UNSUPPORTED_PROFILE, CONTRACT_AMBIGUOUS, CANDIDATE_REJECTED, REPAIR_EXHAUSTED, EXECUTION_LIMIT, OUTPUT_INVALID, PROVIDER_UNAVAILABLE, WORKER_UNAVAILABLE, BUDGET_EXCEEDED, RATE_LIMITED, VERSION_CONFLICT, IDEMPOTENCY_CONFLICT, VERIFIER_UNAVAILABLE, INTEGRATION_FAILED. No error grants larger limits or automatic promotion.

Scoped API token stores only hash, pipeline/action scope, expiry/revocation. Webhook headers are ProofFlow-specific: connection ID, event ID, Unix timestamp, sha256 HMAC. Sign timestamp + newline + event ID + newline + exact raw body, validate constant-time before JSON, require +/-5-minute window, bound connection lookup. Same scoped ID/body returns original receipt; changed body gets 409. Invalid signature/stale delivery performs no fetch/job/model/write. No active approved version yields a clear rejection; failed batch stays held and may create a bounded repair incident needing new approval.

Frozen object inventory: AssetManifest (type/bytes/hash/workspace/validation); Contract; JobEvent (job/sequence/time/attempt/type/actor/safe payload); ExecutionReceipt (execution/job/generation/runtime/applied limits/start/end/exit or reason/captured bytes/truncation/cleanup); VerificationReport (version/job/attempt/verifier/input/candidate/contract/runtime/output digests/check IDs/status/expected/observed/witness/blocking count/verdict/times); ApprovalBundle (exact digests/IDs/expected active version/epochs/actor/intent/time); Error. The controller accepts verification only from its configured trusted service identity for exact stored hashes.

No API implementation or generated types are committed in Phase 0. Pin schema versions/hash vectors first; v1.1 downstream output and new reason codes are coordinated changes across collector, verifier, API, evidence and approval.

## Phase2 identity/asset components — private development only

`api/app/auth.py` creates separate256-bit random session/CSRF credentials, stores domain-separated hashes through the future DB client, hides raw values from repr, and produces a Secure/HttpOnly/SameSite=Strict `__Host-proofflow` cookie with Path=/ and no Domain. Raw ASGI headers preserve duplicates for rejection. Writes require an exact configured HTTPS Origin and CSRF header; Host/Forwarded never choose authority. Cross-site/same-site Fetch Metadata is rejected, with no Referer fallback. These checks are possession/framing, not workspace authorization; every operation must still call PostgreSQL for current expiry/revocation.22 unit tests cover forging/duplicate/control-byte/size/domain/expiry cases. Browser integration is NOT RUN.

`db/phase2/001_identity_assets.sql` creates a separate `proofflow_product` schema/database boundary, nonlogin owner, API and privileged provisioner roles. Only the provisioner creates workspaces/sessions or revokes a workspace; HTTP credentials cannot mint operator authority. API gets named functions, no tables/owner role/provisioning/internal-authorize access. Fixed search paths and qualified relations avoid shadowing. Database PUBLIC CONNECT/TEMP and public-schema CREATE are revoked by the migration, not merely by test setup. Deployment must separately create protected SCRAM login credentials and short connection/statement/idle-transaction timeouts; this migration creates no login/password or deployed service.

Guest sessions expire within1h, operator sessions within12h, never after workspace expiry (<=24h). Workspace row locks precede session locks. Asset writes serialize exact-CSRF authorization, idempotency and quotas against revocation; current expiries are checked after locks. All callers must commit the short function transaction immediately, with no external I/O inside it. A transaction already authorized/locked can complete before a racing revocation; after revocation commits it cannot newly authorize. No promise to recall bytes already delivered or stop a transaction at the exact wall-clock expiry instant is made.

Registry inputs are only pipeline/transactions/customers/contract, with existing per-kind byte bounds; outputs cannot be registered as user uploads. It stores unvalidated immutable metadata after durable byte publication; it is not a contract approval or verification.8 total workspaces,32 sessions/workspace,64 assets/128MiB per workspace are conservative private-development admission defaults. Expired/revoked rows still consume capacity until real retention/physical deletion reconciliation exists. No automatic quota increase. A known hash/foreign asset ID cannot authorize download. Product DB adapter, HTTP upload/download, rate limiting, retention, queue and live authentication remain unfinished.

References reviewed: [PostgreSQL security-definer functions](https://www.postgresql.org/docs/18/sql-createfunction.html), [row locking](https://www.postgresql.org/docs/18/explicit-locking.html), and [OWASP session management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html). Actual disposable PostgreSQL checks prove the named local SQL behaviors; these references alone do not prove our implementation.
