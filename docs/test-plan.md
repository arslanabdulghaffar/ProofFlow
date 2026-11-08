# Acceptance and verification plan

Current Phase6 operational coverage and command semantics are listed below. Dated entries
retain the scope observed at that time; later public TLS/guest acceptance is recorded in
[guest evidence](evidence/phase6-guest-operation-2026-11-08.json). The historical NOT RUN
public-ingress status is superseded; full compromised-host recovery is still unproven.

November8 ingress/recovery:928 Windows tests pass/191 platform skips,161 scoped Linux
tests pass and6 later read-only smoke-tool tests pass. Linux covers actual origin-file
ownership/no-follow rules and expiry during descriptor-based inert recovery. Actual
private TLS smoke denies forged authority; both deployed container policies and73
source files match. Real two-DB restore passes14 groups, including old-session lookup
and runtime ACL/login denial; actual updated-image tmpfs recovery/timeout/cleanup passes.
Prepared systemd units validate on the real host without activation. New dependency
inventory equals its predecessor. Public TLS/guest/browser acceptance and full disaster
rebuild are NOT RUN. [Receipt](evidence/phase6-ingress-recovery-2026-11-08.json).

November8 private package checks:8-slide PPTX package integrity,Arial font policy,
geometry/native-table ownership and Artifact Tool import pass. Every final slide and
standalone1920×1080 cover visually inspected.8 negative archive/XML/table-drift probes
reject unsafe input. Frozen96-job artifact accounting rechecked offline; no model call
or source execution. Final package SHA/file-set/source-commit verification follows the
clean source checkpoint. Native PowerPoint and authenticated submission-form checks
NOT RUN; public-release gates remain open. Product tests are not repeated for unchanged
runtime/schema/contract code. No independent human sign-off is claimed.

`pytest -q tests/unit/test_release_package.py`: 13 pass. These inert archive/XML tests
cover private paths, Windows normalization, symlinks, declarations, encoding and bounds.
An initial Windows separator probe failed; raw-byte construction and original-name
validation were corrected before the passing rerun.

Final ZIP independently re-opened: 13 files, 486 tracked source files, all CRC/hash/file
set/source-commit and media-pin checks pass. Selected source bytes match `git show`;
package documents match committed source after line-ending normalization. Native deck
table matches committed content and frozen accounting. See the package evidence receipt.

November8 Phase6 scoped checks:83 Linux/42 Windows cases pass,including21 new unique
portable crypto/deletion/expiry,scheduled integrity/retention and dated-funding cases.
Actual Windows task LastTaskResult0 after integrity hardening;nonempty consistent
capture/AES-DPAPI roundtrip and Windows-to-Linux inert selection pass. The same portable
package excludes the normally deleted asset; no stale inventory used as authority.
These are actual synthetic recovery probes,not a fresh compromised-host promotion.

One new real Vultr call produced changed source,3 matching fresh checks,exact synthetic
approval and a completed different batch. Original demo harness receipts remain FAILED:
wrong expected terminal UI, then mistaken public report.worker access. Read-only journals
prove both loops killed(signal9),no accepted output,cleanup and absent kernel writers.
No paid rerun. Local forced browser exception now flushes video. Final139.04s MP4 fully
decodes;key frames reviewed for readable claims/absence of secrets;edits are manifested.
Live readback569 CLEANED/344 fences,zero missing deadlines/workspaces/clones,healthy
services,closed admissions. [Evidence](evidence/phase6-scheduled-portable-demo-2026-11-08.json).
Full1044-test baseline not rerun: production runtime/schema unchanged; these scoped
checks supplement dated acceptance. Owner custody,lost-authority recovery,public smoke
and human sign-off are NOT DONE. Earlier dated results below remain scoped history.

Phase6 T21–T23 progress:41 scoped Linux cases pass(12 new bounded-pipe/target/deadline
cases plus29 existing restore/backup cases). Real separate-PostgreSQL encrypted drill
passes13 groups in20.824s,including concurrency,exporter failure,missing authority,
quarantine and deletion during restore. A real1s shortened watchdog fault kills its
trusted test client; production cap stays55s. Windows pipe suite NOT RUN(Linux-only
selectors/Unix Docker socket). Full1044-test baseline not rerun: production source and
dependencies unchanged. Current checks do not replace that dated baseline.

Actual existing-host empty-product export/vault roundtrip passes. Five fresh private
Chromium contexts pass four original outcomes and a separate unchanged-source protected
check/exact activation/new-batch path; no inference. Refresh,mobile,download,logout and
normal retention checked. Two harness failures remain recorded,not counted as passes.
Final readback562 CLEANED/339 fences/zero missing deadlines/workspaces/clones. [Evidence](evidence/phase6-recovery-rehearsal-2026-11-07.json).
Composite Phase6 gates stay partial: scheduled/portable recovery,compromised-host rebuild,
real-AI final recording,public release/media/form and funded judging uptime remain.

Phase5 private technical acceptance audit now passes. On patched149 hosts,all16 fresh
T07/T08 probes pass with confirmed cleanup;exact72 source files and container policy,
HTTP200/503/403,role denial and retention readback pass.1044 Linux+10 subtests;
870 Windows/174 Linux-only skips. New13 scanner-report and8 kernel-plan tests cover
false-clean results,metadata/warnings,package/version/origin/removal drift. Frozen
comparison artifact rechecked without new calls. [acceptance evidence](evidence/phase5-binary-acceptance-2026-11-07.json). Phase6 T21–T23 release/portable
disaster obligations and independent human review remain separate;older counts below
are historical. No exploit or candidate executes on the development/control computer.

Latest runtime/rebuild evidence:28 concrete container-drift cases;both real deployed
container configurations pass;actual API stop/archive/reconstruction,72 exact source
files,unchanged durable authority,revoked session denial,exact authorized download and
fixture cleanup pass. [Evidence](evidence/phase5-runtime-incident-2026-11-07.json). Full compromised-host/key-rotation recovery NOT RUN.
Source scan20 findings;binary package recognition0 means uncovered,not clean.

Latest cancellation evidence:7 real executor/ASGI-double cases cover disconnected and
deadline-ended bundle builds (success/error),bounded asset IO,late upload without
registry commit and revocation during export. Six deployed private HTTP groups and
new-image inert recovery/20.437s kill-cleanup pass. [Receipt](evidence/phase5-http-cancellation-2026-11-07.json).
No additional model call,worker candidate or PR; full host-compromise drill NOT RUN.

Latest full local suites: **1023 Linux tests plus 10 subtests**, **849 Windows tests / 174 Linux-only skips**. Ruff, document/traceability hygiene and secret scan accompany the private checkpoint. These tests do not substitute for missing portable disaster/production recovery or public-release acceptance.

Vault recovery follow-up:13 explicit policy-double cases exercise clock rollback,
post-read expiry,missing/corrupt clock,cipher tampering,partial publication/retirement,
bad-record isolation,hardlinked pending files and capacity. Actual Windows checks
separately cover DPAPI/private ACL/AES/natural expiry and process exclusion/death/
interrupted-save cleanup. Native review uses a network-denied pinned local product
image and read-only designated-worker schema/library inventory, not exploit execution.
[Evidence](evidence/phase5-vault-native-review-2026-11-07.json).

Actual local recovery container: inert authenticated asset roundtrip,pre-decryption
tmpfs/cgroup checks,deliberate hang after materialization,independent20s timeout,
exit137 and removed container without Python finally. No ordinary host asset directory
or candidate execution. Five final Linux driver-boundary/four Windows tests pass;
unexpected module/symlink cases were added after the full suites above. Completed live
recovery jobs are not replayed. Source cache contains only five trusted files; keys
and backup/current-authority bytes travel only on stdin.

Current T22: six SQLite authority-expiry tests cover replay after pruning, clock rollback,
fresh execution versus expired job, legacy migration, quarantine and busy WAL retry;
five Linux marker tests cover idle-only expiry and unsafe files. Fifteen asset-envelope/
materialization tests cover authentication, hashes, limits, age, current deletion
authority and inert files. Four clock-wait tests preserve future-time rejection.
Real local PostgreSQL restore and deletion-expiry checks each pass seven groups. Real
signed-delivery SQL races also verify fresh UUIDv7 batch IDs after migration020.
Actual Windows private ACL/DPAPI/AES roundtrip and natural8-second key expiry pass.
Actual live quiesced encrypted DB+five-asset snapshot recovered four authorized assets
while excluding a normally deleted workspace, with second authority read and cleanup.
Read-only live lifecycle check verifies sources,deadlines,clock floor,healthy timers,
closed admissions and zero remaining workspaces/clones. Sixteen fresh deployed security
probes pass. Natural seven-day expiry remains NOT RUN; no live clocks were changed.
[Evidence](evidence/phase5-encrypted-recovery-2026-11-07.json).

T22 follow-up: `test_worker_receipt_retention.py` covers real SQLite byte retirement,
replay/conflict/generation denial, quarantine/recovery deadline, one legacy grace,
bounded sweeps and pinned-WAL-reader failure/retry. `test_restore_guard.py` covers
stale/future/malformed authority, expiry/lifetime change, deletion races, dump binding
and target rejection. `python -m scripts.check_deletion_safe_restore` performs a real
local pg_dump/restore in a disposable networkless fixture, completed/pending deletion,
pre-sanitization login denial, production-target/schema rejection, authority stripping
and second-live-read deletion detection. Cleanup is verified. It contains synthetic
metadata/assets only; production promotion and portable key recovery are NOT RUN.

T20 final comparison: 96/96 actual jobs, 79 reconciled responses, no unaccounted cleanup; all failures, calls, costs and denominators preserved. Original/candidate/source/runtime/verifier/ledger/proposal/retirement audit passed; the portable artifact recomputes all case hashes/oracles/metrics offline. [Measured report](../eval/final-comparison-2026-11-06.md), [evidence](evidence/phase5-final-comparison-2026-11-06.json). One repeat/shared template/no human oracle review and A/C orchestration differences are explicit limitations. Funding review has 21 offline fault cases plus actual quote/credit/SQL/guard readback, without a cap increase. T22 metadata/restore lifecycle remains incomplete.

Latest Phase5 follow-up:788 Linux+10 subtests,664 Windows/124 Linux skips;6 source-failure SQL groups,11 original queue groups,5 repair groups;72 exact image files;6 deployed verifier boundary groups and7 HTTP groups/3 cases. Actual code crash + successful missing-output diagnosis and invalid-source hold pass; first missing-output failure remains recorded. One real API repair/one Vultr call/three fresh proofs passes without activation. Final A/B/C/D and lifecycle review remain incomplete. [Evidence](evidence/phase5-source-repair-2026-11-06.json).


Latest22:30 KST: Phase4 acceptance passes under the owner's no-new-PR constraint. Explicit pending-ack seed in a disposable DB; actual unchanged SQL/controller/adapter, real existing-PR GET reply loss, natural180-second lease expiry, higher-generation takeover, stale/write rejection, pending/completed restart, no-op redelivery and cleanup.628 Windows passes/86 Linux skips;7 mutation-denial cases. Original POST-create response loss remains NOT_REPRODUCED; this is recovery-only evidence combined with the separate real PR creation/readback. [Phase4 acceptance](evidence/phase4-acceptance-2026-11-05.json).

## Phase4 acceptance audit — November5

| Obligation | Evidence and remaining scope |
| --- | --- |
| T13 exact versions/revocation | Real SQL hash/actor/CAS/revocation checks and deployed synthetic activation/revocation; prior [version/batch](evidence/phase4-versions-batches-2026-11-04.json) and [browser](evidence/phase4-integrations-2026-11-04.json) receipts |
| T14 immutable fresh batches | Deployed clean/held batches and queued revocation; real SQL activation versus existing batch binding; prior receipts above |
| T15 controller/fencing/recovery | Prior deployed worker/controller cleanup evidence; new all-stage controller fault doubles and real disposable SQL pending takeover/fencing; recovery-only drill adds actual existing-PR GET reply loss, native lease expiry and restart against explicit disposable pending state; no production rewinding |
| T16 signed delivery/idempotency | Prior deployed exact duplicate returns same batch; changed body/bad signature/revoked connection denied, with real SQL/HTTP signature cases |
| T17 external action | Actual App setup/scoped authentication/read-only preview/base/tree passed; new tree/shape rejection tests and deployed static probes pass. Actual exact-approved private PR#1 creation/readback, completed restart and idempotent approval replay pass. Recovery-only drill against existing PR passes; original POST-create response loss NOT_REPRODUCED |

[Current receipt](evidence/phase4-readback-hardening-2026-11-05.json):607 Windows passes/86 Linux-only skips, seven actual disposable PostgreSQL groups, four Chromium groups with mocked HTTP. Actual upgraded dispatcher uses installed App credentials only for GETs and scoped token issuance. No PR/branch/commit write or new preview. Product readiness remains503. Evaluation/lifecycle/portable backups retain Phase5/6 scope. No independent human sign-off.

Phase2 gate is now technically accepted per phase-plan.md; [Phase2 acceptance](evidence/phase2-acceptance-2026-11-04.json). Current run:498 Windows tests pass (64 Linux skips),19 targeted Linux asset/retention tests,3 Node recovery groups and4 real deployed acceptance groups. Actual fault injection covers lost acknowledged POST plus reload/same-job retry and interrupted real-journal deletion plus production recovery. Earlier bounded verifier/canary/HTTP/events/SCRAM/cancel/controller/restart results remain historical source-bound evidence. T01–T05 and the Phase2 portions of T06/T08–T10/T15/T18 are satisfied for the private original path; candidate repair, version/batch/external writes, held-out evaluation and T22/T23 release checks retain their later gates. Human independent review is not available.

Current evidence supersedes historical partial counts below: Phase1 accepted; Phase2 has478 Windows passes/55 Linux skips, separately executed10 Linux asset groups,10 actual PostgreSQL queue groups,6 verifier boundary and4 Unix-peer groups, plus6 deployed boundary groups,4 fresh worker canaries,7 private HTTP integration groups and2 actual cancellation/dispatcher-loss cases. Actual SCRAM role denials, restart and encrypted off-VM database restore passed. Source-bound integration receipt retains failures. Unimplemented SSE, guest intake, repair, activation, fresh batches and PR workflows are not covered. Fixture programs ran only on the designated worker; trusted tests ran locally/control. Human review remains unavailable.

Phase 1 local evidence: 30 Windows tests pass (health, image-check validation, bounded logs); 24 Linux collector tests separately pass using trusted static fixtures. These are partial components only. Deployed/core acceptance tests remain **NOT RUN**; no candidate code executes locally. Phase 0 checks remain historical in environment-readiness.md and progress.md. Test cases below specify full acceptance evidence, not completed results. Use trusted test code; every uploaded/generated candidate and adversarial runtime probe executes only on the designated restricted worker.

| ID / phase | Test and required observed outcome | Evidence |
| --- | --- | --- |
| T01 /2 | Exact decimal/minor parsing, signed64 boundaries, zero/refund, USD/JPY, invalid precision/overflow, JS >2^53 | Unit vectors + real parser/verifier results; exact API string rendering |
| T02 /2 | Composite join and source identity; total-preserving ownership swap, dropped/multiplied/invented row | V02/V03/V04 fail with source witness; exact same totals insufficient |
| T03 /2 | Exact duplicate rep/link; conflicting group; mixed violations; reorder; missing lookup; identical lookup collision | V07/V08 outcomes match contract examples; no dangling links |
| T04 /2 | Currency/explicit-offset/UTC microseconds; no FX/guessed zone/leap second or rounding | V05/V06 exact outcomes |
| T05 /2 | Allowed filter boundaries, exact attributes, all rollup fields, empty eligible result | V10 mutations fail; every filtered/duplicate occurrence accounted; no valid-row quarantine |
| T06 /2–3 | Original/candidate/canary are actual separate executions; full inputs checked; bounded witness only diagnostic | Supervisor receipts + independent reports/digests; unchanged-original outcome not AI repair |
| T07 /1/5 | CPU/RAM, guest forks AND threads, output/scratch/inodes, network/host-marker, 20s loop and child cleanup | Separate measurements per control per sandbox.md; all NOT RUN until actual worker |
| T08 /2/5 | UTF-8/header/type/byte/row/cell/nesting limits; traversal, symlink/hard link/FIFO/device/unexpected output | Bounded rejection before inference or safe collection failure; no host writes |
| T09 /2/5 | Two known workspace IDs across read/write/SSE/export/cancel/approval/download; revoked/expired sessions/API tokens | 401/403/404 as defined; no side effect or disclosure |
| T10 /2/5 | XSS-looking cells/logs, formula export, SQL/shell metacharacters, SSRF/redirect, CSRF/fixation | Text rendering, exact canonical output, safely escaped separate export, no fetch/execute |
| T11 /3 | Provider 429/timeouts/5xx/malformed JSON/missing usage/truncation/refusal | <=5 total calls, <=2 transport retries, <=3 proposals, deadlines/reservations enforced; unknown bill retained |
| T12 /3/5 | Concurrent reservations + guest/IP/project quota races, exhausted cost/token/time | No new expensive call beyond remaining cap; operator eval bypass never removes safety/cost caps |
| T13 /4 | Change each code/contract/runtime/verifier/report hash; stale active-version request; revoke at each boundary | Old approval rejected; no changed bytes inherit permission; historical facts retained |
| T14 /4 | Queue A, activate B; revoke A while queued/running; race revoke with terminal commit | Ordinary activation preserves A binding; revoke blocks A execution/publication; no rebinding |
| T15 /2/4 | Kill controller after create; lease expires; delayed old worker receipt; worker reboot/journal uncertainty | Fence generations, query known ID, one committed result, no uncertain PASS or leftover sandbox |
| T16 /4 | Same idempotency key/body, changed body, valid/stale/bad HMAC, repeated event | Original receipt or 409; invalid auth no asset fetch/job/model/write |
| T17 /4 | Approve concrete draft action; moved base/repo/path/code; timeout after GitHub accepted create; redelivery | One actual draft PR, exact head/file/draft/repo readback; stale action can't dispatch; real integration status |
| T18 /2/4 | Disk full between bytes and DB commit, verifier crash, artifact corruption, cleanup failure | FAILED_INFRA/held, no approval/completion; recover exact trusted step only if hashes intact |
| T19 /3–6 | Clean-browser unseen input, refresh/SSE reconnect, cancel second job, unauthorized artifact, slow/error states | Live UI follows committed events; useful accessibility/narrow-layout behavior |
| T20 /5 | Frozen held-out A/B/C/D, interleaved and equal budgets, ambiguity cases, flawed final candidates | All actual run records, repair vs acceptance safety separately scored; no fabricated blanks |
| T21 /6 | Clean trusted install/deploy, source/live manifest match, additive migration rollback compatibility | Build IDs/digests/lockfiles/schema/prompt/model, readiness + real smoke |
| T22 /6 | Encrypted backup restore to separate environment; deleted workspace tombstones; reference/hash checks; benign replay | Actual measured restore, no production overwrite or resurrected data/approval/outbox |
| T23 /6 | Three new variants + ambiguous case from full intake through new batch; downloaded bundle replay | No manual repair/status/output/oracle edits; exact release video links to evidence |

Protected changes receive an automated check and a separate critical review pass. Human independent review is an open gap per owner authorization; do not describe these passes as human sign-off. Unit tests should protect meaningful boundaries, not mirror implementations. Integration checks use real PostgreSQL/verifier/artifacts; mocked PASS cannot establish verification. Fault injection is labeled and cannot replace real provider/runtime/integration acceptance.

CI plan: lockfile install → lint/types/schema drift/secret scan → trusted units → real DB integration → isolated runtime suite on restricted worker → frontend behaviors → production images and dependency/license scans → release manifest → reviewed deploy and real smoke. Candidate code never executes on a privileged shared runner. Credentials or reachable critical vulnerabilities block affected release; other findings get documented triage.

Current operator checks use the actual scripts below; the earlier proposed `make` aliases
were not implemented. Run from the repository root with the locked Python environment.

| Command | Prerequisites and actual scope | Failure behavior |
| --- | --- | --- |
| `python scripts/check_preparation.py` | Local documentation only | Nonzero for missing/invalid links, traceability or repository hygiene |
| `python scripts/check_operations.py` | Configured owner Windows credentials/vault/tasks; existing hosts and public TLS | One-shot GET/SELECT/status checks; fixed blocker codes and nonzero; no new admission or schedule |
| `python scripts/build_release_package.py --verify PRIVATE-ZIP --expected-sha256 TRUSTED-HASH` | Existing private archive and separately trusted checkpoint hash | Bounded inert archive readback; no extraction/execution; nonzero on drift |
| `python scripts/check_saved_database_recovery.py` | Owner vault/SSH, fresh current deletion authority, cached pinned WSL database image | Fresh RAM-only isolated SQL quarantine, second authority read and cleanup; no production restore; nonzero on failure |
| `python -m scripts.check_saved_database_deadline` (Linux/WSL) | Cached pinned database image and trusted Docker access | Empty90s watchdog drill; requires exit137/AutoRemove after launcher exits; scoped cleanup on failure |

These checks do not replace worker containment, paid evaluation, exact approvals or a full
compromised-host rebuild. Completed one-shot deploy/PR/evaluation scripts are not a generic
smoke suite and must not be rerun blindly. Destructive reset must identify an explicitly
disposable workspace. No test may turn stored PASS or ordinary HTTP200 into release approval.

## Observed local budget checks — Nov 4

`scripts/check_budget_postgres.py` passed 14 groups against pinned local PostgreSQL 18.6, including 20 competing reservations, 12 claims of one intent, SIGKILL/restart with durable unknown usage, separate runtime role rejection, expiry and transaction-setting failures. It creates/removes only its own labeled no-network container and volume; trust authentication is fixture-only. `tests/unit/test_probe_plan.py` adds 18 offline synthetic-quote cases. Full Windows suite: 48 passed, 24 Linux cases skipped; unchanged collector's prior 24 Linux passes retained. This is partial T12 evidence, not deployed cost/worker/provider acceptance. [Receipt](evidence/phase1-budget-postgres-2026-11-04.json) includes image scan limitations.
