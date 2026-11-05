# Phase 5 security review — November 5

Separate Codex critical review; **not independent human approval**. Private synthetic deployment only. Phase 5 evaluation and lifecycle acceptance remain incomplete.

## Response deadline finding and fix

The four-slot HTTP boundary previously bounded event streams but not ordinary response transmission. A reader that stops receiving could retain capacity after body/SQL deadlines. The outer HTTP deadline now covers dispatch, response backpressure and busy replies: 30 seconds ordinarily, the existing 65 seconds for event streams. Cancellation unwinds the capacity context. It does not send another response after timeout. A timed-out write remains potentially committed: the existing scoped idempotency/status reconciliation rules still apply. This is not rollback or exactly-once transport.

Two transport-double regressions prove four blocked ordinary sends release slots and a blocked 429 also terminates. Linux suite: 716 passed, including descriptor, collector, secret-file and retention checks. The test deadline is shortened only by monkeypatch; production remains 30/65 seconds. No worker, verifier, contract, SQL, approval or spending limit changed. ASGI tests do not claim real TCP load testing; Uvicorn's eight-connection bound remains configured.

Review checked cancellation after response start, semaphore release, pre-header failures and the overloaded path. Synchronous work dispatched to a thread is not forcibly interrupted by asyncio cancellation; existing input bounds, SQL statement deadlines and process resource limits remain necessary. No general slow-client immunity is claimed.

## Image update and residual advisories

The pinned Python base inherited apt 3.0.3. [Debian's CVE-2026-109518 advisory](https://security-tracker.debian.org/tracker/CVE-2026-109518) identifies 3.0.4 as the fixed Trixie version. The build upgrades only apt/libapt-pkg7.0 to 3.0.4 using signed Debian repository metadata, HTTPS and zero package-download retries; no new package is installed. Image identity and all 72 allowed application files are checked after building. The installer requires this exact immutable image.

Fresh Trivy 0.76.1 database scan after the patch: 46 HIGH, 72 MEDIUM, 62 LOW, 6 UNKNOWN package/advisory pairs, zero CRITICAL. The two apt findings disappeared. Python product dependency audit reports no known vulnerabilities. These are scanner observations, not a security guarantee.

Remaining HIGH advisories are util-linux mount/nsenter helpers (CVE-2026-76642, 78408, 78409, 78410), libacl (54369), ncurses (CVE-2025-69720), SQLite FTS5 (119373), systemd-homed (16742), Perl Archive::Tar (9538), and zlib (76844); 2026 prefixes apply unless stated otherwise. No fixed versions are listed in this scan. Rechecking application call paths found no use of mount/nsenter/ACL helpers, terminal databases, SQLite FTS, systemd-homed or Perl archive processing. Non-root, no capabilities, no-new-privileges and read-only filesystem remain required; candidate execution remains on the separate worker. This is scoped reachability review, not binary analysis or vulnerability clearance.

The new zlib finding has inconsistent scanner title metadata (webpack). [SUSE's zlib advisory](https://www.suse.com/security/cve/CVE-2026-76844.html) describes the native gz* file-write/error-recovery path. Product exports use Python zipfile; no native gzwrite/gzclearerr call path was identified. Retain the affected package and unresolved native risk explicitly; do not dismiss the finding because of its incorrect title. Candidate-worker/runtime dependency review remains separate.

## Deployment and test boundaries

Only the existing controller is updated after a fresh credit guard check. Keep API/dispatcher permissions, private TLS endpoint, pinned worker/verifier, closed job/inference admission, existing PR and guard deadline unchanged. Deployed source/health/role readback and bounded real worker checks must have receipts before claiming acceptance. Native advisories and missing human review continue to block any claim of production security clearance. No new resource, public endpoint, PR or inference call is needed for these checks.

Observed readback now passes: exact new image/source, unchanged UID/resource/network controls, SCRAM and table/owner/schema denial for both roles, liveness200/readiness503/anonymous403. Sixteen fresh worker probes pass including network denial, filesystem, CPU, storage/inodes, output types/links/size, log capture, memory, timeout/descendant cleanup and pandas. Six verifier boundary groups and four fresh protected challenges pass. Network positive endpoints were not re-established; retain Phase1 positive-control evidence. A stale predecessor pin initially blocked installation without changing running services; readback identified the prior image, the exact pin was corrected and the upgrade preserved its containers.

## Evaluation tooling critical pass

Offline accounting binds records to a predeclared manifest with case/content and source/prompt/runtime/schema/grader/rate hashes. It rejects duplicate runs, changed schedules, invalid types and cap/usage violations; missing runs stay NOT RUN, unknown grades do not become zero incorrect acceptance, timeouts remain in denominators and latency, and outstanding reservations stay visible. Forecast caps are **not dispatch authorization**. Receipt hashes cannot prove actual calls; reconciliation and a funded durable runner remain required. Nineteen accounting/data tests use explicit invented fixtures only.

Twelve development cases are disclosed derivatives of the existing canary shape, with one repairable and one source-ambiguity/hold case per family. Small source-derived counts/totals were checked against explicit arithmetic before any model run. This is not independent human oracle review, unseen business data or undefined-policy clarification coverage. The initial units fixture chose JPY and failed to expose its injected conversion bug; preserve its five-run receipt. The revised development fixture explicitly uses fractional USD. Verifier, expected business policy and product thresholds were unchanged.

Final development validation ran24 real isolated executions:12 faulty originals rejected (2 schema crashes,10 semantic mismatches),12 positive controls matched (6 held). Worker/verifier cleanup passed. The driver binds execution/job/source/data/runtime/verifier identities through production classification functions. Only the designated worker executes payload bytes. Controller fixtures have fixed hashed sources, a fixed verifier path, the existing64-intent journal cap and closed product/model admission. No generic command, new secret privilege, model call or product state edit is introduced. These observations validate fixtures, not repair quality or an A/B/C/D score.

Final checks:649 Windows tests pass/86 Linux-only skips; all735 pass on Linux plus10 subtests. Admissions remain closed; services/retention active; PR#1 COMPLETE/3 writes. Credit$195.50 at14:14:23 UTC; guard deadline unchanged2026-11-06T21:05:35.177139Z. [Source-bound evidence](evidence/phase5-security-development-2026-11-05.json).
