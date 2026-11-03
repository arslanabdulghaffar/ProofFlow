# Resume ProofFlow

Current phase: **Phase 1 IN PROGRESS / deployed gates BLOCKED. Phase 0 remains DONE.** Official timing is now satisfied: on Nov 4 KST the event dashboard explicitly showed Live / Submissions open. The owner requested Phase 1 and authorized continuing independent work while resolving credit activation. Do not ask the timing question again.

Repository: private arslanabdulghaffar/ProofFlow, checkout A:\hackathon\ProofFlow, branch main. This work started from clean local/remote `79ccf59ec61b7885ce3ba63d82d3e87d5bfc7233`. Preserve history and user changes. Read AGENTS, product, contract, threat-model, rules, decisions, risks and phase1-readiness. Use `git log -1` and `git ls-remote origin refs/heads/main` to verify the latest WIP checkpoint; it is not Phase 1 acceptance.

## Immediate dependency

**Activation resolved:** owner completed the separate Gift Code tab. Dashboard now shows Account Balance and Remaining Credit **$200.00**, Charges This Month $0.00. Billing history shows completed Account Credit -$200.00, dated 2026-11-03, **expires 2026-12-04** (UI supplies date, no timezone/time). No card was requested/entered by Codex. No cloud resources or inference subscriptions exist. Do not repeat redemption or account-login questions.

**Remaining blocker:** verified service-specific coverage/tax and enforceable zero uncovered liability. The event page covers Compute and other Vultr services broadly; no hard non-overage/expiry-stop promise was found. General Vultr terms sections 7/9 retain fees/overage obligations, rather than guaranteeing suspension before debt. Console limits are 5 instances / $200 monthly instance cost, not a lifetime $150/$25 cap. Owner asked Codex to decide from official sources and continue while they sleep; this does not authorize personal spending. Do not ask the same question again. Record missing evidence and keep billable actions blocked unless actual event/account terms establish the required bounds. No organizer/support contact authorized or sent.

**$150 total/$25 inference mean eligible promotional-credit usage ONLY. No personal spending, deposits or payment-method charges authorized.** Authenticated current quotes: Seoul AMD shared control 2c/4GiB $24/month and worker 4c/8GiB $48/month, Ubuntu24.04, base public IPv4; default backup add-ons removed in previews, DDoS off. Initial 72h conservative compute estimate $7.92 plus at most $2 probe allocation. VPC/firewall/SSH not created and taxes/credit coverage not finalized. Inference creation notice now says usage-billed, no monthly fee, monthly usage below $1 not charged; model rates inspected, no subscription created. If all standing conditions become verified, proceed without another generic permission question. See current quote/coverage packet in phase1-readiness.

## Implemented and checked

- Trusted FastAPI/Pydantic health shell: `/health/live` 200, `/health/ready` intentionally 503. No route admits candidates or changes readiness. No upload/job/verifier/approval/provider/worker interface exists yet.
- `pyproject.toml` exact pins and `uv.lock`; Windows Python 3.12.10 clean runtime-only install passed. uv 0.13.5 under `.venv-tools/Scripts/uv.exe`; dependencies in ignored `.venv`.
- Eight local tests passed (ASGI boundaries and real loopback HTTP); Ruff passed. pip-audit found no known vulnerabilities in 48 installed Python distributions. This is not an OS/image vulnerability clearance.
- Trusted control Dockerfile pins Docker Official Python 3.12.16 slim trixie linux/amd64 digest and wheel hashes. Local WSL build and non-root/read-only/no-mount smoke passed, readiness remained 503, test container cleanup verified. `scripts/check_control_image.py` operates only on this trusted health image; it is never a candidate sandbox test.
- Trivy 0.76.1 image scan completed. Removed outdated runtime pip; final Python scan has zero findings. Debian retains 45 HIGH package/advisory pairs (9 unique), 72 MEDIUM, 61 LOW, 7 UNKNOWN, no CRITICAL. No suppression or clean-image claim. Full reachability/fix review remains open; receipt in docs/evidence/control-image-scan-2026-11-04.json.
- See phase1-readiness for recorded image identity, exact commands, dependency/critical review and all NOT RUN gates. No candidate or pandas execution occurred locally or in cloud; no Vultr inference request occurred. Local Docker is not the designated worker.

## Resume Phase 1

Once spending/account gates pass, provision the separate control/worker, private networking and operator HTTPS; pin and review runtime images; prove explicit runsc/systrap and benign Python/pandas on the worker; independently probe CPU/RAM/guest forks AND threads/storage/inodes/network/wall-time/output capture/cleanup; then perform bounded real Vultr coding/JSON calls. Follow the ordered checklist in phase1-readiness. No plain-Docker candidate fallback or fabricated provider success. Real readiness must be implemented from dependency/identity checks, not a flag or manually stored PASS.

After actual Phase 1 acceptance: critical review → durable docs/evidence → checks/secret scan → commit/push → remote SHA readback → report and **STOP for owner review before Phase 2**. Current WIP checkpoint is not that boundary. No automatic continuation to Phase 2.

The owner is the only confirmed human; independent human review remains open. Codex's separate critical pass is not human sign-off. Synthetic-only business approval remains narrow. Q08 (missing declared attribute on filtered-out row) needs owner decision before Phase 2 freeze, not now. Enrollment/Discord status, MIT ownership clearance, later product GitHub App, public release/submission and funded judging uptime remain external dependencies. Keep private; do not publish, submit, contact organizers or create reminders without instruction.
