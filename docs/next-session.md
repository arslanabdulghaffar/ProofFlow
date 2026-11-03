# Resume ProofFlow

Current phase: **Phase 1 IN PROGRESS, deployed acceptance NOT PASSED. Phase 0 DONE.** Read AGENTS, product, contract, threat-model, rules, decisions, risks and phase1-readiness before work. Keep private `arslanabdulghaffar/ProofFlow`, main, and preserve all existing changes. Current work started from remotely verified `c808c94d75fc1d7100565929580f19cef19aa341`; use actual Git/remote readback for the latest checkpoint.

## Current authorization

The event is live. The owner explicitly authorized using redeemed credits now while awaiting their Vultr support reply, and saved the management key. No more login/key/billing-sufficiency question is needed. $150 total/$25 inference are promotional credits only; no card, deposit or personal payment. Do not send support messages. The owner may be away for 12 hours: keep working through WIP checkpoints. After actual Phase 1 acceptance, update durable evidence/docs, commit/push/verify and report, then continue Phase 2 under the latest explicit permission. This supersedes the old stop-for-owner-review boundary. Failed critical gates still block dependent work. Q08 remains a substantive unapproved business rule; do not silently choose it. Publication/licensing remain separate unresolved gates.

## Real resources and private access

Exactly two real Seoul Ubuntu24.04 VMs now exist: control `vhp-2c-4gb-amd` $24/month, isolated worker `vhp-4c-8gb-amd` $48/month. One project VPC and distinct firewalls; SSH restricted to the current administrator IPv4. Backups and paid DDoS off. $145 reserved across compute72/inference25/later-storage18/incidental10/contingency20. Latest observed account usage $0.12, remaining $199.88; redeemed credit expires Dec4. No inference subscription or call yet.

Private state is `C:/Users/IT/.proofflow/deployment/phase1.json`; do not print/commit the whole file. It contains IDs, create/rebuild intents, host addresses, quote/reservations and guard state. Management key is encrypted at `C:/Users/IT/.proofflow/credentials/vultr-management.dpapi`. Project operator/server SSH keys and pinned known_hosts are in the protected deployment folder. Never expose credentials or send the management key to either VM.

`scripts/vultr_phase1.py` uses authenticated official API, durable pre-POST intents and an exclusive administrator lock. Do not rerun `prepare`, duplicate creates or retry uncertain POSTs. `hosts` safely refreshes actual VM status/addresses and pins. `Admin.host` uses exact Windows OpenSSH, explicit project key/known_hosts, no unrelated SSH configuration, and configured port22/443. A failed host key check must not be bypassed.

SSH now works on port443 with exact pre-pinned host keys on both VMs. Actual worker and private controller probe transport/PKI are installed. No management/inference key is on worker. Use scripts/install_probe_controller.py after any reviewed worker-source update to independently rebind runtime pins. Full installer refuses changed manifests; scripts/update_worker_image.py installs a new immutable image while retaining prior artifacts. Restricted private evidence is under deployment/evidence; do not print raw account state.

## Spending guard

`ProofFlow-CreditGuard` Windows scheduled task runs every15 minutes under the owner, invoking `scripts/Watch-VultrCredit.ps1`. Its first actual run succeeded and observed $199.88. `guard-last.json` is private. Guard cuts off at $120 observed spend, preserving $30 below project maximum, or the state's 72-hour funded review deadline; absolute teardown is Nov23 UTC. It latches admission closed, verifies exact project VM identity and deletes/readbacks only recorded project VMs. Lost replies reconcile absence. No inference caller is deployed; later callers must stay on control and use the separate DB ledger.

The task depends on Windows login/power/network/API/accounting availability. It is not a provider billing guarantee. Inspect task status and last report; never clear a stop latch or extend funded review without a fresh balance/quote/reservation check. The application ledger cannot stop VM meters. Stopped VMs still bill until destroyed.

## Existing implementation and artifacts

Latest full local suite: 224 Windows passed,45 Linux-only skipped; all45 passed separately. Eight offline credit-guard cases passed, Ruff passed. Current trusted integration evidence:11 systemd lifecycle groups,9 real TLS fixture groups,3 image-import groups,14+14 PostgreSQL ledger/SCRAM/receipt groups. None is actual runsc/guest/provider acceptance. Review the receipts in docs/evidence rather than rerunning unchanged fixtures without reason.

Worker code has fixed runsc/systrap, immutable SquashFS import, private mTLS RPC, resource/20s watchdog, bounded safe collection, durable journals/fences/ACK and cleanup. Controller has fixed Vultr client, SCRAM budget driver and immutable probe receipts. Health shell is intentionally ready503. No product workflow or public execution route exists.

- Worker image SHA: `2f6e7eeff7d8c66ec76010b2c19f4f1420abdeb28039e7a887f1878e258ccf96`; SquashFS SHA `98f64a3b6b9276f012aa1894089b7dbb0397c56479758cb8325ed0be00707393`. Retained WSL blob/import.json under `/var/tmp/proofflow-rootfs-tmp-fixed-final`, no local candidate/image execution.
- gVisor release `release-20261102.0`; all8 members/official archive pinned in `infra/gvisor/runsc-release.json`, local `.tools/gvisor/release-20261102.0`. Manifest SHA `7c50f528e54024e3c5b3fd05a28c6c46288c39c41701249bd8e53ce590133cbe`. Runtime source scan retains20 advisories and no binary reachability clearance; receipt has primary-source HIGH triage.
- Patched PostgreSQL image `sha256:9ed8d24e2d804f04bd228a4619c9ed43c3a8d2f4a09fe947b44b112615eb010d`, recorded scan zero known findings. Control image `sha256:6f768888022d817e095a3f6267882aaa93cc8d8d09dadb20a5c78bdfb8f55a2c`. Debian worker/control/helper advisories remain disclosed.

## Remaining ordered work

1. Finish deployed containment: supervisor/control death recovery; disposition default fork flood runtime host-task exhaustion (128 host tasks before63 guest children, fail-closed cleanup). Separate32-task voluntary guest fixture passed. Preserve failed capacity evidence; do not raise limits to pass.
2. Worker/PKI/VPC are installed. Control database/docker/health are not. Install bounded control/database storage, prove restoration reconciliation and restricted HTTPS readiness. Keep credentials off worker.
3. Actual pandas, UID/caps/read-only, network with positive controls, CPU/RAM/thread/storage/inode/capture/ordinary timeout/descendant cleanup passed; receipts in docs/evidence/phase1-deployed-2026-11-04.json. Repeat changed dependencies as warranted. Failures and partial probes are retained. The fixed suite still reports the unresolved default fork-capacity failure honestly.
4. Establish actual inference subscription/key/quotes and deployed durable caps before bounded real JSON/coding/ambiguity probes. Preserve exact receipts/usage/latency. Execute generated code only on the designated worker after critical containment gates pass.
5. Separate critical review, source-bound evidence/docs, appropriate tests, secret/diff/privacy checks; commit/push/read remote SHA. Phase1 is DONE only after all acceptance and remote verification. Then report and continue authorized Phase2 work; no generic continue question.

No independent human review is confirmed. Do not label Codex/automated checks as human approval, resource creation as deployment acceptance, or a WIP checkpoint as phase completion.
