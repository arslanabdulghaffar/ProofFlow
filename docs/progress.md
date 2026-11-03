# Progress

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
