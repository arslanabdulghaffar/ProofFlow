# Release and operations plan

## November8 ingress and recovery follow-up

Image `c65fa2203eed08f062f76a9c6a58d056119d1521e19af42091244ede201c7dc4` is deployed
privately with73 matching source files and both container policies verified. Strict
HTTPS authority is active; optional protected origin config remains absent/private.
[Public edge preparation](../infra/public-demo/README.md) supplies host-validated disabled
TLS passthrough units, guest constraints, activation/rollback steps and a no-domain IP
certificate option. No public socket, certificate, firewall or shared invitation exists.

Recovery now checks expiry after materialization. Actual fresh encrypted two-DB restore
and old-session/runtime-login denial pass; actual updated-image tmpfs timeout/cleanup
passes. [Evidence](evidence/phase6-ingress-recovery-2026-11-08.json). Lost deletion authority
and compromised-host recovery remain unproven; owner offline key custody is deferred.
The existing video/package retain their historical source/image. Refresh the private
source package for these changes without overwriting the earlier sealed artifact.
Fresh credit$189.27, caps and Nov10 01:29 KST cutoff unchanged. No new resource/model call.

## Private release package — November8

The [package source and guide](../release/README.md) now include8-slide deck,cover,
existing real-AI video,draft submission fields/copy,safe setup notes and a manifest
builder. Exact reviewed media hashes are in [assets.json](../release/assets.json).
The builder requires clean committed source and never calls cloud/publishing APIs.
It verifies native comparison values,ZIP membership/hash/commit identity and private
gate flags. [Final package readback](evidence/phase6-release-package-2026-11-08.json)
passes: 13 files, 4,729,372 bytes, including a 486-file tracked source snapshot from
verified checkpoint `d6dfceae1d22a901442f85e0dc5440ad4149993a`. The ZIP is outside Git
in the owner's private release directory. Do not rebuild it merely to include its
later receipt commit; the manifest and receipt explicitly distinguish those commits.

This is private review readiness,not Phase6 completion or public release. The owner
deferred offline key custody. Public repository/demo/media and permissive licensing
remain unapproved; authenticated form/deadline/registration remain unverified. Keep
public URLs null. Existing$150/$25 credit caps and Nov10 01:29 KST cutoff remain intact.
No resource,inference request,cloud charge category or runtime dependency was added.

## Phase6 current status — November8, private scheduled recovery and recorded AI demo

[Current evidence](evidence/phase6-scheduled-portable-demo-2026-11-08.json) supersedes
the dated open-work statements below. Actual scheduled backup, nonempty capture and
portable Windows-to-Linux inert recovery now pass. Final private edited video is139.04s;
original clips and receipts stay outside Git. Phase6 remains IN PROGRESS for portable
authority/compromised-host recovery, owner custody and the final public package/gates.

The existing desktop task `ProofFlow-ProductBackup` runs as the current interactive user
with limited privileges/no stored password. It checks hourly and captures at12h or2h
before expiry. It needs this machine awake/logged in; busy/failed capture is a visible
retry,not a successful backup. Latest actual capture:185,228 SQL bytes,1 synthetic asset,
snapshot Nov8 01:35 KST,expires **Nov9 01:35 KST**. Even a not-due check authenticates the
encrypted envelope/key. Latest receipt is `scheduled-backup-latest.json`; task status is
`scheduled-backup-task-last.json` in the private deployment directory. Preserve pending
receipts; reconcile before retry. Existing vault expiry remains enforced.

Optional owner custody: run this in a private interactive PowerShell terminal:

```powershell
powershell -NoProfile -File "A:\hackathon\ProofFlow\scripts\Export-PortableBackup.ps1"
```

Enter a unique long recovery password only at the hidden prompts,
then copy the displayed encrypted kit to secure offline storage and keep the password
separately. No password is saved by the helper or requested in chat. This has NOT been
completed by the owner. Expiry is not extended by export; destroy copies by their expiry.
Exported keys cannot be remotely erased,so this is synthetic operator custody rather
than an enforced guest-data retention claim. Recover with `recover_portable` only after
obtaining fresh authenticated trustworthy deletion authority. The package itself is
never that authority. Existing quarantine/strip/recheck rules below still apply.

The real portable test used an ephemeral random in-memory password and authenticated
inert bytes on Linux, then excluded them after deletion using the SAME package. It did
not execute its SQL dump, restore production or reconstruct a compromised host. The
prior actual separate-DB restore drill remains the SQL/quarantine evidence; together
these are scoped proofs,not an end-to-end host disaster or measured production RTO.

New funded review verified$190.13 credit and unchanged$72/month VM quotes,$145 reservations
and$150/$25 caps. Cutoff is now **Nov10 01:29 KST**; do not replay either completed renewal.
Provider hard stop/taxes are unknown. No card/payment/new resource/PR/public action.
Judging uptime beyond this cutoff requires another fresh bounded review,not a bypass.
Both admissions are closed after recording; public readiness is not claimed.

The139.04s video records one real Vultr call,three fresh matching checks and exact test
activation/new batch. The batch's completion is a labeled actual-receipt summary because
the raw browser clip moved on too quickly. Separate loop clip/readback confirms kill
and cleanup. Two failed harness receipts remain failed and reconciled. `demo.md` lists
the filenames,hash and edit disclosure. No new paid attempt was used to conceal them.

Earlier dated entries below remain historical evidence,not current gate status.

## Phase6 current status — November7, private WIP

[Recovery and rehearsal evidence](evidence/phase6-recovery-rehearsal-2026-11-07.json)
now covers a consistent PostgreSQL export, encrypted recovery in a separate fresh
database instance, a real off-VM vault capture and current private-browser rehearsal.
Phase6 is not DONE: scheduled nonempty backups, portable keys/current deletion
authority, compromised-host reconstruction, final live AI recording and public package
remain separate gates. Public release, MIT ownership and submission remain unapproved.

`scripts/consistent_product_backup.py` holds a fixed read-only exported MVCC snapshot
while reading the workspace/asset inventories and running pg_dump with that snapshot.
Only trusted fixed Docker/Unix-socket commands are admitted. Output is bounded while
reading; the final helper has a50-second shared client deadline,55-second container-owned
kill deadline and45-second SQL/60-second abandoned-transaction timeouts. No plaintext
dump is written to disk. This improves capture under concurrent writes; earlier
quiesced fixture backups remain valid scoped evidence. Official PostgreSQL
[snapshot synchronization](https://www.postgresql.org/docs/current/functions-admin.html#FUNCTIONS-SNAPSHOT-SYNCHRONIZATION)
and [pg_dump snapshot option](https://www.postgresql.org/docs/current/app-pgdump.html)
were checked November7. A dump is executable trusted-admin SQL, never an upload to run.

Actual disposable recovery used two distinct network-denied PostgreSQL containers.
Concurrent workspace/asset commits were excluded from the shared snapshot. Deleted
and revoked workspaces stayed excluded; all24 runtime-authority tables were emptied,
surviving workspace access remained revoked, normal logins were refused and a deletion
during recovery invalidated the plan. Both containers/volumes and temporary data were
removed.20.824 seconds measured the entire small synthetic fixture, not a production
RTO or fresh-host rebuild. RPO24h/RTO60min remain targets.

The live one-shot `check_phase6_backup_live.py` captured the then-empty private product
without stopping its services:184,540 SQL bytes,zero assets. AES-GCM envelope plus
current-user DPAPI key survived the actual off-VM vault roundtrip; exact database bytes
were authenticated in memory. This live capture predates the later independent55s
process-timeout hardening, which passed the separate local real-database drill. Do not
replay its completed receipt. Its key expires **November8 18:04:03 KST**; existing vault
expiry enforcement must remain active. An expired snapshot is not a usable backup.

### Disaster runbook and honest stop points

1. Keep product/inference admission closed. Preserve the incident evidence and record
   the trusted source/image hashes. Never restart a known compromised predecessor.
2. Recover the envelope/key only through the vault under the same Windows identity.
   Missing profile/key, failed authentication, expiry or clock-floor uncertainty is a
   stop. Do not restore an older vault clock file to revive a key.
3. Obtain current deletion authority from an authenticated trustworthy source. A stale
   backup inventory cannot replace it. If that authority was lost with the host, data
   recovery is currently blocked; this is the portable-disaster gap to solve.
4. Restore only a trusted dump into a new isolated `proofflow_restore_<uuidhex>` database,
   created with connection limit zero. Require the exact reviewed schema and quarantine
   plan; strip sessions, approvals, repair allocations/intents and other runtime authority.
   Restore hash-checked inert assets only for currently eligible workspaces; re-read
   deletion authority before accepting the result. Never overwrite production.
5. A quarantined data check is not permission to promote it. Reimaged-host trust, new
   scoped credentials, source/runtime checks, spending controls and real containment
   probes are required before any future promotion. Compromised-dump execution and
   new paid services are outside this tested drill.

No object-storage service, backup schedule or new paid resource was enabled. The
existing$145 reservation and$150/$25 caps remain; fresh credit was about$191. Funded
review still expires **November8 23:27 KST**, earlier than the previously recorded
submission target. Do a new bounded funded review before that cutoff; do not replay
the completed November6 renewal, raise caps or promise post-event uptime from balance
alone. The guard may tear down resources at its cutoff. Do not disable it for filming.

Phase5 private technical acceptance passes after binary review and two-host149 kernel
patch/reboot;all16 new containment probes and exact deployed-source checks pass.
[acceptance evidence](evidence/phase5-binary-acceptance-2026-11-07.json). This closes the previous Phase5 audit,not Phase6 release gates. Admission remains
closed;repository private. Next work is the existing Phase6 portable/scheduled recovery,
clean-browser rehearsal,media/package/source agreement and funded-uptime plan. Public
publication/submission/license clearance remain unresolved. Do not rerun completed
kernel maintenance,API rebuild,encrypted recovery,comparison,renewal or product PR.
Earlier Phase5-open statements below are historical.

Actual private API-container rebuild now passes with unchanged image/source pins,
preserved revoked sessions/data and normal cleanup. Expanded installer checks require
the full security configuration,not just image identity. [Evidence](evidence/phase5-runtime-incident-2026-11-07.json). This does not establish
fresh-host/credential-compromise recovery or public readiness. Phase5 remains open.
Do not replay the completed one-shot incident drill or restore its stopped predecessor.

Latest private image is e64a0040b23a347b264c5aacf4e66687bdd8c8f8e84da4f95e8d3e6a3ed6e358;
72 source matches and deployed auth/inert-upload smoke pass after cancelled-work
capacity hardening. Worker/verifier/schema/epoch5 unchanged. Product/inference remain
closed and readiness remains503 until release acceptance. No publication authorized.
[Checkpoint evidence](evidence/phase5-http-cancellation-2026-11-07.json).

Current status: Phase0–4 DONE;Phase5 security/evaluation IN PROGRESS. Actual private
runtime/provider/repair/approval/fresh-batch/PR evidence and the final comparison exist.
Encrypted off-VM DB+asset recovery into inert quarantine passed, including current
deletion exclusion and cleanup; vault crash/clock checks also pass. [Recovery](evidence/phase5-encrypted-recovery-2026-11-07.json),
[hardening](evidence/phase5-vault-native-review-2026-11-07.json). These are not portable
disaster recovery, scheduled consistent backups or production promotion. The older
backup helper retains its guest/deletion gate. Broader security review remains open.

Final-release clean-browser rehearsal, public endpoint/package/video and publication
are NOT RUN. Public release/submission and repository visibility changes require
explicit owner authorization. MIT ownership and independent human review gaps remain;
finish concrete artifacts/tests before requesting consequential approval. Existing
deployment/tests are not reset to NOT RUN merely because release work is unfinished.

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
