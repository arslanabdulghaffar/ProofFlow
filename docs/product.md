# Product and UX specification

Phase 1 has local health, byte-collection/log-buffer and budget-backed inference components plus a built, unexecuted worker image; no operational UI, execution endpoint or repair workflow exists. The owner is the only confirmed human contributor, with Codex assisting. The target user is a data/operations engineer responsible for small merchant revenue imports. The value hypothesis is repairing existing code while preserving declared behavior and exposing reliable evidence; no customer validation or ROI has been measured.

P0 outcome: compatible unseen input runs end to end without manual code fixes, edited outputs, database status changes or human stage advancement. A real original execution exposes a crash or silent data error; Vultr proposes actual changed code; each candidate executes in a fresh sandbox; an independent deterministic verifier accepts or rejects records; bounded retry or honest clarification/failure follows. An approved exact version automatically processes and re-verifies a fresh batch. A separately approved operator action creates a real draft PR with readback. Artifact export is a durable outcome but not a substitute claim for completed GitHub integration.

## Workbench screens and acceptance

| View | Information and actions | Evidence needed |
| --- | --- | --- |
| Intake | Labeled synthetic picker or compatible files, limits, disclosure of code/witness sent to inference, expiry | Unknown compatible input uses real backend; invalid field is identified without discarding valid selections |
| Contract | Plain join/units/duplicate/downstream rules; exact version/approver; explicit approval | No auto-approval by model; unknown business meaning blocks |
| Incident | Job ID, durable stage, real elapsed time, attempts, budget, known queue position, cancel | No fake percentage or timer-driven state progression |
| Evidence | Source/actual rows, per-merchant/currency totals, V01–V10 failures, witness and exclusions | Total-preserving ownership error is understandable within a minute |
| Attempts | Stored original/candidate bytes and server diff, diagnosis labeled model proposal, receipt and checks | Prior attempts remain inspectable; candidate PASS text cannot alter status |
| Versions | Exact bundle, limitations, activate/revoke/history | Stale approval fails visibly; guests control their workspace only |
| Batches | Fresh upload/API event, immutable version binding, completed/held output and receipt | New execution/verification happens without developer intervention |
| Export/integration | Authorized evidence download; operator repo/base/diff/draft preview and actual PR URL | Missing/failed integration is visible; guest has no external-write control |

Display explicit separate Queued, Running original, Proposing repair, Executing candidate, Verifying, Needs review, Verified awaiting approval, Active version, Batch completed, Held, Failed and Cancelled states. Preserve selection/scroll on updates. SSE reconnect uses Last-Event-ID then durable status refresh; refresh never resubmits. Slow/provider/quota failures retain evidence and explain retry conditions. Unsupported buttons are omitted or disabled with a reason. Replay has original timestamp and prominent label.

Keyboard operation, visible focus, semantic labels, clear table headers, textual statuses, readable contrast and code diffs without color dependence are acceptance requirements. Announce important async changes accessibly without reading every log. Support desktop and a usable narrow layout. Currency formatting derives exactly from integer units; API strings/BigInt prevent JavaScript precision loss. Show explicit timezones.

The first deployed useful screen in Phase 2 is an original-pipeline failure view using real persisted events and source/output evidence. Build repair, approval and batch views incrementally around real behavior. Final visual polish waits until the core path works. The release gate requires three fresh variants (IDs/order, overlapping merchant customers, changed amounts/refund) and one ambiguity case from intake to durable outcome without intervention; clean-browser refresh/cancel/unauthorized download tests accompany it.

The short public-facing description while preparing is: “We are building ProofFlow to repair supported revenue-import code, check actual records against approved rules, and show the evidence before a version processes another batch.” After authorized release, change tense only for demonstrated behavior. No first-self-healing-agent, formal proof, certified security, production readiness or early-submission advantage claims.

P1/deferred: rich analytics, animated presentation, witness minimization, runtime model routing, more connectors/profiles. Post-event only: large datasets, arbitrary repositories/runtimes, live ERP writes, browser automation, SSO/HA/multi-region and enterprise compliance. Keep security, budgets, exact approval and truthful states when narrowing scope.
