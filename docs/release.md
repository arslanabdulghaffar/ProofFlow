# Release and operations plan

## November8 KST — recovery receipt and funding reconciliation hardened

Saved recovery/export now reject an unfinished backup pointer and a pointer replaced
while waiting. SQL recovery re-reads the vault after rehearsal so retired keys cannot
be accepted from memory. The scheduler's not-due path also binds capture time to the
authenticated envelope. No older receipt is silently substituted and no offline key
prompt/export was performed.

Added read-only `review_credit_window.py --inspect --review-date 2026-11-08`.
Actual saved receipt, local cutoff and deployed budget match; no deadline extension.
Partial remote/local/completion states receive distinct non-success reports and never
retry UPDATE. The old cutoff stays authoritative; no stop is reopened. Fixed errors
avoid leaking native SQL/account diagnostics.103 scoped tests and Ruff pass.

Actual authenticated185228-byte scheduled SQL restore passes again in fresh local
RAM-only PostgreSQL: one deleted workspace excluded, all24 authority tables cleared,
ordinary login denied and container removed.6.218s is a small rehearsal duration, not
production RTO. Scheduler authenticated the existing backup and correctly said not_due.
[Evidence](evidence/phase6-recovery-funding-reconciliation-2026-11-08.json).

Fresh13:18 KST hosting preview: credit $188.85; $24/$48 monthly VM plans; additional
14-day compute estimate $36 inside the existing $72 compute/$145 total reservations.
Caps remain $150/$25. Funded cutoff remains Nov10 01:29:33 KST. Official post-event
payment-method wording is unchanged; no card, new resource, model call or promise of
judging-period access. Backup expiry remains Nov9 01:35 KST; hourly scheduler's next
due capture is after13:35 KST and still requires closed/idle services and awake Windows.

Phase6 IN PROGRESS: full compromised-host trust/credential rebuild, lost deletion
authority, post-event eligibility, publication/license/submission and human review
remain open. Offline custody is deferred. Do not repeat paid acceptance or regenerate
the dated v4 archive for these operator-only changes. No deployed product change.

## November8 KST — live operations check and release instructions reconciled

Added `scripts/check_operations.py`: one-shot TLS/health, authenticated backup,
Windows task, pinned-host service/storage and credit/budget readback. Actual run at
13:10 KST passed its scoped checks: credit $188.85, unchanged $150/$25 caps and
Nov10 01:29:33 KST funding cutoff. Certificate expires Nov15 01:01:59 KST;
current backup expires Nov9 01:35:14 KST. Both scheduled tasks last returned zero.
[Sanitized evidence](evidence/phase6-operations-check-2026-11-08.json).

Twenty regression tests cover stale/failed tasks, backup expiry/authentication, TLS,
service/storage pressure, budget drift, missing probes, redaction and false readiness.
The initial harness used the foundation readiness reason; corrected against actual
product source. Public liveness is 200; readiness remains 503
`product_acceptance_incomplete`. SCOPED_OK is explicitly not phase acceptance.
README/setup/test-plan now describe actual guest access and implemented commands.
No new resource, model call, admission, deployment change or public release.

Phase6 remains IN PROGRESS. Preserve dated private v4; no media regeneration needed.
Offline custody is deferred. Fresh compromised-host trust/credential rebuild, lost
current deletion authority, post-event access, license/publication/submission and
independent human review remain open. The checker is not a background monitor;
existing credit/backup tasks still require the owner's Windows session awake.

## November8 KST — actual saved SQL restore and deadline fix accepted

The latest authenticated scheduled185228-byte SQL backup restored into a fresh local,
networkless, nonroot PostgreSQL container using tmpfs only. One saved workspace was
excluded by current live deletion authority; all24 runtime-authority tables cleared,
normal login denied, fresh live authority rechecked and container removed. Small-snapshot
rehearsal5.18s, observed snapshot age11.4h: neither is a production RTO/RPO guarantee.
No production import, credentials restored, candidate execution, cloud resource or model call.

Fault testing found BusyBox timeout as namespace PID1 did not stop the empty PostgreSQL
fixture by90s. Harness detected failure and cleaned up. Require existing Docker-provided
init; unchanged90s deadline now yields exit137 and AutoRemove after91.487s, after launcher
exit and without observer cleanup. Exact tmpfs readback corrected (HostConfig.Tmpfs,
not Mounts); actual filesystem type and resource/network/process policy are checked.
28 Windows tests pass/1 Linux-only skip;29 Linux tests,Ruff and documentation checks pass.
[Evidence](evidence/phase6-saved-database-release-audit-2026-11-08.json).

Release G01–G12 now has concrete scoped statuses and evidence links. The pinned local
product image still matches all73 approved files. The live deployment and private v4
archive were preserved. No need to regenerate media or replay paid acceptance for this
admin-tool change. Phase6 IN PROGRESS: fresh compromised-host trust/credential rebuild,
lost current deletion authority, owner offline custody (deferred), post-event access,
publication/license/submission and independent human review remain open. Existing caps
and Nov10 01:29:33 KST cutoff unchanged. New helper is a trusted-admin rehearsal only;
never supply uploaded or suspected-compromised SQL. No remaining temporary containers.

## November8 KST — recovery denial drill and judging-hosting preparation

Eight actual fresh local pinned recovery containers passed: valid inert materialization,
deleted-workspace exclusion, missing/stale/future authority, wrong key, corrupted envelope
and expired backup. Every denial returned the expected fixed error with no data; every
container was removed. No production restore, candidate execution or owner offline key.
42 Windows tests pass/1 Linux-only skip, plus5 Linux tests pass and Ruff. A read-only
hosting harness result-shape error was fixed and regression-tested; no remote mutation.
[Evidence](evidence/phase6-recovery-hosting-2026-11-08.json).

Fresh account/VM/ledger readback at12:32 KST: credit$188.96; existing plans$24+$48/month.
Additional7/14-day compute estimates$18/$36; full$72 compute and$145 total reservations
remain unchanged, with$150/$25 caps. Created-to-final-cutoff compute estimate$49.18.
These estimates exclude unknown taxes/overages and do not establish post-event eligibility.
Current funded cutoff remains **Nov10 01:29:33 KST**; absolute stop Nov23 09:00 KST.
No extension or new resource. `scripts/prepare_judging_hosting.py` performs GET/SELECT
only and can recheck current quotes/ledger without closing an owner's active guest window.

Official event page still says post-event deployments require a payment method, contrary
to owner-relayed judging guidance. Record the conflict once; no card, inferred clearance,
repeated approval request or promise of two-week uptime. Future extension uses existing
closed/idle, fresh-account48-hour review only; never bypass its latched stop or caps.
Renewal and guest timers active; certificate expires Nov15 01:01:59 KST, next renewal
check Nov8 21:00:44 KST, last renewal result0. Future production rotation remains unobserved.
Desktop credit guard12:29/backup11:36 KST last result0; awake/logged-in dependency remains.

Phase6 IN PROGRESS. Offline custody deferred; lost-authority/fresh compromised-host
recovery, post-event access and publication/license/submission remain open. Preserve
private v4 as a dated package; this later operational evidence is in Git. Do not rebuild
the same archive or replay completed paid tests merely to refresh its date.

## November8 KST — private release v4 sealed and read back

Source checkpoint `0d2dff6217899f6029178bcc83c3cf59d16a0682` is verified on remote main. The private v4 ZIP
contains17 files and522 source files; entire source ZIP matches a fresh
Git archive byte-for-byte. SHA-256 `38467ff5a5afe080abbd28fe82a5808c96a97fc540e9bae94bd49d87d5069a63`.
[Readback receipt](evidence/phase6-release-package-v4-2026-11-08.json). Bundle location:
`C:/Users/IT/.proofflow/release/2026-11-08/ProofFlow-private-release-v4.zip`.
Trusted-hash verification, CRC, media/source binding and a missing-required-receipt
negative probe pass. v1-v3/video/deck preserved. No publication, export password,
paid model call or runtime change. Phase6 remains IN PROGRESS with the scoped gaps below.

## November8 KST — recovery receipt and private package verification hardened

Offline export now binds the scheduled receipt to authenticated ciphertext, capture time
and expiry before prompting. It re-reads the vault after the password wait (a retired key
must stay retired) and checks expiry again after encryption. Owner custody remains deferred;
no password was requested or export created. Actual current-profile backup authenticated:
185228 database bytes and1 inert asset, expiry Nov9 01:35:14 KST. This is not a live restore
or current deletion-authority proof. Backup11:36/credit guard12:14 KST last task results0.

Private package verifier now binds documents/media to the bundled source/pins, accepts a
separately trusted ZIP hash, and requires the full v2 file set. New bundle includes guest
AI/expiry evidence and this recovery review; original video/deck provenance stays intact.
36 scoped tests, Ruff, frozen comparison and historical v3 trusted-hash readback passed.
[Evidence](evidence/phase6-recovery-release-hardening-2026-11-08.json).

Separate critical pass checked key retirement during the prompt, receipt substitution,
expiry after encryption, package self-consistency versus trusted provenance and no archive
execution. No deployed image/policy/dependency change, paid call, new resource, visibility
change or human sign-off. Preserve owner guest work. Phase6 remains IN PROGRESS: offline
custody deferred; compromised-host rebuild/lost authority/RTO-RPO, post-cutoff hosting and
license/publication/submission gates remain. Do not rerun paid acceptance merely to refresh
these receipts. Funded cutoff remains Nov10 01:29 KST; credit caps unchanged.

## November8 KST — bounded guest launcher and real public AI workflow accepted

Current owner-ready window: ACTIVE until **Nov8 12:34:59 KST**. Exactly one guest,
zero assets/jobs; no model call or approval during launch/readback. Run the launcher to
open this window; after expiry it creates a fresh one only after current checks/cleanup.
A final review found dispatcher startup could precede the timer's boot check; installed
Requires+After guard dependency and verified an actual idle restart runs guard first.
This does not claim another full-host reboot or compromised-host recovery.

The owner can run `powershell -NoProfile -File "A:\hackathon\ProofFlow\scripts\Open-PublicDemo.ps1"`.
It opens a dedicated signed-in guest browser with labeled synthetic files selected.
It does NOT upload, approve a contract/version or call the model automatically. Review
and click those controls in the UI. No credentials in chat/Git/URLs; CurrentUser DPAPI
and owner/SYSTEM ACL protect the short-lived access envelope outside Git. Normal direct
URL access still shows login; this is invited access, not anonymous signup.

One workspace/session per30-minute window, fresh credit/VM/model quote, fixed caps and
existing isolated worker. A source-pinned root systemd guard checks every10s on control;
expiry/reboot/backwards clock/invalid state closes inference then execution. Database
workspace/session expiry and provider quote expiry also apply. It does not depend on
the Windows desktop being awake. Real20s window test: automatic closure9.945s after
expiry, expired public access403, both admissions closed, normal retention leaves0
workspaces. No schema/app image/provider/cap change; image441d3a remains deployed.

Actual public guest AI run passed: first candidate mismatched and was rejected; second
candidate plus ownership/quarantine checks matched, all four cleanups confirmed. Two
Vultr calls reserved$0.055706 (not invoice). Exact synthetic automated approval followed
by a fresh batch COMPLETED; no PR intent. Test guest deleted and admissions closed.
966 Windows tests pass/191 platform skips;18 scoped Linux pass;Ruff passes. First setup
failed token-format validation safely; use existing auth validators, with regression.
[Evidence](evidence/phase6-guest-operation-2026-11-08.json).

Keep private Git/media, credit-only$150/$25 limits and funded cutoff Nov10 01:29 KST.
Latest credit$189.06 at12:01 KST; no new resource or personal payment. Offline custody
is deferred. Full compromised-host/lost-authority recovery, judging uptime, license/
publication/submission and independent human review remain open. Phase6 IN PROGRESS.
No need to repeat the same paid acceptance run. `guest_demo.py stop` closes a window
and requests normal deletion; it does not edit outcomes. An expired/closed window may
be replaced only after fresh checks and normal prior-workspace cleanup. Partial failed
intents/active work are reconciled, never blindly replaced. Guest guard's CLOSED/no-window
state intentionally leaves other explicit administrator tests under their own controls.

## November8 KST — public TLS source checkpoint and private package v3 verified

Source checkpoint `72f6800c1a356bdd7ad4ffdc22f552e3578b86fc` pushed to main and matched by remote SHA;
repository private verified. New private archive `ProofFlow-private-release-v3.zip` has15 files,
509 source files and4793703 bytes. SHA-256 `1dff901b4516f070ab1b748c420ae40cdc4ca091d9986c5e516cbfea76b56a7a`.
Independent ZIP/source/committed-byte/media readback passed. [Receipt](evidence/phase6-release-package-v3-2026-11-08.json).
Location: `C:/Users/IT/.proofflow/release/2026-11-08/ProofFlow-private-release-v3.zip`.
Previous archives/video/deck preserved. Package now contains the accepted public URL
and scoped TLS/guest/restart evidence; package/repository/media remain private.

Next authorized work should target remaining recovery/guest-operating readiness, not
repeat completed certificate issuance or the same tests. No shared live invitation;
execution/inference closed after test cleanup. Do not blindly rerun one-shot installers
or dated receipt scripts. Funded cutoff Nov10 01:29 KST remains; use a fresh bounded
review before extending uptime. Offline owner custody deferred; lost-authority restore,
fresh compromised-host reconstruction, public source/license/submission and human review
remain incomplete. Phase6 is IN PROGRESS, not falsely marked DONE.

## November8 KST — public guest TLS and restart recovery accepted

Owner explicitly authorized public TLS/guest testing. https://158.247.227.66:8443 is
live with a publicly trusted IP certificate; repository and media remain private.
Separate networkless guest API rejects operator tokens. Private operator TLS/SSH stays
intact. Image `441d3a417149242c7afb1f6ae72a355865b8515f2416ff02f92a0deb1cf50a74` runs
all three product roles;73 exact source files and container policies verified.

Four clean external Chromium guest contexts passed actual worker execution: mismatch,
mismatch,match,held; refresh, mobile layout and revoked logout access passed. Additional
actual public checks passed cross-workspace download denial, wrong-origin denial, guest
PR denial, expired sessions, valid access after restart and revocation after restart.
No new product PR or inference request. Public trust uses no certificate bypass.

Certbot5.9.0/18 hash-locked packages live outside app/worker runtimes. Staging/production
issuance, staging renewal dry-run, trusted deploy-hook/no-op and scheduled service passed.
Timer runs twice daily with systemd jitter; duplicate Certbot sleep is disabled to stay
inside the240s bound. Certificate expires Nov15 01:01 KST, but funded VM cutoff remains
**Nov10 01:29 KST**. Fresh credit **$189.17** at10:11 KST, VM quotes$24+$48/month,
$150 total/$25 inference caps unchanged. No new resource or personal payment.

Windows949 pass/191 platform skips; Linux40 scoped pass; Ruff clean. Failed firewall
propagation probes, an overloaded browser revocation probe and an invalid-ID harness
attempt remain preserved/reconciled. Limits/auth policy were not weakened. Review is
Codex/automated, not independent human sign-off. [Evidence](evidence/phase6-public-tls-2026-11-08.json).

Final state: public login available, zero test workspaces, execution/inference admissions
CLOSED. Guest invitation and bounded operating admission are required before live use;
no anonymous signup/shared credential. Full compromised-host rebuild/current-deletion-
authority recovery and judging-period hosting remain open. Offline owner custody is
deferred. Phase6 remains IN PROGRESS; public repo/license/media/submission are separate.

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
The existing video/package retain their historical source/image. A new private source
package v2 is verified from checkpoint `414dd13a7a35192be1418577f3dcdbb5a5e4bbaa`:
14 files,497 source files,4,754,204 bytes. [Readback receipt](evidence/phase6-release-package-v2-2026-11-08.json).
The earlier sealed artifact remains intact; media are unchanged and truthfully dated.
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

| Gate | Current assessment | Evidence and remaining work |
| --- | --- | --- |
| G-01 rules | PARTIAL | Event/track verified; enrollment, authenticated form and absolute deadline remain unverified. See [rules](rules.md). |
| G-02 scope | SCOPED PASS | Approved synthetic-only contract including Q08; each exact contract still requires product approval. [Contract](contract.md). |
| G-03 stack | SCOPED PASS | Actual Vultr VM/provider/sandbox accepted. [Phase1](evidence/phase1-acceptance-2026-11-04.json). |
| G-04 autonomy | SCOPED PASS | Real bounded repair and new batch on the invited guest path; no generalized arbitrary-code autonomy claim. [Guest run](evidence/phase6-guest-operation-2026-11-08.json). |
| G-05 correctness | SCOPED PASS | Source-derived record checks/protected canaries; exact finite profile, not formal proof. [Phase3](evidence/phase3-acceptance-2026-11-04.json). |
| G-06 boundaries | SCOPED PASS / REVIEW GAP | Containment/runtime review and guest denials pass; native/administrator limits and missing independent human review remain disclosed. [Phase5](evidence/phase5-binary-acceptance-2026-11-07.json), [public checks](evidence/phase6-public-tls-2026-11-08.json). |
| G-07 durable result | SCOPED PASS | Exact activation, fresh completed batch, owned downloads and real private PR readback/recovery. [Phase4](evidence/phase4-acceptance-2026-11-05.json). No additional PR authorized. |
| G-08 reliability | PARTIAL | Restart/replay/cancel and isolated backup recovery pass. Actual scheduled SQL quarantine is now tested; fresh compromised-host trust/credential reconstruction and production RTO/RPO remain unproven. [Recovery](evidence/phase6-saved-database-release-audit-2026-11-08.json). |
| G-09 comparison | SCOPED PASS | Frozen measured arms, attribution and limitations; no customer ROI or universal repair-rate claim. [Comparison](../eval/final-comparison-2026-11-06.md). |
| G-10 demo | SCOPED PASS | Real private AI recording/containment, later public TLS/guest rehearsal; dated recording is not footage of later runs. [Media](evidence/phase6-release-assets-2026-11-08.json). |
| G-11 package | BLOCKED PUBLIC RELEASE | Private v4 archive verified; repository/media remain private, license ownership, public URLs and submission confirmation unresolved. [Package](evidence/phase6-release-package-v4-2026-11-08.json). |
| G-12 availability | PARTIAL | Current credit/caps/timers and conditional judging cost plan verified; post-event account access, future funding reviews and on-call availability unconfirmed. [Hosting](evidence/phase6-recovery-hosting-2026-11-08.json). |

These are scoped evidence assessments, not a blanket release approval. Phase6 remains
IN PROGRESS. Owner-deferred offline custody is separate from already completed recovery
experiments. No snapshot is a replacement for lost current deletion authority.

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
