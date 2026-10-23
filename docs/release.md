# Release and operations plan

All deployment, backup, restore, clean-browser and runtime gates are NOT RUN. Public release/submission and repository visibility changes require later explicit owner authorization. MIT ownership clearance and independent human review gap remain recorded; do not invent either. Finish concrete artifacts/tests before requesting any required consequential approval.

Provision in order after Phase 1 gate: eligible account/credit and bounded charges → actual region/VM quote (2vCPU/4GiB control, 4vCPU/8GiB worker are sizing assumptions) → private network/mTLS and allowlisted SSH → supported OS/security updates/time sync/key-only named admins → private DB/artifact volumes/roles → pinned Docker/runsc and probes → secret files/services → HTTPS/secure cookies → actual provider → real smoke. No public database/Docker API; worker RPC restricted to control. API status may remain available when admission is disabled by unhealthy verifier/worker/runtime/storage/inference configuration.

Release sequence: reviewed source/tag → immutable builds/locks/image scan → real required checks → encrypted consistent DB dump and referenced-artifact backup → additive migration tested on copy → deploy manifest → readiness → fresh public repair/approval/batch/containment smoke → dated release record with evidence/limits. Keep previous known-good images and schema compatibility notes. Rollback cannot revive revoked approvals, duplicate outbox writes or rewrite failed history.

Backup design: restic to private Vultr S3-compatible storage with separate credentials/password file; actual compatibility, locking/listing/prune and billable minimums must be tested. At least daily/pre-release consistent DB+artifact snapshot. Restore into a separate environment, verify job/version/approval relations/hashes/tombstones/outbox, replay benign approved code in sandbox, measure time. Up to 24h loss and <=60min recovery are targets, not measured service levels. Expire backup snapshots within policy; no production overwrite as a restore test. An authorized owner keeps recovery credentials securely out of chat/source.

## Stop/go inventory mapped to PDF p53

| Gate | Required linked evidence before release claim |
| --- | --- |
| G-01 rules | Registration, track, timing clarification, current form |
| G-02 scope | Owner-approved contract, supported/unsupported inputs and worked examples |
| G-03 stack | Actual Vultr VM web/backend, provider calls and sandbox receipts |
| G-04 autonomy | Actual generated code and new inputs without hidden human repair |
| G-05 correctness | Independent per-record/mutation/canary checks |
| G-06 boundaries | Runtime, tenant, secret, upload/output, quota and cleanup evidence |
| G-07 durable result | Exact approval, new batch, authorized download, actual integration status |
| G-08 reliability | Restart/replay/cancel/provider-failure/restore/clean-browser results |
| G-09 comparison | Prior-art attribution, held-out methodology/baselines/raw results/limitations |
| G-10 demo | Final-release live execution, containment and disclosed fixtures/replay |
| G-11 package | Authorized public repo/app, license/notices, cover/video/deck, descriptions/links and confirmation |
| G-12 availability | Funded judging uptime, alerts, named owner, backup/cleanup plan |

A credential leak, crossed workspace, unsandboxed/unbounded code, false acceptance or fabricated result blocks the affected release until repaired/retested. Optional omissions are removed from claims. Low repair coverage is reported rather than hidden. Missing real PR readback is an integration gap, not an export success. Final source/deployment/evidence/evaluation/video/copy must agree.

## Operational signals and runbooks

Logs use request/job/attempt/execution IDs, lease generation, release and workspace pseudonym; no raw records/secrets/full prompts. Track queue/model/execution/verification time, check outcomes, queue slots/depth, memory/disk/inodes, expired leases, cleanup lag, provider usage-known flag/reservations, outbox age/readback, webhook rejects and external HTTPS plus benign workflow health. Alerts must pause admission before exhaustion. Budget and uptime plan in eval/plan.md.

- Provider unavailable: stop bounded retries, preserve state/uncertain cost, show failure; deliberate retry only within remaining budget.
- Worker unhealthy: stop admission, reconcile known executions/deadlines, clean server-owned leftovers, rerun containment probes before reuse.
- Wrong acceptance: revoke affected versions/digests, hold future batches, preserve evidence, fix verifier and re-evaluate; never edit statuses manually.
- Disk/DB failure: stop writes, use known-good release or tested restore, reconcile artifact hashes/outbox and deletion tombstones before resuming.

After submission, the owner is the only currently known on-call person; availability is unconfirmed. Check TLS, credit/cost liabilities, health, queues, cleanup and integration permission daily during judging; scheduling a future monitor requires a separate request. Avoid feature changes invalidating evidence; security/availability fixes get a new release record. Revoke unused keys/resources only once obligations and funding are resolved.

Submission inventory: title/short and >=100-word long description, technology/category tags, platform, public app/repo/video/deck links, cover, track, actual evaluation report and release manifest. General title/summary/video limits remain provisional until form read. Save timestamp in KST+UTC, confirmation, URLs/file hashes/release ID; record actual reviewer identity or review gap. No submission is performed in Phase 0.

Post-event roadmap is deferred: permissioned pilot/data/provider terms and real workflow baseline; managed DB/secrets/tenant hardening/load measurements; new profile-specific schemas/evaluators/adversarial tests; enterprise SSO/service objectives/security review. These are not current capabilities or certifications.
