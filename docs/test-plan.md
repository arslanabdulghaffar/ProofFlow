# Acceptance and verification plan

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

Planned commands, none implemented yet: make doctor (presence/version/dependency checks without secret values), dev, test, sandbox-probe, smoke, eval, build, deploy, verify-release, backup, restore-test. Each needs prerequisites, safe defaults, output/failure codes and cleanup documented; nonzero on failure. A placeholder zero exit is not a check. Destructive reset must name and validate an explicitly disposable workspace.

## Observed local budget checks — Nov 4

`scripts/check_budget_postgres.py` passed 14 groups against pinned local PostgreSQL 18.6, including 20 competing reservations, 12 claims of one intent, SIGKILL/restart with durable unknown usage, separate runtime role rejection, expiry and transaction-setting failures. It creates/removes only its own labeled no-network container and volume; trust authentication is fixture-only. `tests/unit/test_probe_plan.py` adds 18 offline synthetic-quote cases. Full Windows suite: 48 passed, 24 Linux cases skipped; unchanged collector's prior 24 Linux passes retained. This is partial T12 evidence, not deployed cost/worker/provider acceptance. [Receipt](evidence/phase1-budget-postgres-2026-11-04.json) includes image scan limitations.
