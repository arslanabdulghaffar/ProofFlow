# Progress

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

## November8 KST — visible Windows browser launcher repaired

The owner reported missing `chromium-1248/chrome-win64/chrome.exe`: prior acceptance
used the separate installed headless shell, so it did not prove the visible launcher.
Installing the matching CFT package exposed a second Windows side-by-side assembly
activation failure. No Windows security policy or system runtime was changed to bypass it.

Windows launcher now uses Playwright's installed Microsoft Edge channel with a fresh
nonpersistent profile. It launches the real visible browser BEFORE guest credential
access, provider refresh or admission. Missing/failing browser therefore cannot open a
new demo window. The browser closes on later setup failure. Two regression tests and
six access-envelope tests pass. Actual visible Edge157.0.4341.42 launch and the full
existing-window login/file-selection path passed: workspace visible, login fields cleared,
run disabled, contract unchecked. A separate Edge guest window was left open for the
owner; no automatic upload/approval or new model call. Existing window expiry remains
Nov8 12:34:59 KST; no deadline extension or new guest was needed.

Repository stays private. This repairs local browser setup only; app/worker/TLS image,
spending caps and server expiry guard are unchanged. The earlier headless tests remain
valid for their stated scope; they did not cover native visible-browser installation.

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

Scheduled credit guard recovered from RETRY_REQUIRED during serialized administration:
actual task LastTaskResult0 at10:14 KST, balance$189.17. Local key expiry checked3 records;
last scheduled backup09:36 KST/result0. No backup custody or always-on guarantee implied.

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

## November8 KST — refreshed private source package verified

Ingress/recovery source checkpoint `414dd13a7a35192be1418577f3dcdbb5a5e4bbaa` was pushed
and matched to main. New private release v2 passes independent readback of14 files,
497 tracked source files, all CRC/hashes, source identity, committed media pins and
native table/source agreement. ZIP size4,754,204 bytes. The prior ZIP remains intact;
video and deck keep their actual original runtime/evidence rather than claiming a new
recording. [Receipt](evidence/phase6-release-package-v2-2026-11-08.json). No publication,
model call, new resource or personal spending. Public and full disaster gates remain.

## November8 KST — public-demo preparation deployed; recovery expiry and replay checked

Deployed strict HTTPS authority handling on the existing private API, with protected
future-origin configuration and no public listener/default signup. Wrong/duplicate
Host, forwarded-header spoofing and plaintext scope are denied before data access.
Both roles run image `c65fa2203eed08f062f76a9c6a58d056119d1521e19af42091244ede201c7dc4`;
73 exact source files/container policy match. Native/Python dependencies are unchanged.
Prepared bounded TLS passthrough units; actual host validates them without activation.
Private TLS smoke passes. The documented IP-cert option avoids a domain purchase.

Fixed frozen-start-time expiry in inert recovery and tested authority/workspace/backup
expiry during materialization. Real separate-DB restore passes14 groups, with old sessions
and normal logins denied after all runtime authority is stripped. The first added probe
expected a session error under a role that intentionally lacks restored schema grants;
fixed the harness to separately verify ACL denial and admin-invoked session lookup.
No permission was restored to make the test pass. Fresh container tmpfs recovery and
independent kill/cleanup pass (21.797s). No production promotion or host rebuild claimed.

928 Windows tests pass/191 platform skips;161 scoped Linux tests and6 later HTTP-probe
tests pass. Initial raw event fixture lacked Host; fixed fixture, not policy. First
network-disabled image build missed its cache; normal build reused unchanged pinned
dependency layers. Local systemd verification lacked the deployed service dependency;
actual control-host validation passed. All failures remain disclosed.

Credit$189.27, prior caps/cutoff retained, no new service or model request. Backup task
last observed09:36 KST/result0. Owner offline custody deferred. Repository remains private;
public certificate/activation/external acceptance, license/submission, lost-authority
recovery and judging-period funding remain open. No independent human sign-off.

## November8 KST — verified private package checkpoint

Source commit `d6dfceae1d22a901442f85e0dc5440ad4149993a` was committed, pushed and
matched to remote main. Built the 4,729,372-byte private ZIP from that clean commit:
13 outer files, including eight-slide editable deck, standalone cover, existing video,
submission draft, evidence, setup and 486-file tracked source snapshot. Separate
readback passed outer/source CRCs, manifest hashes, exact membership, source-commit
identity, reviewed asset pins, document consistency and native comparison table checks.
Receipt: `evidence/phase6-release-package-2026-11-08.json`. The archive remains local
and private; only sources, tests, sanitized hashes/evidence and handoff are committed.

Private deck/cover/package task is complete. Phase6 remains IN PROGRESS for public
authorization and access, licensing/ownership, actual form/enrollment/deadline checks,
recovery gaps and judging-period hosting. Offline key custody stays owner-deferred.
No cloud/model calls or new spending commitments for this package; existing funded
service charges continue. No independent human sign-off. No new PR or submission.

## November8 KST — Phase6 private deck, cover and release package

Prepared8 editable slides with actual synthetic screenshot,3 native evidence tables
and source-linked speaker notes,plus standalone1920×1080 cover. Final-file structure,
font/layout and Artifact Tool re-import checks pass; all8 slides visually reviewed.
Fixed fallback-font export and one source-note filename; no product/runtime changes.
Existing139.04s video and its disclosed failed-harness reconciliation are preserved.

Added private submission fields/copy,setup notes and deterministic file selection for
an offline release ZIP. Source comes from a clean committed `git archive`; media are
pinned by SHA-256. Public URLs stay null; license/release flags stay false. The deck's
native comparison table agrees with the offline frozen artifact,including the better
deterministic baseline. Eight archive/XML/claim negative checks pass. No candidate or
model invocation. Package assembly/readback follows the first source checkpoint,with
its separate receipt committed afterward; do not confuse prepared sources with a
verified archive before that receipt exists.

Owner deferred offline key custody; recorded without re-prompting. Event page/dashboard
rechecked,but authenticated form/deadline/registration remain unknown. No public action,
new paid service,credit renewal or application dependency. Phase6 remains IN PROGRESS
for release authorization,public smoke and recovery/uptime gaps.

Packaging review added 13 durable guard tests. The first pass had one failure because
Windows normalizes ZIP backslashes; corrected the raw-byte probe and rejected filename
normalization in the reader. All 13 now pass, plus the eight actual-deck/negative probes.
The final comparison heading says "Held / clarified" to cover both correct outcomes.
Sanitized asset validation is in `evidence/phase6-release-assets-2026-11-08.json`.

## November8 KST — Phase6 scheduled capture, portable recovery and real AI media

Installed hourly current-user backup task with12h capture cadence/early expiry refresh,
bounded consistent DB/asset capture, authenticated AES/DPAPI readback and visible retry.
Actual nonempty backup contains185,228 SQL bytes and1 inert synthetic asset; expires
Nov9 01:35 KST. Task ran successfully after added not-due integrity checking. Desktop
login/awake dependence is explicit; no always-on RPO claim or new storage service.

Real Windows-to-Linux password-wrapped recovery passes before deletion, then excludes
the same asset after normal deletion. Current authority remains mandatory. Owner-held
offline password/kit and lost-authority/compromised-host recovery remain unfinished.
No plaintext SQL materialization/execution or candidate execution on the desktop.

Recorded one actual Vultr repair:1 call,$0.027853 reservation,changed source,3 fresh
matching isolated checks,ZIP download,exact automated synthetic approval and a new
completed batch. Both deliberate loops terminated/cleaned up. Two demo harness errors
remain failed/reconciled; neither product states nor verifier acceptance were changed.
Final139.04s private MP4 has clear edits/paused frames/separate loop/receipt-summary
labels, plus original videos and manifest. Full decode and frame review pass. No PR.

Separate critical pass fixed earliest asset retention timestamp, not-due backup health
checks and exceptional recording flush.83 scoped Linux/42 Windows tests pass (21 new
unique cases); no independent human sign-off. Product/worker/verifier images and schema
unchanged. Local FFmpeg only, no new cloud/runtime dependency. [Evidence](evidence/phase6-scheduled-portable-demo-2026-11-08.json).

Readback569 CLEANED/344 fences,zero missing deadlines/workspaces/clones,healthy services,
both admissions closed. Credit$190.13. New dated funding review extends existing cutoff
to Nov10 01:29 KST with the same$145 reservation/$150 project/$25 inference caps. Earlier
renewal and frozen comparison remain untouched. Private WIP checkpoint,not Phase6 release
completion; public package/ownership/submission/disaster-authority gaps remain.

## November7 KST — Phase6 consistent backup and clean-browser rehearsal

Added a bounded exported-snapshot coordinator so asset inventory and pg_dump describe
one committed database state. Separate review added an independent55s container-owned
deadline; killing the Docker client or timing out SQL alone is insufficient to bound
a client blocked on output. No product/schema/contract/verifier/dependency changes.

Actual two-instance encrypted restore passed13 groups,including concurrent commits,
ended exporter reuse,interruption,missing current authority,deletion exclusions,
quarantine/schema checks and cleanup.20.824s is a small local fixture duration,not an
RTO. Live existing empty-product capture184,540 bytes passed actual off-VM AES/DPAPI
roundtrip; no services stopped. Snapshot expires Nov8 18:04 KST. Scheduled/portable
recovery is still incomplete; completed live backup receipt must not be replayed.

Four current clean-browser original cases passed(mismatch/mismatch/match/held),plus a
separate no-AI original/three protected checks/download/exact approval/fresh batch path.
Screenshots and ZIP retained privately; fresh inputs remain template-derived synthetic
tests,not independent held-out evaluation. Preserved two failed harness attempts and
their normal cleanup; amended sample/HTTP transport only,not acceptance policy.

41 scoped Linux tests(12 new),Ruff and documentation checks pass. Separate Codex review
is not independent human sign-off. Final readback562 CLEANED,339 fences,zero missing
deadlines/workspaces/clones;both admissions closed,three services healthy. Credit$190.88;
no inference/new resource/PR/publication. Source remains private. [Evidence](evidence/phase6-recovery-rehearsal-2026-11-07.json).

Phase6 WIP checkpoint,not release completion. Demo narration now ties each scene to
actual evidence and identifies remaining real-AI recording/public package gates.
Funded review cutoff Nov8 23:27 KST remains earlier than the old submission target;
a fresh bounded review is required before then. No caps raised or old renewal replayed.

## November7 KST — binary review, kernel fix and Phase5 acceptance

Completed the bounded private Phase5 acceptance audit. A critical TCP vulnerability
in the installed host kernel required a real fix: both VMs upgraded from147 to signed
Ubuntu149 and rebooted sequentially. Exact packages/new boot IDs/integrity verified;
all16 post-update worker probes pass with cleanup.72 source matches and full service
policy readback pass;548 CLEANED/327 fences/zero unfinished retention fixtures.

Go binary analysis closes the prior zero-package scanner gap for five binaries;three
small ELF C helpers received separate source/disassembly review.18 distinct Go IDs
remain recorded with module/package/symbol distinction. Added fail-closed reporting
of missing metadata,scanner errors and warnings;JSON exit0 never means clean.21 new
boundary tests;1044 Linux+10 subtests,870 Windows/174 skips. No runtime/contract/verifier
policy relaxation. README's stale Phase3-only status corrected.

[acceptance evidence](evidence/phase5-binary-acceptance-2026-11-07.json). Original Phase5 private technical gates pass,with DONE contingent on verified
push. Phase6 disaster/release work and independent human review remain explicit gaps.
No product PR,model call or new service. Credit$191.85;caps/cutoff unchanged.

## November 7 KST — runtime exposure and real service rebuild

Found/fixed incomplete existing-container acceptance: exact image alone did not deny
changed security flags,mounts,commands or several resource/namespace settings.28
new negative/positive cases pass;actual API and dispatcher match expanded checks.
Deployed trusted installer update changes no application image or runtime policy.

Actual API reconstruction passed on the existing trusted control VM,with closed
admissions and unchanged durable workspace/session/assets plus job/version/PR counts.
Revoked token remained denied;fresh login retrieved identical bytes;72 exact source
files verified. Stopped predecessor retained,synthetic workspace normally deleted.
This does not claim recovery of a compromised host or lost credentials.

Eight worker runtime files verified;worker has no Docker/containerd daemon. Control
daemon2.4.2 is distinct from vulnerable2.1.5 in gVisor source dependencies. CRI is
loaded locally;no CDI specs or containerd TCP service.20 source findings remain;
binary scanner recognized no packages,so no clean-binary result claimed. Official
release/config/advisory review recorded without suppressions. Initial read-only
probe assumed absent worker tools existed; explicit absence handling corrected it.

1023 Linux+10 subtests,849 Windows/174 skips,Ruff. Fresh credit$191.85;existing funded
window/caps unchanged. No new resource,model call,worker candidate or PR. [Evidence](evidence/phase5-runtime-incident-2026-11-07.json).
Phase5 remains IN PROGRESS pending remaining runtime coverage and acceptance audit.

## November 7 KST — cancelled-work capacity fixed and deployed

Found and reproduced a semaphore lifetime gap: timed-out/disconnected HTTP requests
left executor work running but reopened admission. Fixed all API asset IO and bundle
builds to hold their bounded slots until the real thread finishes. Original regression
had3 failures/1 pass; final7 new cases pass, including actual HTTP deadline cancellation,
orphan errors,late upload without registry publication and revocation before disclosure.
Full995 Linux+10 subtests and821 Windows/174 Linux-only skips pass.

Deployed image e64a0040b23a347b264c5aacf4e66687bdd8c8f8e84da4f95e8d3e6a3ed6e358 with72
source matches, unchanged dependencies/worker/verifier/schema/approval semantics.
Actual private HTTP CSRF,hostile inert attachment,revoked/foreign download and foreign
approval checks pass; normal deletion left zero workspaces. Initial fixture session
lifetime and cleanup-status assertions were corrected with failures preserved.
No jobs,provider calls,new resources or PR intents added. Updated-image data-only
recovery and independent20s kill/cleanup pass; live lifecycle healthy/closed. Fresh
credit$192.06 and Nov8 23:27 KST review remain within unchanged credit-only caps.
[Evidence](evidence/phase5-http-cancellation-2026-11-07.json). Phase5 remains IN PROGRESS;
broader host/runtime advisory and incident-rebuild coverage are not claimed complete.

## November 7 KST — vault crash/race fixes and refreshed native review

Also fixed decrypted temporary-file survival after a killed recovery process. The
bounded local data-only runner uses private tmpfs and a container-owned20-second
timeout. Actual inert recovery and forced termination/removal pass; no candidate code
executes locally, no original live job/restore was replayed. Five final driver-boundary
Linux tests/four Windows tests pass after the full suites, including two new cases.

Fixed overlapping/partial backup operations with exclusive OS locking, flushed atomic
publication, interrupted-save cleanup, persistent clock floor and post-read expiry
checks. A damaged key no longer delays unrelated authenticated expiry. Thirteen fixture
tests plus actual Windows concurrent-process/process-death/interrupted-save and natural
key-expiry checks pass. Two diagnostic/harness failures are preserved; no key/ACL widening.

Fresh exact-product scan has49 HIGH/75 MEDIUM/62 LOW/zero CRITICAL pairs;186 pairs are
unchanged, severity ratings changed. Official advisory review and actual product/worker
mapped-library hashes and read-only journal schema inspection narrow the inspected
paths without suppressing any finding. Broader native/runtime review remains open.
986 Linux tests+10 subtests;813 Windows/173 skips. Product runtime and frozen comparison
unchanged. Credit$192.17,caps/funded deadline unchanged; no inference/new resource.
[Evidence](evidence/phase5-vault-native-review-2026-11-07.json). Phase5 IN PROGRESS;
Phase6 recovery/rehearsal/media/publication deliverables remain distinct.

## November 7 KST — encrypted assets recovered; replay/deletion expiry deployed

Actual off-VM AES-GCM DB+asset recovery passed: normal deletion excluded one synthetic
workspace; four authorized assets recovered byte-for-byte into inert quarantine, all
runtime authority stripped, fresh deletion authority rechecked, clone/bytes/key removed.
Two harness failures and exact-backup resumes are preserved; no job replay or new PR.
Windows private ACL/DPAPI roundtrip and natural key expiry pass. The guard now checks
backup expiry even when its independent credit check fails.

Time-bound worker/workspace IDs, persistent clock floors, bounded seven-day cleaned
record/fence/completed-deletion pruning and idle-root marker expiry are deployed.
Unfinished work remains quarantined; unknown legacy/expired IDs cannot regain admission.
Actual readback:532 cleaned records,311 fences,zero missing deadlines, healthy services,
no remaining recovery fixture or clone. Twenty migrations/epoch5/current pins are in
the [handoff](next-session.md). Natural seven-day elapsed-time acceptance is NOT RUN.

970 Linux tests+10 subtests;797 Windows/173 Linux-only skips; seven real PostgreSQL
restore and seven deletion-expiry groups;16 deployed worker security probes pass.
Credit$192.17, unchanged caps/funded deadlineNov8 23:27 KST; no new service or inference.
[Evidence](evidence/phase5-encrypted-recovery-2026-11-07.json). Phase5 remains IN PROGRESS;
native advisory/human review and portable disaster/production recovery gaps remain.

## November 7 KST — receipt expiry deployed; deletion-safe recovery rehearsal passes

Detailed cleaned receipts now expire after seven days without deleting execution IDs,
conflict manifests or generation fences. One persisted legacy grace, quarantine-safe
recovery and physical SQLite/WAL removal are covered by five meaningful tests. Actual
deployed migration/readback confirms515 cleaned receipts/294 fences/zero missing
deadlines after16 fresh containment/resource/capture/timeout/cleanup probes. Natural
seven-day wall time has not elapsed. Product/runtime pins and epoch4 are recorded in
the [handoff](next-session.md);72 exact source files verified,18 migrations unchanged.

A real disposable PostgreSQL restore excludes completed/pending deletions using fresh
current authority, blocks runtime logins before import, removes all authority in the
clone, and detects deletion during recovery. Six groups and14 policy tests pass.
This is local synthetic metadata-only recovery, not production restore or encrypted
asset backup. The clone is dropped; no live data/status was rewritten.

940 Linux tests plus10 subtests;779 Windows tests/161 Linux-only skips; Ruff/hygiene
pass. Preserved initial security-runner failure before any probe: an expired historical
PR row was gone. Fixed current outbox rowset hashing and reran successfully, without
creating a PR. Credit$192.38; API/dispatcher/retention active, admissions closed,
funded deadlineNov8 23:27 KST unchanged. No new service/inference call/personal payment.
[Evidence](evidence/phase5-metadata-restore-2026-11-07.json). Phase5 remains IN PROGRESS:
negative-authority TTL/capacity, full backup/restore and known native/human review gaps.

## November 6 KST — final comparison audited; funded hosting review passed

All 96 predeclared jobs completed with no paid replay. Actual receipt audit reconciled 79 provider responses, candidate provenance, original failures, fresh protected checks, global reservations, all closures and 24 normal API retirements. [Report](../eval/final-comparison-2026-11-06.md): A 15/18 repairs, 6/6 holds/clarification, 0/15 incorrect acceptance; B 14/18, 1/6, 9/23; C 15/18, 6/6, 0/15; deterministic D 18/18, 6/6, 0/18. Preserve the interrupted A, five exhausted model runs, polling-only amendment, shared template and absent human oracle review. No A/C quality-superiority claim. Usage estimate $0.060841; $2.200387 held, no settlement.

Fresh account/plan/identity/idle/ledger review extended only the existing funded window to November 8 23:27 KST. Verified remaining credit $192.92, full $145 allocation and $150/$25 caps unchanged, no new services or personal payment. SQL/local expiry and a subsequent actual guard readback agree. Admissions are closed. [Evidence](evidence/phase5-final-comparison-2026-11-06.json). Phase 5 remains IN PROGRESS: metadata/fence/tombstone lifecycle, restore coupling and documented native/human review gaps remain; release and publication are not authorized.

## November 6 KST — portable comparison artifact and funded review prepared

Added an allowlisted synthetic report export and offline dataset/oracle/denominator/metric recheck. Seven tampering tests pass; candidate source remains inert data and protected canaries, provider responses and account identities stay outside the artifact. Final export awaits actual receipt reconciliation. A reviewed administrator helper can renew the unexpired existing hosting window by at most 48 hours after fresh credit/quotes/identity and unchanged reservations, without raising caps or opening admission. Twenty-one offline funding tests pass, including interrupted SQL updates and replay denial. Actual renewal is NOT RUN at this checkpoint.

Full suites before the four final interrupted-write tests: 913 Linux plus 10 subtests; 757 Windows with 156 Linux-only skips. The campaign is still running; frozen sources, product runtime and scoring remain unchanged. Phase 5 remains IN PROGRESS.

## November 6 KST — offline evidence audit prepared during final comparison

The real 96-job comparison is progressing beyond its preserved interrupted prefix. Added bounded read-only receipt collection and offline request/quote/global-ledger reconciliation, exact candidate provenance, unchanged source/runtime classification, three fresh accepted proofs, baseline acceptance before grading, and complete dispatch/closure/product-retirement checks. No new provider calls, execution, refund, activation or external write is performed by this audit. Actual final collection and scoring remain pending; failed runs are retained.

Full local suites passed: 883 Linux tests plus 10 subtests; 727 Windows tests with 156 Linux-only skips. Six additional lifecycle-audit cases pass in the focused 32-test receipt/collection set. Separate Codex critical review is recorded; no independent human sign-off. Source/runtime/grader/cases used by the ongoing campaign are unchanged. Phase 5 remains incomplete pending actual final evidence and metadata/restore lifecycle work.

## November6 KST — nine dispatches preserved; transport recovery prepared

After polling amendment, two real full-API A cases pass with one call each. Eight completed accepted/correct runs plus the interrupted A are preserved;9 closures verified. A read-only SSH preflight timeout and subsequent management preflight failure stopped before job10. Fresh account and full closed/idle/image/service checks passed, credit$193.02. New no-replay suffix recovery has6 tests; offline receipt reconciliation has14 tampering/unknown-usage tests. Remaining87 jobs and final actual receipt audit/report are pending; do not infer full repair quality from this prefix.


## November6 KST — actual comparison started, interrupted prefix preserved

Frozen96-job comparison ran completeness-1 B/D/C successfully (2/0/1 prepared model calls, accepted/correct). A polling harness omitted BASELINE_RUNNING/BASELINE_VERIFYING and stopped before repair; closure cancelled its original normally, confirmed worker cleanup. All four records preserved; no repeated run. Fixed polling and prepared a single-use, exact-prefix continuation with unchanged cases/prompts/runtime/grader/caps and explicit source-amendment disclosure. Seven amendment tests and two polling tests added;31 Windows API/launcher/amendment checks pass. Remaining92 jobs and final reconciliation still pending; no full score or Phase5 completion claim.


## November6 KST — finite campaign launch controls

After verified ffb91c9, added the finite96-job launcher with prospective hashes/quote policy, exact IDs, existing global/per-job caps, isolated trusted controller mounts, independent cutoff timers and fail-closed cleanup. Six launch fault tests plus two ineffective-original tests raise the focused comparison set to53 passing Linux checks;21 API/launcher checks pass on Windows. Final campaign not launched at this entry; no score or Phase5 completion claim. Proceed with live preflight after clean committed source.


## November6 KST — comparison adapters WIP

Added B/C/D bounded orchestration and a full-product API A adapter after verified bd6829c. Forty-five local Linux checks pass:16 controller,15 API/proof,14 durable journal. B acceptance is persisted before grading and survives grading failure as unknown; fresh proof/source/runtime bindings reject tampering. A preserves exact IDs/evidence before writes, never activates/creates a PR, and retires only completed synthetic workspaces through normal deletion. No deployment/model call/final freeze or score in this checkpoint. Phase5 remains IN PROGRESS; finite campaign launch/reconciliation and lifecycle work remain. Separate Codex review is not human approval.


## November6 KST — final comparison infrastructure WIP

Verified609bb0f checkpoint and continued. Added a dedicated bounded B/C receipt journal with14 passing Linux security tests, preserving the unchanged global spending ledger/transport and100-row probe limit. No final freeze, launch, model call or deployed image change. Four new synthetic workspaces retired normally;4 SQL completions/byte-absence/restore markers verified,2 preexisting workspaces remain. Phase5 remains IN PROGRESS; final controllers/campaign and metadata/restore lifecycle still require work. See the separate review; no independent human sign-off.


## November6 KST — real API code-failure repair passed

Phase0–4 DONE; Phase5 IN PROGRESS. Continued from6b59d0ef without an owner prompt. Full-product evaluation preparation found original crashes could not enter repair. Added source-only diagnosis and truthful execution_failed status, while source ambiguity remains held and outputs are never declared verified. Additive017/018 migrations, bounded source operation, UI/types and controller receipt redaction are deployed. Original crash passed; initial missing-output probe failed closed on successful stopped-unit exit-kind0. Preserve it. New018 also requires positive host cgroup observations/exact limits; fresh missing-output and invalid-source checks pass. No contract/verifier comparison/canary expectation or candidate limit changed.

Actual retained crash then passed through the real API/queue/Vultr/worker path:1 model call,3 fresh executions (candidate/ownership/quarantine), all cleanup confirmed, awaiting exact activation approval. No activation or PR. Held reservation$0.027853; provider usage estimate$0.0009993, not settled billing. Shared development reservation$1.339265. [Evidence](evidence/phase5-source-repair-2026-11-06.json).

Current product image200257609d3fa99f53829ab1cb9493e77a646f08afd2090abb947120d0388131, verifier rootfs0290920d63d9b55108c83d300922f5af84608147495f340e86025fc0e599e63b, worker unchangedc826cf6662bcb4495cb744e34b9944044ade193fd870ca5a7bef140d3150dd78.18 migrations installed,72 exact image files. New verifier epoch3 invalidates prior activations normally; do not rebind approvals.788 Linux tests+10 subtests;664 Windows/124 Linux skips;6 new SQL failure groups,11 original queue groups,5 repair groups,6 actual bounded-verifier groups and7 deployed HTTP groups/3 cases pass. Separate Codex review is not independent human approval.

Credit$193.13 at12:42 UTC Nov6; job/inference admissions closed, API/dispatcher/product-retention timer active, guard review deadline unchanged2026-11-06T21:05:35.177139Z. The original owner workspace has expired and normal retention removed its product PR rows; historical PR#1 acceptance remains valid evidence, no GitHub deletion/write occurred in this work. The first service readback queried the wrong retention timer name; corrected named readback is active. No new cloud service/dependency or personal payment.


## November6 KST — worker preview retirement deployed and checked

After verified67920adc pilot checkpoint, fixed the remaining indefinite raw failure-preview storage. Indexed300-second deadlines, one-time legacy grace, secure_delete/WAL truncation and bounded maintenance preserve all execution/fence/cleanup/quarantine records. Local real-reader checkpoint failure/recovery tests pass; deployed natural expiry and physical database/WAL absence pass, exact replay stays idempotent and changed source is rejected. A later readback after actual worker restart passed; the first immediate RPC was delivery-unknown and is preserved, not counted successful.

Coordinated worker/control/dispatcher pins and new product image4ec2fbe368ff48894f07076812d33398b5d92d683736ceb3084dd66b8bf88bcb. Normal semantic-epoch advance clears active versions; old approval is not rebound.16 fresh worker gates and7 HTTP/queue groups/3 cases pass;745 Linux+10 subtests,649 Windows/96 Linux skips,72 exact image files. Dependency versions unchanged. [Evidence](evidence/phase5-worker-retention-2026-11-06.json).

Credit$195.38, both admissions closed, existing PR unchanged, no model calls/new resources beyond the earlier pilot. Phase5 remains IN PROGRESS: final comparison and metadata/deletion-aware backup lifecycle remain. Human security/oracle review is still absent. Update/commit/push/remote verification preserves this progress without a continuation question.

## November6 KST — Phase5 model pilot and retention checkpoint

Completed12 real development jobs/15 Vultr calls on existing infrastructure. All three arms repaired3/3 cases; witness and verdict-only arms held the one ambiguous case, while execution-only B incorrectly accepted it. All cleanup confirmed. This is repair-core development evidence, not a held-out/full-product benchmark. D NOT RUN. Usage estimate$0.011443; held reservations$0.417795 remain unreleased. [Evidence](evidence/phase5-model-pilot-retention-2026-11-06.json).

Fixed/deployed expired-operator retirement and32-job original/repair union; actual11 retired asset directories absent with markers,0 expired workspaces,1 live. Added/deployed shared evaluation allocation using production's unchanged$5 cap and lock; full$1.20 pilot allowance recorded conservatively after run, with future driver reserving before launch. Prior per-job/global caps and closed product admission prevented concurrent spend. Shared development reserved$1.311412; no settlement/cap increase.

742 Linux tests+10 subtests including3 root-installer filesystem tests,649 Windows tests/93 Linux-only skips;11 new real SQL budget checks,7 expiry checks and existing retention/PR groups pass. Credit$195.38, closed admissions, unchanged guard deadline, private source/Demo, PR#1 unchanged, no new service. Phase5 remains IN PROGRESS: final held-out comparison, worker raw-log expiry and metadata/backup lifecycle remain. Separate critical review is not independent human approval. Commit/push/remote verification follows; no continuation question.

## November5 23:15 KST — Phase5 security/evaluation development checkpoint

Fixed/deployed slow-reader capacity exhaustion (30s ordinary/65s event deadline includes busy replies) and apt/libapt3.0.4. Exact image/source/UID/resource/private-network/SCRAM/role/HTTP readback passes. Initial stale predecessor pin refused upgrade without changing services; corrected exact pin and preserved predecessors. No worker/verifier/SQL/contract/approval changes.

16 fresh worker probes,6 verifier groups and4 protected challenges passed with cleanup.735 Linux tests plus10 subtests pass;649 Windows pass/86 Linux skips. Native scan retains46HIGH/72MEDIUM/62LOW/6UNKNOWN/zeroCRITICAL; Python dependencies have no known audit findings. [Separate critical review](phase5-security-review.md) is not independent human sign-off.

Added evaluation accounting and12 disclosed development cases. Real worker validation rejects12 faulty programs and matches12 positive controls (6 held). Earlier5 executions exposed an ineffective JPY units fixture; preserved and corrected to fractional USD. No model pilot/final comparison or held-out claims. Phase5 IN PROGRESS; comparison/lifecycle work remains. [Source-bound evidence](evidence/phase5-security-development-2026-11-05.json).

Private repo, no new service/PR/model calls; credit$195.50, closed admissions, active services/retention, unchanged guard deadline. Commit/push/remote SHA verification supplies this checkpoint; no continuation question.

## November5 22:30 KST — Phase4 acceptance passed

Finished the owner-requested recovery test without another PR. Recovery-only disposable SQL scenario plus actual existing PR reads: real GET reply loss, pending database restart, natural180-second lease expiry, generation5→6 takeover, stale-controller/write rejection, exact readback, completed restart/redelivery and cleanup all passed in189.67 seconds. Production receipt snapshot unchanged; zero GitHub writes/new PRs/provider calls/cloud resources. Original POST-create response loss remains NOT_REPRODUCED; synthetic seed and real observations are clearly separated. [Phase4 acceptance](evidence/phase4-acceptance-2026-11-05.json) closes Phase4's functional recovery obligations using the owner-constrained method, alongside prior live version/batch/signed-event/real-PR evidence. DONE requires this checkpoint's verified push.628 local passes/86 Linux skips;7 mutation-boundary cases/Ruff pass; private repos and$150/$25 promotional-only limits maintained.

## November5 22:16 KST — exact-approved private PR verified

Owner local approval succeeded. The fault harness failed before injection because it mutated frozen ProductStore; normal dispatcher restart then completed the same authorized branch/commit/draft PR once. Verified [private PR#1](https://github.com/arslanabdulghaffar/ProofFlow-Demo/pull/1) against exact base/head/source/tree/title/body/draft/repo, plus completed restart persistence and idempotent approval replay.3 confirmed writes; actor logged out. No new approval or duplicate PR needed. Fixed harness using wrappers and real immutable-type regression;621 tests pass/86 Linux skips,25 targeted checks/Ruff pass. [Evidence](evidence/phase4-real-pr-reconciled-2026-11-05.json). Actual response-loss/lease recovery remains NOT RUN, so Phase4 remains incomplete. Both repositories private; credit$195.60; no new resources/model/worker work.

## November5 14:20 KST — repair local approval preparation

Fixed explicit owner/DACL creation for DPAPI sessions after the owner's elevated terminal produced an Administrators-owned file. Added workspace-expiry preflight and safe stage diagnostics. Replaced the expired test workspace through ordinary synthetic intake/worker proof, retaining old records. Actual original match,3 fresh isolated checks/cleanup, zero model calls and deployed preview/session readback passed; test actor logged out and zero PR writes remain. Initial fresh-workspace helper wait bug cancelled its first original; retained cleanup evidence and corrected terminal-state polling before a new API job.620 tests pass/86 Linux skips; Ruff passes. [Evidence](evidence/phase4-local-approval-fix-2026-11-05.json). Phase4 remains incomplete; actual interactive approval/PR/recovery still NOT RUN. Source repo private; credit$196.46, no new services, admissions closed.

## November5 08:46 KST — remove chat timing from the approval handoff

A third exact preview was approved but processed after expiry; actual API/SQL/GitHub reconciliation confirms no approval/write/branch/PR. Services are active, no fault container remains, and credit is$197.10. Prepared a human-operated local preview/Notepad/full-digest confirmation command so the owner can submit within the same validity window without another chat round trip. Unique records/sessions preserve history; terminal/expiry/authority checks fail closed. No actual local approval has been performed. [Receipt](evidence/phase4-local-approval-ready-2026-11-05.json).

Prepared and locally tested the final real-response-loss driver: normal approved branch/commit/PR operations, discard only the final response before confirmation, then normal lease-expiry readback/restart/replay checks. Actual external path remains NOT RUN.617 tests pass/86 Linux-only skipped; no deployed source/SQL/policy change, new resource/inference/candidate run, PR or publication. Phase4 stays incomplete until actual operator action, readback/recovery and verified completion checkpoint.

## November5 03:24 KST — readback hardening and recovery coverage

Completed the non-PR Phase4 review: fixed final-commit tree/mode verification and malformed PR object handling. Matching-byte executable/symlink/submodule trees, truncated/wrong/duplicate/extra/missing entries and malformed shapes now fail. Added lost-response/DB-ack controller tests across all three write stages and real SQL commit/PR takeover/fencing checks.607 local passes/86 Linux skips, seven real SQL groups and four browser HTTP-double groups pass. [Evidence](evidence/phase4-readback-hardening-2026-11-05.json).

Deployed image886e5044e05ce84b78c2fc10ae19019d577338b66e7808475d0020a4fb452bab:72 exact modules, only adapter changed. Actual installed App/private base/tree reads, absent expired branches/PRs, trusted static rejection checks, active services and private TLS boundaries pass. No PR write/preview, candidate execution, inference call or new resource. Credit$197.63; admissions closed. Offline image build first lacked dependency RUN cache; normal trusted build reused the existing hash-pinned layer without dependency changes. Phase4 remains incomplete at actual approved PR/readback/live recovery. No new approval prompt or human sign-off.

## November5 03:04 KST — late exact answer, no external write

The exact fresh-preview approval was processed at03:02:23 KST, after01:48:41 expiry. Completion helper stopped. Actual read-only reconciliation found no recorded product approval, no durable write, no branch/PR and an unauthorized saved session; working App authentication remains valid. Credit$197.75; no new provider call/resource/worker execution. [Receipt](evidence/phase4-refresh-expired-2026-11-05.json). Added an explicit read-only refresh reconciliation mode and two tests proving it never POSTs approval. Thirteen scoped tests/Ruff pass. Owner reiterated no further approval questions while unavailable; none sent. Phase4 remains incomplete; no expiry change, replacement intent or write bypass.

## November5 KST — fresh exact PR preview and completion harness

On the owner's explicit request, generated one new real read-only preview of the existing active verified version. Actual API eligibility and unchanged candidate checks passed; encrypted actor save/ACL/decryption readback passed. No model call, worker job, new resource or external write. Credit$197.85; both admission controls stayed closed. Exact intent/digest/expiry and the complete review artifact were presented in one concrete approval request. Prior expired intent and evidence were preserved. [Receipt](evidence/phase4-pr-refresh-2026-11-05.json).

Prepared a trusted completion harness for exact approved API dispatch, independent GitHub source/PR readback, three confirmed durable writes, completed-state restart and duplicate-approval checks. It is NOT RUN against the external write path until concrete approval arrives. Eleven scoped tests pass, including changed digest/content, expiry, revocation, repeat-approval and private-session path rejection; no live PR success is claimed. Phase4 remains IN PROGRESS. Broad permission and owner absence do not waive the product's exact external-action control.

## November5 KST — approved key cleanup, expired PR preserved

Removed only the specifically approved unused App key5183052. Working key5183074 still authenticates against the private demo repository; Actions remain disabled and hooks absent. The owner's exact PR approval reached processing after its preview expired. No approval override or replacement intent was created. Actual reconciliation found zero durable external writes, no branch/PR and an unauthorized saved temporary session. The initial probe expected logout200 rather than204 and failed before saving its final receipt; the corrected readback records that limitation instead of claiming a retained expiry409 result. [Receipt](evidence/phase4-expired-approval-2026-11-05.json).

No new worker execution, provider call or cloud resource. Admission stayed closed and fresh credit was$197.85. Phase4 remains IN PROGRESS pending fresh exact approval and actual PR write/readback/recovery. No independent human sign-off. This is a private WIP checkpoint, not Phase4 completion or a request to continue.

## November5 KST — actual App connection and PR preview

Dedicated private App setup was explicitly approved, completed and verified. Scope is one private demo repository; fixed minimal permissions, Actions disabled, hooks absent, dispatcher-only secret. Actual scoped token authentication and deployed read-only base/diff preview passed. Three additional real isolated unchanged-source checks matched with cleanup, then exact synthetic version activation. Zero model calls/new resources; no external write authorized or sent. [Receipt](evidence/phase4-app-installed-2026-11-05.json). Exact draft-PR approval and removal of an unused first generated key are separately pending. Corrected Windows credential-helper ACL persistence and administrator ACL reading after actual failures, without relaxing access. Phase4 remains IN PROGRESS.

## November5 KST — dedicated GitHub repository ready

Owner login confirmed. Created private ProofFlow-Demo with README/main, disabled Actions, then verified exact private repo identity, no hooks, one-file tree and source repository privacy via real read-only administrator API. [Receipt](evidence/phase4-demo-setup-2026-11-05.json). Private App form is ready with minimal permissions and webhook off; registration/installation/key storage await the single browser persistent-access confirmation. No product PR, inference call, new cloud service or application change. Phase4 remains incomplete.

## Phase4 integration follow-up — November4, in progress

Deployed signed batch ingress and the optional GitHub App/outbox path with migrations013/014 and product image3c89abc975a89545c53e23e6e1512b2765a95cd470b42367f2b8b23eddb4253c. Exact external preview/approval binds actor, repository/base/path, version/configuration and fixed draft content. Durable per-stage authorization precedes writes; uncertain responses receive read-only reconciliation, never blind resend. Signed events bind exact bytes/event/time, freeze the accepted version, reject changed replay and support revocation/retention. Browser double-submit and stale response guards were strengthened.

Actual browser and signed ingress produced two fresh completed/matching isolated batches, with lost-reply same-job recovery, dispatcher restart, duplicate-event recovery, signature/body/revocation denials and desktop/mobile/logout readback. Version/connection revoked after checks; completed history retained. Zero new provider calls/resources; latest credit$198.17 and unchanged guard deadline.569 Windows tests pass/86 Linux skips;8 targeted Linux, real SQL5+6+4 new groups and11+5 regression groups,4 mocked-browser groups pass. [Source-bound evidence](evidence/phase4-integrations-2026-11-04.json) distinguishes live results, doubles and harness failures.

GitHub App account setup and actual separately approved draft PR/readback remain NOT RUN; the owner requested setup-screen help and GitHub sign-in is pending. Helpers are tested, no key installed. Phase4 is not DONE. This private WIP checkpoint preserves progress without requesting generic continuation. No independent human approval or public release.

## Phase4 versions/batches checkpoint — continuing

Exact-version approval and fresh-batch HTTP path now pass on the deployed worker. Clean fresh data completed; missing customer held with blocking evidence; invalid extra columns were rejected before execution; queued revocation cancelled work and preserved affected completed history. Real retirement erased the disposable version/batch/approval/journal state and preserved earlier records. Four SQL security groups cover actor/digest/CAS/idempotency, frozen assignment, revocation and global runtime rollback invalidation;11 prior queue groups and534 Windows tests pass. No provider calls or new cloud resources. [Source-bound evidence](evidence/phase4-versions-batches-2026-11-04.json).

Phase4 remains IN PROGRESS. Browser controls are implemented but not yet live-tested. GitHub App setup is pending, while client/outbox/signed ingress development continues. No external PR or human approval claim. Checkpointing is not a request to stop.

## Phase3 bounded repair — acceptance passed, November4

Completed the private bounded Vultr workflow with immutable proposals, three-call/five-minute/per-job money bounds, durable budget claims, exact worker/verifier bindings, fresh protected canaries, bounded retry/clarification/abstention, cancellation/reconciliation and raw retirement. Already-correct originals receive fresh checks with zero model calls. Passing produces reviewable export, never activation. Browser shows committed attempts/checks/events and model diagnosis as an unverified explanation; bounded ZIP contains hashed authorized evidence and isolated replay instructions, excludes protected rows and private reasoning.

Actual new development run: one final model call (9.185s,reported1,896 prompt/3,951 completion tokens) produced a candidate passing all three fresh checks. Earlier three model calls remain counted and failed evidence preserved. Four calls reserve$0.111412; estimates are not invoices. Exact-byte replay and zero-model original path pass; actual guest deletion preserves existing records.532 Windows,14 targeted Linux,5 PostgreSQL groups and4 final live acceptance groups pass;78 Linux-only skips on Windows. Source-bound [Phase3 acceptance](evidence/phase3-acceptance-2026-11-04.json) records image/migrations/calls/executions/budgets and failed probes. No new cloud resources; credit$198.50, admissions closed, private repo.

Mandatory phase commit/push/remote verification follows acceptance; final checkpoint report supplies SHA. Phase4 activation/batches/integration remain unimplemented. Final evaluation, full metadata/worker lifecycle, portable backups/publication and independent human review remain explicit later gaps. One-hour quote expiry fails closed; changed quote installation needs reviewed closed-idle refresh before later inference.

## Phase2 technical acceptance passed — Nov4,16:54 KST

The original schemas/backend/verifier phase gate now passes. [Phase2 acceptance](evidence/phase2-acceptance-2026-11-04.json) binds the current source/image, seven migrations, prior semantic/canary/API evidence and the final deployed checks. Commit/push and remote-SHA verification finish the mandatory checkpoint. This is a private synthetic original-run capability, not completed AI repair, version activation, fresh-batch processing, GitHub integration or public release.

Added non-secret, workspace-scoped browser request recovery with explicit retry after reload. Actual fault test lost an acknowledged POST response, reloaded the browser, retried the saved identity and observed the same worker job and wrong-owner finding; job count did not increase twice. Added real execution-journal retirement fault acceptance: stopped the timer for the scoped drill, revoked the disposable guest, interrupted its physical deletion after rename/partial unlink, verified no completed DB deletion, then resumed the normal production service and confirmed bytes/rows removed. Existing evidence counts were unchanged. No candidate code ran on the development or control host.

Validation:498 Windows passes/64 Linux skips,19 targeted Linux passes,3 JavaScript groups and4 final deployed acceptance groups; image58 file hashes/UID/modes matched, verifier rootfs read back unchanged,13 semantic sources unchanged, Ruff/generator/syntax checks passed. Current product image5c1840e90b0f8c291543fb6913411d44cebda452cf3a94398c3305c02d93abc8. Existing7 workspaces/36 assets/9 jobs preserved,0 uploads,2 completed tombstones. API/dispatcher/retention timer active; product and inference admission closed. Latest credit$198.81; no new resources/provider calls,1 new worker execution.

Scope audit corrected the earlier handoff's combined Phase2/release backlog using the unchanged original phase plan. Full metadata/worker-history/tombstone pruning and public hardening remain Phase5; consistent portable backup/retention-aware restore remains Phase6/T22. They remain required release gates and are not represented as implemented. Separate critical review covered persistence before POST, no automatic retry, credential exclusion, expiry/workspace validation, idempotent same-job recovery and incomplete-deletion truthfulness. No independent human review. Next: Phase3 bounded repair.

## Phase2 browser and raw-retention checkpoint — Nov4

Private browser intake is deployed on the existing control service. Exact preprovisioned session/CSRF import, bounded four-file uploads, exact contract approval, original execution, typed summary, real event stream, failure witnesses, refresh/cancel/logout and explicit workspace deletion are wired to real API/queue/storage. Browser-v1 Pydantic/JSON Schema/TypeScript contracts and uniform safe errors are versioned. No model call or candidate execution in the browser/control host.

Actual browser checks passed four groups: secure cookie login/form clearing; uploaded/approved wrong-owner program executed on the worker and failed V04 visibly; SSE replay plus refresh without extra enqueue; logout/foreign-workspace denial and physical deletion of a separate disposable guest. Two harness failures were retained: separate request client lacked the custom CA; later a visibility assertion targeted collapsed details. Corrected without TLS-wide bypass, changing expected outputs or duplicate worker execution. The continuation verified the same job and source hashes. Desktop/mobile screenshots were inspected privately.

Migration007 revokes before deletion, refuses active/uncleaned jobs, fixes the job manifest, then acknowledges actual byte cleanup before DB erasure. Nonroot byte worker uses descriptor-rooted deletion, rejects links/special files and preserves other workspaces; root timer cannot turn an unsafe result into success. Asset/journal leases and permanent tombstones block stale writes/restored access. Existing synthetic operator evidence remains. Seven-day metadata/tombstone/worker history pruning and backup lifecycle remain unfinished; the old backup helper now refuses guest/deletion state. Phase2 is IN PROGRESS, not complete or publicly released.

Validation:498 Windows passed/64 Linux-only skipped;19 Linux asset/retention tests;11 real disposable queue SQL groups and4 retention/session SQL groups;4 actual browser groups;57 image files hash/mode/UID-checked; Ruff, JS syntax, generated-type drift and whitespace checks. Current image87ff3f87bdb4e78d96578ca536993909f751ee5ce60606837701d9dee6e32c81. All7 migrations installed. Product/inference admission closed after probes; API/dispatcher/retention timer active. Counts7 workspaces/36 assets/9 jobs/0 pending uploads/1 completed deletion. Credit$198.92, existing deadline unchanged;1 worker execution,0 provider calls,0 new resources. [Source-bound evidence](evidence/phase2-browser-retention-2026-11-04.json). No independent human sign-off.

## Authenticated event replay after the private API checkpoint — Nov4

Pushed/verified `7398442424472d29cf72913b88557a6ffaa5bd94`, then continued without a permission pause. Additive migration005 exposes bounded authorized event reads; private SSE uses exact job-scoped cursor strings, committed monotonic events,15s comment heartbeat and finite connection lifetime. Two stream slots reserve room within the four-request API limit. Fresh authority is checked before the first disclosure and between frames; disconnect/revocation never creates a fake event ID. Terminal resume204 and invalid/foreign cursors400/404 are explicit.

Actual deployed6 groups passed:5 committed events replayed, exact resume, terminal/future-cursor behavior, cross-workspace denial, live logout closure, queued fixture cancellation without execution. Reused existing workspaces/assets; no worker/model calls. Current image `213ee066eeb1783fa83d6e984704993b7ee966ca59cbad297cdda6b4f3fd9a22`;53 modules match source. Upgrade required closed idle queue, preserved stopped prior containers and retained all data.11 actual PostgreSQL groups and482 Windows tests/55 Linux skips pass. An initial network-disabled image build correctly could not install pinned dependencies; normal trusted build reused the existing locked dependency layer. Candidate isolation did not change.

Phase2 remains IN PROGRESS for browser intake, remaining wire/generated-type/error contracts and lifecycle/retention. Admission closed after probes; private services restarted. Historical original/recovery/restore results retain their exact tested image/source binding. [Event receipt](evidence/phase2-events-2026-11-04.json). No human security sign-off or public release.

## Private original API/queue and failure evidence — Nov4

Continued from verified private main `ae1bc6f8444e0c43ddf0b758337648525ff1c3c5`. Product migrations001–004 and separate functions-only SCRAM roles are deployed. The private networkless API supports immutable uploads/downloads, exact contract approval/revocation, idempotent original jobs, status/cancel/logout and a stored failure page. A separate restricted dispatcher runs only the fixed worker and bounded verifier; no provider credentials or new cloud service. Pre-write reservations and bounded staging recovery prevent crash leftovers from bypassing quotas. API concurrency covers the entire response.

The updated verifier passed6 deployed boundary groups and4 fresh protected worker canaries. Real HTTP/queue checks passed7 groups, including deliberately wrong ownership with expected/actual-owner witnesses, Q08 excluded missing attributes held2, and invalid input rejected without an execution intent. Cancellation and dispatcher SIGKILL passed on actual worker jobs: same execution ID, cleanup receipt before terminal state, recovered lease generation after controller loss. No direct job-state edits, fabricated events, model calls or manual repair.

Separate critical review corrected socket-directory umask traversal, bounded temporary-file recovery, response concurrency, strict source/output/receipt binding, old-runtime retention during reconciliation and durable termination receipts. An invalid date-range test fixture was rejected and corrected; policy stayed frozen. Native/runtime advisory and independent-human-review gaps remain. Local478 tests pass/55 Linux-only skips;10 actual PostgreSQL groups,10 Linux asset groups,6 verifier boundary groups and4 peer/frame groups passed;53 product image modules match source hashes. Later restore evidence and current sanitized receipt are recorded with this checkpoint.

Phase2 remains IN PROGRESS: remaining wire/generated types, authenticated event resume/browser intake, retention/lifecycle and complete acceptance. Matching originals/canaries do not approve activation; correct quarantines stay held. No public product, autonomous repair or full backup claim. Continue authorized Phase2 work after this checkpoint without asking to continue.

Final integrity checks: both actual SCRAM roles accepted their protected credentials and denied wrong passwords/table reads/owner escalation/schema writes. Database restart and decrypt/restore of an off-VM DPAPI dump preserved all8 product table rowsets; budget tables stayed identical.7 synthetic workspaces,32 assets,7 jobs/38 events retained,0 pending uploads. Product job admission is closed after probes, inference admission remains closed, private liveness serves normally. Remaining credit observed$199.13; cutoff/review deadline unchanged. Backup covers database only and requires the Windows profile, not asset/journal or portable disaster recovery. [Source-bound receipt](evidence/phase2-private-integration-2026-11-04.json).

## Bounded verifier and protected canaries — Nov4

The trusted verifier is deployed on the existing control VM in a pinned read-only SquashFS: separate UID10002, no credentials/candidate code/network sockets, 512MiB/no swap,1CPU/32 tasks,10s systemd watchdog and15MiB output ceiling. Single-slot root-only admission, request/report/image hashes and confirmed cgroup cleanup precede receipt return. The watchdog survives controller exit; the next invocation reconciles the prior slot. Prepare/canary/verify are fixed byte operations, not arbitrary code dispatch.

Actual local and deployed checks each passed6 groups: fixed protocol rejection; UID/capability/read-only/secret and IPv4/IPv6/Unix socket denial; independent timeout; OOM; output ceiling; task ceiling/descendant cleanup. Four fresh worker executions passed: correct ownership/duplicates/refunds matched with0 blocking occurrences; correct quarantine matched with4; Q08+attributes/date/rollups matched with5; wrong ownership was rejected. Quarantine matches remain held. No inference/new resource.463 Windows tests pass/53 Linux-only skips;14 new protocol cases. [Source-bound evidence](evidence/phase2-bounded-verifier-2026-11-04.json).

Critical review corrected Docker directory exceptions that included bytecode/host modules, explicit image modes/traversable directories, missing Linux service identity and journal capacity (64 retained intents including failures). Final image inventory and boundary checks passed; intermediate builds were not deployed. No independent human sign-off. API/queue/retention/original failure UI and Phase2 acceptance remain unfinished. Continue integration after this WIP checkpoint.

## Q08 resolved; frozen semantics and actual worker rejection evidence — Nov4,10:37 KST

The owner explicitly approved holding a batch for a missing required customer field even when its transaction is excluded by the date range. Recorded D59, resolved current Q08 instructions/risk/handoff, and froze synthetic v1.1 schema/example before semantic implementation. Required attributes precede all date/currency filters; every invalid exact duplicate remains blocking. This is business-policy approval, not human security review or automatic version activation.

Implemented strict immutable policy parsing, independent complete-source derivation and bounded output comparison for V01–V09 and the V10 attribute/rollup extension.58 new tests cover Q08 date/currency/both exclusions, exact duplicates/earliest representative, conflicting raw spellings, all applicable violations, lookup ambiguity, same-total wrong ownership, integer precision/refunds/zero, half-open filter endpoints, raw attribute values and every rollup field. Current Windows suite449 passed/53 Linux-only skips; Ruff/docs checks pass. Existing Linux/PostgreSQL sources are unchanged.

Three labeled fixture programs ran on the real worker, then again after exact receipt-type hardening (six actual executions, no inference): wrong owner fails V04 while sums match; hiding missing segment behind FILTERED_BY_CONTRACT fails V08; correct MISSING_ATTRIBUTE output matches but leaves2 blocking occurrences. All six exit0/cleanup confirmed. Source/capture/contract/runtime/manifest hashes and final run IDs are [in the evidence](evidence/phase2-semantics-2026-11-04.json); full receipts remain private. Candidate code never ran locally; the independent comparison was a trusted local component. The deployed bounded verifier, protected canary workflow, product API/queue/failure view and full Phase2 acceptance remain unfinished. No new cloud resources, dependencies or provider calls. Continue those engineering tasks without reopening Q08.

## Phase2 identity/registry checkpoint — Nov4,08:20 KST

Continued after verified private checkpoint `9f5f08d897f8745a7051bd98fa63c462991ee923`, without waiting for continuation. Added opaque session/CSRF helpers and a separate product PostgreSQL migration with private nonlogin owner/API/provisioner roles, immutable workspace-scoped input registry, exact retry conflicts, expiry/revocation and fixed capacity/byte quotas. Public HTTP routes and the product DB client/deployment are still unfinished; no guest signup or permission to activate a version exists.

Actual disposable PostgreSQL18.6 checks passed10 groups: migration/topology/durability, scoped registry/CSRF/idempotency, table/owner/provisioner/public/transaction-policy denials, input bounds, concurrent64-object and128MiB quota, expiry/logout, both workspace-revocation race orders, workspace/session capacity, dump/restore and confirmed fixture cleanup. The separate critical pass moved database PUBLIC CONNECT/TEMP and public-schema CREATE revocation from test setup into the actual migration, then reran the checks. This helper uses local test-only trust authentication; production SCRAM and browser integration are NOT RUN. [Source-bound component evidence](evidence/phase2-components-2026-11-04.json).

Current suite:391 Windows tests pass/53 Linux-only skips;8 new Linux storage groups passed and the prior45 unchanged Linux cases retain their previous evidence. Ruff passes. No new dependency, provider request, cloud resource or account action. Q08 remains pending, and full schema/verifier/queue/live failure-view acceptance is unfinished. No independent human sign-off. Continue from this WIP checkpoint with the product adapter/authenticated routes and durable queue; quota admission must precede blob staging so rejected registrations cannot accumulate unbounded orphan files.

## Phase2 source and evidence components — Nov4,08:09 KST

Phase1 is DONE at verified private main `0a24f45467b64132b0a3ca95a503aa8f4799ebff`. Continued directly into authorized Phase2. Added strict bounded JSON/CSV/scalar parsing and canonical vectors; every original occurrence remains present and exact. Candidate-output structural decoding grants no status. V02–V04 compare source partition, original identity and composite customer ownership; total-preserving ownership swaps are rejected. Full V01–V10/verifier schema freeze remains pending Q08 and remaining semantics/integration.

Added an internal Linux immutable byte store with descriptor-pinned reads, private ownership, hash checks, serialized atomic/fsynced publication and no public route.8 Linux fixture groups prove unsafe links/types/corruption rejection, concurrent reuse, short-write completion and failed-sync behavior. Quotas, workspace registry authorization and retention are not provided by this primitive. No candidate executed locally; no new provider request, dependency or cloud resource.

Checks:369 Windows tests passed/53 Linux skips;8 new Linux storage groups passed separately (the prior45 Linux cases are unchanged). Ruff and documentation checks pass. Distinct critical pass found and fixed native Unicode exception leakage from malformed attribute declarations; regression cases now return fixed diagnostics. No independent human approval. Latest credit guard observed$199.67 remaining atNov3 23:07UTC; cutoff/review deadlines unchanged. This is a WIP checkpoint, not Phase2 completion; continue independent product auth/storage/queue preparation while the already-sent Q08 question remains pending.

## Phase 1 technical acceptance passed — Nov 4, 07:50 KST

The actual private Vultr foundation now passes the Phase 1 gates. [Acceptance evidence](evidence/phase1-acceptance-2026-11-04.json) contains23 reviewed records, the retained failures and checkpoint source hashes. The phase checkpoint is complete only after ordinary push and remote SHA verification; the checkpoint report supplies that commit. Earlier sections below are historical, not current blockers.

- Two fixed Seoul VMs, private mTLS worker, immutable gVisor/SquashFS and isolated pandas execution. Network denial, resource/storage/inode limits, safe collection, wall timeout and cleanup have actual deployed evidence. Supervisor death and controller disconnect each terminated writers and recovered cleanly. Default fork capacity remains limited:128 host tasks can be exhausted before64 guest processes. Kernel denial and cleanup are proven; the63-child capacity fixture remains failed (D54).
- Actual PostgreSQL18.6 uses SCRAM, a private Unix socket, functions-only dispatcher and bounded8GiB ext4 disk. Wrong/missing credentials and privilege escalation were denied. Restart/dump/restore preserved1 account,10 reservations and8 real provider receipts. An encrypted off-VM DPAPI backup also restored to a separate disposable database with identical table hashes. Portable restic/object-storage recovery is later work.
- Eight real Vultr calls: both models passed JSON and ambiguity probes; two2048-token coding responses were correctly rejected as truncated. New request IDs with the existing8192-token ceiling returned complete code. Both programs executed only on the worker and matched independently derived signed integer totals, including9007199254740993. This is a synthetic infrastructure probe, not measured repair-agent quality or the business verifier. Durable replay after database restore read the same response without another request.
- Operator HTTPS over pinned SSH passes TLS1.3 and liveness200; untrusted CA rejected. Readiness remains503 and unimplemented routes404 because the product admission path does not exist yet. No anonymous/public product release.
- A real reboot exposed SSH socket/service configuration drift. Access was recovered over the private network using the same pinned host key, without transferring an operator key. Persistent key-only SSH config now survives new reboots:control34.44s,worker37.02s. Post-reboot database authentication, worker identity/benign task and HTTPS passed. The initial failed reboot remains recorded.

Latest account observation:$199.77 credit remains. Eight requests reserve$0.279349; provider metering matches617 input tokens per model and6716/4770 output tokens. Catalogue-rate estimate$0.00782425 is not an invoice. All reservations remain held. $150 total/$25 inference/$2 probe limits and the $120 early account cutoff remain. The guard now revokes the exact recorded inference subscription as well as removing exact project VMs when triggered. Funded review remains Nov7 06:05KST; absolute teardown Nov23UTC. No card/deposit/personal payment and no hard provider non-overage guarantee.

Checks:229 Windows tests passed,45 Linux-only skipped there (all45 previously passed on unchanged core sources),11 prior trusted systemd groups, repository Ruff and preparation/link checks passed. Five new guard fault tests pass, including account-endpoint failure and subscription failure without leaving known VMs running. Hosted CI NOT RUN: no hosted runner billing authorization. No independent human sign-off. Continue through the verified checkpoint into authorized Phase2; Q08 remains the only current contract-freeze decision requested from the owner.

## Actual worker deployment checkpoint — Nov 4, 07:09 KST

Both VMs now have pinned SSH on port443. The worker runs the actual pinned runsc/systrap and immutable SquashFS image over private mTLS. Trusted pandas output is independently captured/hash-checked. Actual passes: UID10001/no capabilities/no-new-privileges, read-only root/input, host-marker isolation, CPU throttling, 768MiB OOM kill, 64-task thread ceiling, shared scratch/tmp/shm byte quota, output byte quota, inode exhaustion, bounded logs, unsafe/oversized output rejection, 20s timeout/descendant cleanup, and benign recovery. Network denial covers IPv4/IPv6/DNS/UDP/raw sockets/metadata/private services/controlled external SSH with positive host controls; temporary public test access was removed.

Real probes found and fixed: input permissions lost to restrictive umask; valid dotted Ubuntu cgroup counter rejected; failed captures losing all diagnostics; gVisor automatic tmpfs hiding the scratch quota through a /tmp symlink; and transient kernel writer teardown after systemd reported stopped. Limits remain unchanged. The new image keeps /tmp a real directory and explicitly binds all scratch aliases to one bounded host mount. Failure receipts remain preserved. [Source-bound deployment evidence](evidence/phase1-deployed-2026-11-04.json) includes failures and subsequent results.

Open: default fork flood exhausts 128 host tasks before all63 children can coexist (latest diagnostic45); it fails closed and cleans up. The separate fixture voluntarily lowered its own guest limit to32 and observed31 children/EAGAIN/no hard-limit raise, proving guest fork accounting without changing deployment policy. The original capacity test is still failed, not relabeled passed. Complete its critical disposition, deployed supervisor-death/controller-disconnect recovery, control/database/disk/restore/HTTPS and real bounded Vultr inference before Phase1 acceptance. No provider subscription/call yet; no Phase2 work or independent human approval.

Validation: 224 Windows tests passed/45 Linux-only skips; all45 Linux tests passed separately;11 trusted local systemd groups passed after termination changes; Ruff passed. New worker image scan: no CRITICAL or Python findings,45 HIGH/72 MEDIUM/61 LOW/7 UNKNOWN retained. Earlier evidence belongs to its named historical source/image. This is a WIP checkpoint; continue authorized work immediately.

## Phase 1 real deployment started — Nov 4, 06:30 KST

Continued from verified private main `c808c94d75fc1d7100565929580f19cef19aa341`. The owner explicitly authorized credit use now while awaiting their support ticket, supplied management API access, and authorized Phase 2 continuation after genuine Phase 1 acceptance/checkpoint/report while away. This supersedes older billing-wait and stop-for-review descriptions below; it does not authorize personal spending, publication, invented business rules or bypassed infrastructure gates.

Authenticated API confirmed the redeemed $200 credit and fresh $24/$48 monthly plans. Created exactly two project VMs in Seoul, one private VPC, dedicated SSH key and separate restricted firewalls. Backups and paid DDoS add-ons disabled. A $145 project allocation reserves $72 compute, $25 inference, $18 later storage, $10 incidentals and $20 contingency. Latest console and API guard observation: $0.12 pending/charged, $199.88 remaining. No inference subscription/call, card, deposit or message from Codex.

Management key uses Windows user-bound DPAPI outside Git, with checked owner-only ACLs; project SSH identities and resource IDs are also outside Git. Cloud-init contains no management/provider key. Host keys are pre-pinned; failed SSH does not permit disabling identity verification. Both VMs booted, but SSH access is under diagnosis. Empty project VMs were rebuilt in place for restricted alternate-port/IPv4 diagnostics; no application data existed to discard and no additional VM was created. This is not deployed acceptance.

Added a scheduled administrator credit guard every 15 minutes, with a $120 early cutoff (preserving $30 below the authorized maximum), a 72-hour funded review deadline and absolute November 23 teardown deadline. Exact recorded VM IDs/labels/plans/region/tags must match before deletion; the stop latch is durable before action; uncertain deletes reconcile by GET. Scheduled task actually ran successfully and observed $199.88 remaining. It depends on this Windows account/computer/network and provider accounting availability; it is not a provider hard stop. Deployed inference still needs its separate durable $2 probe/$25 inference ledger.

Eight new offline guard fault cases passed; full Windows suite 214 passed/43 Linux-only skipped, Ruff passed. These checks do not prove cloud containment. Remaining work: restore restricted SSH, install actual immutable worker/control/database, prove all deployed isolation/resource/capture/watchdog/cleanup gates and real bounded Vultr inference. No Phase 1 completion or independent human sign-off.

## Phase 1 database/provider hardening — 2026-11-04 KST

Started from clean private main/remote `f342ad91fdec62404b189fa3ec1612a9af627804`. Added fixed same-host SCRAM database access, least-privilege runtime roles, reviewed PostgreSQL settings and bounded owner-only host secret loading. Patched the active PostgreSQL fixture using supported Alpine package fixes and removed unused gosu/setid permissions; final image scan has zero known findings. Preserved prior vulnerable-image receipts and unresolved findings in other images. Setup, source attribution and a separate Codex critical review are in [inference](inference.md) and [readiness](phase1-readiness.md); exact observations in the [receipt](evidence/phase1-database-provider-2026-11-04.json).

Observed: 170 Windows tests passed; 37 Linux-only skipped there and all 37 passed separately. Fourteen real database ledger groups and nine SCRAM/driver/mock-HTTP groups passed, including wrong/missing credentials, admin impersonation, trust downgrade, environment injection, least privilege, concurrent claims, crash persistence and provider-failure replay denial. Owned fixture containers, volume and secret files removed. Repository-wide Ruff passed after also cleaning up seven existing findings in the preparation checker: resolved Git executable, bounded fixed-command invocation and formatting. The fixed-command subprocess annotation documents trusted literal inputs; no vulnerability-scan suppression was added. Preparation/link checks passed. Helper image retains known Debian advisories; no independent human sign-off.

Phase 1 remains IN PROGRESS / NOT ACCEPTED. No cloud charge, live inference, real secret setup, candidate execution, external message or visibility change. Deployed database/restore, real provider receipt/model/price/entitlement, runsc/resource/network/cleanup and credit-only billing gates remain. This is a meaningful private WIP checkpoint, not the Phase 1 review boundary.

Checkpoint review: 25 intended source/configuration/test/document/evidence files reviewed. Current and historical source hashes matched staged bytes or their named verified commits; the old worker image receipt now explicitly binds its original checkpoint. Documentation/link checks, repository-wide Ruff and whitespace checks passed; staged Gitleaks found zero leaks. Authenticated GitHub metadata confirmed private=true/default main. No credentials, local environments, images, database volumes or raw test outputs staged. Normal commit/push and remote SHA readback identify this WIP checkpoint.

## Phase 1 authenticated worker service and image import — 2026-11-04 KST

Continued from clean private main and matching remote `10960d997f78d18a335911902460f2fdce95ab9f`. Implemented private TLS 1.3 RPC with CA and exact peer pins, bounded messages/connections, runtime expectation binding, scoped lifecycle operations, independently hashed capture, durable controller persistence and lost-ACK reconciliation. Added fixed designated-host entrypoint/systemd composition and trusted Docker-create/export-to-SquashFS import without image start, pull or host archive extraction. Full setup/security review is in [sandbox](sandbox.md); [receipt](evidence/phase1-worker-service-2026-11-04.json) binds code, tools and actual tests.

Observed: 159 Windows tests passed; 32 Linux-only skipped there and all 32 passed separately. Nine real local TLS/service groups, nine supervisor lifecycle groups and three image/mount groups passed. These cover certificate rejection, connection bounds, malformed framing/JSON, wrong runtime, scope/replay/transfer/ACK loss/tamper, disconnect/cancel/shutdown, independent watchdog, cleanup and image pin/immutability. Owned test certificates, sockets, processes, mounts and loop devices removed; private final build artifact retained outside Git. Rootfs blob `bb9a2f31b699fa961b897686e0187f021251029b2b1445ebb42f061afe645cb9` derives from the existing approved image; the image was not started. Ruff passed. No new Python dependency; existing host tool usage documented. Critical review fixes include runtime binding, ACK recovery, unsafe TLS configuration rejection, shutdown admission and explicit local/no-pull Docker policy. No independent human sign-off.

Phase 1 is still IN PROGRESS, not accepted. Deployed service installation/restart/cross-VM TLS, runsc/pandas, guest resource/network limits, deployed cleanup, database/provider composition and real Vultr calls remain NOT RUN. Existing image/host security findings are not waived. No cloud charge, payment action, real key setup, public release or external message. Credit-only/private limits remain; no continuation question needed.

Checkpoint review: 33 intended source/test/configuration/document/evidence files reviewed, including explicit LF policy for the systemd unit. All 96 current/historical evidence hashes match staged bytes or their named verified checkpoint. Documentation/traceability, lint and whitespace checks passed; staged Gitleaks found zero leaks. Exact GitHub repository privacy was authenticated again. No private keys, raw fixture output, rootfs blobs, local environments/tools or unrelated work staged. Normal commit/push and remote SHA readback identify this WIP checkpoint.

## Phase 1 worker supervisor follow-up — 2026-11-04 KST

Continued from clean, remotely verified main `884bc82b18fec1bc820ea564827dcb6b3f0fc346`. Implemented the internal worker supervisor, private durable journal, fixed OCI/runsc launch, independent systemd watchdog, bounded capture, exact owned cleanup and crash recovery. Separate critical review fixed late launch after cleanup, concurrent retention reservations, full-capacity replay and cancellation at receipt commit. Runtime source/image identity is bound to replay; cleanup uncertainty quarantines new admission. No dependency or existing image changed.

Observed: 124 Windows tests passed, 32 Linux-only skipped there; all 32 Linux collector/journal tests passed in WSL. Nine explicit real systemd integration groups passed using trusted fixed local writers/sleepers: capture/replay/acknowledgement, watchdog-policy mismatch denial, delayed-start denial, bounded simultaneous logs, extra-file rejection, resident expiry/maintenance-failure recovery, cancellation with detached child, cleanup quarantine/recovery, and independent 20s watchdog after supervisor SIGKILL followed by restart cleanup. Owned units/processes/mounts/staging absent afterward. Ruff passed. Exact sources/environment/results: [supervisor receipt](evidence/phase1-supervisor-2026-11-04.json); design and critical review: [sandbox](sandbox.md). These fixtures are not candidates, runsc, pandas, live provider calls or deployed containment proof. No independent human sign-off.

Phase 1 remains IN PROGRESS / NOT ACCEPTED. Authenticated worker service/transfer, immutable rootfs import/provenance and deployed service restart composition still need work; actual deployed runtime/resource/network/cleanup and Vultr inference gates remain NOT RUN. Credit-only tax/non-overage blocker is unchanged; no paid action, payment setup, message or visibility change. This WIP checkpoint preserves progress and does not request permission to continue. Actual Phase 1 acceptance still stops before Phase 2.

Checkpoint review: 21 intended source/test/document/evidence files reviewed; all 60 source hashes in the current foundation/supervisor receipts match staged bytes. Documentation/traceability, Ruff and whitespace checks passed; staged Gitleaks found zero leaks. Exact GitHub repository rechecked private=true/default main. No raw fixture output, credentials, local tools/environment or unrelated files staged. Required normal commit/push and remote SHA readback identify this WIP checkpoint.

## Phase 1 worker image follow-up — 2026-11-04 KST

Continued directly after pushing and verifying inference checkpoint `2442eebc522e5d9153851989242aaac57acdb7c0`. Built/scanned the pinned worker image with a separate pandas/NumPy lock and fixed nonroot bootstrap. Fourteen pure/mock policy cases added; 114 Windows tests passed, 24 unchanged Linux cases skipped (prior pass retained), Ruff passed. No worker image launch, pandas import, candidate execution, real rlimit mutation or cloud charge. Scan retains Debian 45 HIGH/72 MEDIUM/61 LOW/7 UNKNOWN and Python zero, no CRITICAL; this is not worker release clearance. [Sandbox](sandbox.md) and [receipt](evidence/phase1-worker-image-2026-11-04.json) record limits and critical review.

Phase 1 remains IN PROGRESS: deployed runtime identity, independent resource/network probes, supervisor watchdog/writer termination/cleanup and real Vultr calls remain unproven. Private repo and credit-only scope preserved; no repeated sufficiency question. This is a second implementation checkpoint in the same work period, not a Phase 1 completion. Reviewed 20 intended staged files; 36 foundation and 7 worker hashes match staged bytes, and 16 retained inference hashes match its verified checkpoint. Documentation/traceability, whitespace and staged secret checks passed (zero leaks). No candidate/private data, environments or raw build/scan artifacts staged.

## Phase 1 inference client follow-up — 2026-11-04 KST

Continued from verified private main `df7717f948ba195b84f1c42c40ed859a402a4731`. Added a real Psycopg budget driver and fixed-endpoint bounded Vultr HTTPX client, strict provider JSON parser, optional locked dependencies and a reproducible trusted integration image. 100 Windows tests passed, 24 unchanged Linux cases skipped with prior Linux result retained; Ruff passed. PostgreSQL 14 groups plus five real-driver/mock-HTTP checks passed; all owned test resources removed. Python audit: 51 distributions, zero known findings. New helper image has no Python/CRITICAL findings; existing Debian advisories remain and PostgreSQL test-image critical findings are not waived. Separate critical review and exact sources in readiness and budget receipt.

No cloud service, paid provider request, candidate execution or public release. Phase 1 remains incomplete. Owner instructed continuous development without repeated sufficiency questions; ordinary work is not waiting on support-message permission. This is a WIP checkpoint, followed by worker-image implementation, not a phase boundary. Reviewed all 23 intended staged files, 30 foundation/16 budget source hashes, documentation/traceability and whitespace. Staged Gitleaks found zero secrets; exact GitHub repository privacy reverified. Commit/push/remote readback identify the checkpoint.

## Phase 1 local budget and organizer-guidance follow-up — 2026-11-04 KST

Started from clean local/remote `59d64f3847aeaef2cd6f2354dec87372cdee1e48`. Implemented infrastructure-only PostgreSQL reservations/one-shot claims/reconciliation and offline fixed-endpoint Vultr JSON planning. No new Python dependency, HTTP provider client, candidate execution or cloud service. Separate critical review fixed role-test privilege assumptions, definer ownership, quote deadlines, stale transaction-snapshot risk and nondurable commit settings. Owner-relayed organizer guidance accepted for service coverage, Docker minimum and judging duration; private-repository, credit-only and Phase 2 boundaries persist.

Observed: 48 Windows tests passed (24 Linux-only skipped; unchanged prior 24 WSL passes retained), Ruff passed; 14 real local PostgreSQL groups passed including 20 competing reservations, 12 competing claims, crash/restart and role/expiry/rollback failures. Own test container and volume absent after cleanup. Eighteen planner cases are synthetic and offline. PostgreSQL image scan retains two CRITICAL findings and other findings; local fixture is not deployment-approved. [Readiness](phase1-readiness.md), [inference](inference.md) and [budget receipt](evidence/phase1-budget-postgres-2026-11-04.json) record limitations and review. No independent human approval.

**Phase 1 IN PROGRESS / deployed gates BLOCKED**, not DONE. Service coverage now has owner-relayed organizer evidence; tax/non-overage terms and final billing enforcement remain unresolved. A precise support-message permission request is pending, no external message sent. No personal spending, cloud provisioning, paid inference or visibility change. WIP checkpointing does not itself require stopping authorized work; stop before Phase 2 only after actual Phase 1 acceptance and owner review.

Checkpoint review: intended source, SQL, tests, attribution, durable docs and evidence reviewed; no local database volume, raw scanner output, environment or account secret belongs in Git. Documentation/traceability and Ruff checks passed; GitHub API reverified private=true on the exact repository, branch main and prior remote checkpoint unchanged. All 21 intended staged files reviewed; 21 foundation and 4 budget source hashes matched staged bytes, whitespace passed and staged Gitleaks found zero secrets. Normal commit/push and remote SHA readback identify this WIP checkpoint; it does not complete Phase 1.

## Phase 1 local collection follow-up — 2026-11-04 KST

Started clean at verified local/remote `7d5153f1e2b60a17164054541b59bad8d1e489e4`. Added trusted Linux collector (fixed output names, O_PATH inode pinning before data I/O, aggregate byte/line limits, exact hashes, mutation detection and descriptor cleanup) plus a shared 100 KiB raw stdout/stderr buffer with truncation flags. No execution endpoint, subprocess dispatcher, candidate execution or cloud service. 30 Windows tests passed; 24 Linux collector cases skipped on Windows and separately passed in WSL. Ruff and unchanged control-image health/hardening/cleanup passed. Six MEDIUM advisories reviewed with Debian sources; package fixes and remaining review stay open, no suppressions. Details and separate critical review: [sandbox](sandbox.md), [readiness](phase1-readiness.md), [source receipt](evidence/phase1-foundation-2026-11-04.json).

Phase 1 remains **IN PROGRESS / deployed gates BLOCKED**. Quiescence, gVisor isolation/resource limits, deployed capture/watchdog/cleanup, real inference and durable spend enforcement remain NOT RUN. No charges incurred; credit-only limits/private repository preserved. No independent human review. This is a WIP checkpoint, not phase acceptance.

Checkpoint review: all 20 intended source/test/document/evidence files reviewed; no unrelated files or runtime artifacts staged. Source hashes, documentation/traceability, whitespace, lint and staged Gitleaks checks passed (zero secrets). GitHub exact repository privacy reverified. Commit/push/remote SHA readback identify this WIP checkpoint; it does not complete Phase 1.

## Phase 1 security follow-up — 2026-11-04 KST

Continued from clean main with remote SHA `1798c30accf9f4d333bfb21595e62dd73aac4a5c`. Removed unnecessary setuid/setgid permissions from 11 trusted image utilities. Expanded the image checker to inspect actual service privileges, `/usr` inventory/aliases, fstab and advisory-specific components. Old image rejected; cleanup verified. Rebuilt image passed health/hardening/cleanup. 22 tests and Ruff passed. Rescan retains 45 HIGH/72 MEDIUM/61 LOW/7 UNKNOWN and no CRITICAL, Python zero: permission hardening is not a CVE patch. All nine HIGH advisories have official Debian-source triage; remaining unique findings are retained, individual lower-severity/deployed review open. No independent human sign-off.

Official billing FAQ confirms tax excluded from advertised rates; account limits are allocation controls and stopped VMs continue billing until destroyed. No account-specific inference/tax coverage or non-overage guarantee found. No cloud services, subscription, paid request, payment setup or external message. **Phase 1 still IN PROGRESS / deployed gates BLOCKED**, not DONE. Detailed sources, separate critical review and receipts: [readiness](phase1-readiness.md). This is another private WIP checkpoint; normal commit/push/remote verification required. Stop after eventual successful Phase 1 acceptance for owner review.

Checkpoint review passed: all 11 intended source/document/evidence files reviewed; source hashes match, documentation/traceability and whitespace checks passed, staged Gitleaks found zero secrets. Authenticated GitHub metadata rechecked exact repository private=true, default main. No local caches, environments, raw browser/account state or unrelated files staged. Commit/push and SHA readback identify this WIP checkpoint; it is not Phase 1 acceptance.

## Phase 1 kickoff WIP — 2026-11-04 KST

Started from clean main and matching remote `79ccf59ec61b7885ce3ba63d82d3e87d5bfc7233`; existing work preserved. Official timing gate PASSED: dashboard Live / Submissions open. Account activation PASSED after owner used the distinct Gift Code tab: authenticated Dashboard/ledger $200 Remaining Credit, expiry 2026-12-04, charges $0.00. Billing coverage/hard non-overage bounds remain BLOCKED. Owner asks autonomous official-source decisions while they sleep; no repeated question or assumed personal-spending exception. No cloud services created.

Implemented trusted local API health surface, exact Python lock, hashed runtime export, pinned non-root control image and bounded trusted image smoke checker. Eight tests, Ruff, clean runtime-only install, actual loopback HTTP, local image build/smoke/cleanup passed. pip-audit found no known vulnerabilities in 48 installed Python packages. Trivy identified outdated pip in the first image; upgraded build installer and removed runtime pip, then rebuilt/retested. Final image Python scan zero findings; Debian has 45 HIGH/72 MEDIUM/61 LOW/7 UNKNOWN package-advisory findings (no CRITICAL), retained for triage in the scan receipt. Full evidence, dependency review and separate critical pass: [Phase 1 readiness](phase1-readiness.md). No independent human sign-off; no claim of deployed acceptance. Updated rules/judging plan and traceability to distinguish partial foundation from full requirements.

Checkpoint review: preparation/link/trace checks and staged whitespace passed; Gitleaks 8.30.1 staged scan found zero secrets. Reviewed the explicit staged inventory (source, trusted tests, locked dependencies, pinned image files and redacted/public evidence only). No credential, local cache/environment, account identifier or raw browser state staged. GitHub API rechecked private=true on the exact repository.

Phase 1 **IN PROGRESS / NOT ACCEPTED**. Real Vultr inference, deployed isolated pandas, guest/resource/network/output/timeout/cleanup gates remain NOT RUN. Preserve this as a private WIP checkpoint; normal push and remote SHA readback are required. Identify its full SHA with `git log -1` plus `git ls-remote origin refs/heads/main`; no self-referential SHA embedded. Stop after eventual successful Phase 1 checkpoint for owner review before Phase 2.

## Historical Phase 0 evidence

As of 2026-10-24 KST: **Ready for kickoff. Phase 0 DONE; Phase 1 not started.** Owner confirms the start request was premature; core stays gated until official opening. Account/charges evidence also remains incomplete. No cloud resource, billable service, inference request or candidate execution occurred in this session.

Completed preparation: 59-page review including appendices/S01–S42; source version/hash and selected visual table/diagram review; exact private repository authenticated read and advertised write confirmation; isolated local Node LTS/uv readiness; durable product/contract/architecture/security/API/sandbox/inference/budget/UX/test/release plans; 276 trace entries across 59 pages; one-human work-package ordering and owner question register.

Owner decisions recorded: sole confirmed contributor; Codex may continue ordinary development/checkpoints without repeated permission; synthetic duplicate/downstream rules approved; no real-customer policy approval; independent human reviewer and hours unknown; development may proceed with automated/separate critical review and disclosed gap; MIT ownership clearance open; $150 total/$25 inference using verified eligible credits only, no unbounded/out-of-pocket spend without approval. Timing/publication/product external-action gates remain.

Observed checks: PDF pages/hash/extraction and selected renders; Git HTTPS clone/read and authenticated API identity/private/permission; Node 24.22.1/npm 11.19.1, Python 3.12.10, uv 0.13.5 commands; WSL/Docker daemon/cgroup inspection. Rulesets API 403 is an access limitation, not a failed push.

Preparation acceptance passed: `python scripts/check_preparation.py` checked required documentation, 276 unique complete trace rows/all 59 pages, S01–S42, local links, safe environment template and ignore coverage. `git diff --cached --check` passed after removing a trailing blank line. Gitleaks 8.30.1 scanned the full staged initial diff with redaction: zero findings after rephrasing one verified prose-only false positive; no scanner suppression was added. The staged inventory contains only intended documentation/templates and the preparation checker, with LF text policy. No source PDF, extracted pages, tool archives, environment, private data or runtime artifacts are staged. A separate critical pass is recorded in phase0-review.md; it is not independent human sign-off.

NOT RUN: application install/build/lint/types/unit/integration/e2e, PostgreSQL workflows, Vultr authentication/model probes, sandbox/containment/guest PID controls, real verifier/repair, approval/batch/PR integration, evaluation, cloud deployment, restore, public clean-browser/video/submission. Reason: no core exists; pre-kickoff implementation and account/charges gates. Catalogue descriptions and synthetic worked examples are not results.

Open blockers for later phases: timing; enrollment/eligible account/charges; actual runsc/resource/model compatibility; independent human review gap; ownership/license; product GitHub App/demo repository; public release/submission/domain/uptime authorization. Phase 0 can complete while these are explicitly recorded.

Verified Phase 0 acceptance checkpoint:

| Fact | Observed result |
| --- | --- |
| Repository | arslanabdulghaffar/ProofFlow; private |
| Branch | main, tracking origin/main |
| Acceptance commit | `40bc9edcb20e74e51aa0725dc976b5f0316f9f8c` |
| GitHub link | [Phase 0 acceptance checkpoint](https://github.com/arslanabdulghaffar/ProofFlow/commit/40bc9edcb20e74e51aa0725dc976b5f0316f9f8c) |
| Authenticated read | Passed: exact private repository API and local Git clone/read |
| Advertised write | GitHub permissions.push=true; separate from actual push |
| Actual push | `git push -u origin main` succeeded; no force/protection bypass |
| Remote verification | `git ls-remote origin refs/heads/main` equaled the full acceptance commit SHA |
| Working state at verification | Clean; main matched origin/main |

This receipt is committed after observing that push, so it intentionally names the acceptance commit instead of embedding its own self-referential SHA. The later status-receipt commit only updates README/progress/next-session; its final HEAD is also pushed and read back. To identify the latest handoff checkpoint, use `git log -1` and compare to `git ls-remote origin refs/heads/main`. Every future phase requires the same acceptance/checks/diff-secret review/docs/commit/push/readback sequence before DONE.

## Preparation follow-up for Phase 1

Starting checkout was clean main at `be67be18e3d88d91b0b65bdb7d24aed3d268e127`; fetch and remote SHA agreed. Authenticated GitHub metadata rechecked: exact repository, private=true, pull=true, push=true. Advertised permission remains distinct from actual checkpoint push.

Completed useful follow-up: current official schedule/rules and rule book rechecked; timing question resolved by owner (no early permission; do not ask again); exact deployed Phase 1 dependency/probe/acceptance checklist; public VM catalogue evidence plus authenticated unsubmitted Seoul Ubuntu24.04 control/worker quotes; account/login steps and organizer-question refinements; latest stop-after-Phase-1 policy made durable. See [readiness](phase1-readiness.md). No extra implementation or public release was performed.

Vultr login succeeded. Billing requires payment-method verification; its form shows $0.00 Total Available Credit but no verified redeemed-event balance, expiry or service coverage. No payment details entered/card linked/code redeemed. Compute previews were $24+$48/month after removing default backup add-ons; differing hourly displays remain documented. Provisional whole-project reservation is $145, including $25 inference, within the owner's $150 ceiling. Final fee/coverage/inference/minimum/termination terms and actual spending authorization remain external dependencies; no enforced spend cap exists yet.

Separate Codex critical review (not independent human sign-off): found Q08, an unresolved missing-attribute-versus-filter interpretation; recorded example/recommendation for Phase 2 without changing semantics. Clarified cleanup-success eligibility and cross-pipeline policy invalidation. Checks passed: preparation checker (276 entries/59 pages, links/templates/ignores), JSON parsing and budget arithmetic, staged whitespace, and redacted Gitleaks staged scan (zero findings). Reviewed the 15-file staged inventory: documentation plus public catalogue JSON only; no secrets, account identifiers, raw browser state, local tools or core code. Application, inference and deployed containment gates remain NOT RUN. This is a preparation checkpoint, not Phase 1 completion. Its containing commit is identified by Git HEAD and required remote readback rather than an impossible embedded self-hash.

## Phase 1 receipts and runtime follow-up — Nov 4

Continued from verified private main 3552af72826b75e7ccd32e0dd718b87bc56b0a7c. Implemented bounded immutable provider intents/results, exact-byte recovery without another request, crash persistence and synthetic database dump/restore comparison. Added kernel cgroup policy readback before launch and sampled CPU/memory/task evidence. Fixed current gVisor multi-file installation coverage by pinning and validating all eight release executables and a fixed companion search directory.

Observed: 206 Windows tests passed; 43 Linux-specific tests skipped there and all 43 passed under WSL. Ten trusted systemd lifecycle groups, nine real TLS fixture groups, 14 real PostgreSQL ledger groups and 14 SCRAM/driver/receipt groups passed. Provider HTTP remains explicitly mocked. All owned test containers, volume, units, mounts, processes and temporary certificate/secret fixtures were removed. Ruff passed. No candidate, pandas or gVisor guest ran locally. Trusted runtime version/flag inspection passed; no runtime installation.

Phase 1 remains IN PROGRESS / NOT ACCEPTED. Real deployed installation, runsc/pandas, guest network/resources and cleanup, live Vultr calls and credit-only spending enforcement remain NOT RUN. No cloud action or charge. Browser connector access failed (browser.user is unavailable); no fresh account observation claimed. Earlier credit evidence remains historical. No independent human reviewer is confirmed; automated checks and a separate Codex critical pass are not human sign-off. [Detailed evidence](evidence/phase1-receipts-runtime-2026-11-04.json).

Checkpoint review: all 33 intended source/test/configuration/document/evidence files reviewed; current and historical source hashes verified against the appropriate checkout/commit. The trusted helper image's installed source bytes match the checkout and its review container was removed. Documentation/traceability, Ruff, whitespace and staged redacted Gitleaks passed with zero secret findings. Authenticated GitHub metadata confirmed private=true and main; remote still matched the starting checkpoint before push. No private runtime artifacts, downloaded binaries, credentials or unrelated files staged. The containing commit is a WIP checkpoint, not Phase 1 acceptance; read its full SHA from Git and verify the remote.

Continued after pushing f1be7111ab2bd4e0e33209f3998f354d83646b32: checked official gVisor source manifests rather than stopping at the binary scanner's coverage gap. The 128-package source inventory reports 20 advisories; all nine scanner-HIGH advisories received primary-source context review. No clean-runtime claim or suppression. Full evidence records upstream severity differences and limits of binary-string inspection. No executable/source dependency changed, no guest code ran and no cloud action occurred. Phase 1 deployment acceptance remains blocked; this evidence update preserves that status.
