# Phase 1 entry and deployment proposal

## Current kickoff state — 2026-11-04 KST

**Phase 1 IN PROGRESS, not accepted.** Official dashboard explicitly Live / Submissions open at the Nov 4 recheck (trusted clock Nov 3 16:33:54 UTC / Nov 4 01:33:54 KST). The owner authorized implementation. The Oct 24 section below is historical and superseded where noted here; its proposed topology and ordered deployed checks still apply.

Account activation **RESOLVED during this run**: the initial card-form summary showed a $200 promotion while Dashboard credit was zero. Codex located the distinct Gift Code tab at the event-linked `/billing/?promo=HACKATHON`; the owner completed it privately. Subsequent Dashboard: Account Balance $200.00, Remaining Credit $200.00, Charges This Month $0.00. Billing history: completed Account Credit -$200.00, dated 2026-11-03, **Expires 2026-12-04**. The UI specifies no expiry timezone/time; this ledger date supersedes the earlier generic 30-days-after-signup label. No code was read/submitted and no payment method added by Codex. No repeated redemption/login question is needed.

The [event instructions](https://lablab.ai/ai-hackathons/vultr-hackathon) broadly cover Compute and other Vultr services and describe adding a payment method for post-event continuation. They do not explicitly establish inference/tax coverage or guarantee stopping before uncovered charges. The authenticated account has a 5-instance / $200-monthly-instance-cost allocation limit; no total-spend stop was found. [Vultr terms](https://www.vultr.com/legal/tos/#tos_7), read in the browser after web extraction failed, retain applicable fees/taxes/overage obligations in sections 7/9; no event-specific exception was shown. **No personal spending, deposits, card charges or uncovered liability are authorized.** Decision: billing bounds/coverage gate remains blocked. The owner asked Codex to use official evidence and decide while they sleep; do not repeat the question or interpret this as personal-spending authorization. No cloud resource, subscription or inference call has been made.

[Public plans rechecked Nov 4](evidence/vultr-plans-2026-11-04.json) plus **authenticated quotes rechecked after activation**: control/worker remain $24/$48 monthly, API/config header $0.033/$0.066 hourly. Both Seoul plans, Ubuntu24.04 x64 and Public IPv4 were selectable; final previews showed $24/$48 and rounded $0.04/$0.07 hourly. Plan-selection table still shows $0.036/$0.071. Backup defaults re-enabled on plan switch and were removed again in unsubmitted previews ($4.80/$9.60 excluded); DDoS off. No Deploy click. Private VPC starts at $0/month in [official overview](https://docs.vultr.com/product-overviews/vpc-networks); no NAT gateway is proposed, and VPC/firewall/SSH have not been created. Preview does not establish tax/credit coverage. Initial 72h estimate remains conservative **$7.92 compute + at most $2 probes**, not a final bill or hard cap. Project allocation remains $145 within $150, inference at most $25. Stop/deletion/expiry treatment must bound ongoing charges; an application ledger alone is insufficient.

### Current inference quote (not activated)

Authenticated Create Inference notice: usage billing, **no monthly fee**, invoiced monthly per subscription; a month below $1.00 is not charged (not a $1 minimum). This supersedes older minimum/plan assumptions. Checkbox remained unchecked and Create was never submitted. [Live prices](https://api.vultrinference.com/docs/models) match the console. Examples per million input/output tokens: DeepSeek V4.1 Flash 1017 (`deepseek-v4.1-flash-1017`) $0.15/$0.60; GLM 5.3 (`glm-5.3`) $0.75/$3.00; Qwen3.8 Flash Next $0.10/$0.20. These are candidates for the planned two-model probe, not compatibility/JSON/coding results. No model is selected as proven. Reserve worst-case input/output/retry and uncertain usage before each call; the $2 probe/$25 aggregate enforcement is still unimplemented and blocks requests. No automatic subscription activation from this quote.

### Trusted foundation evidence (local only)

[Machine-readable foundation receipt](evidence/phase1-foundation-2026-11-04.json) records source-file hashes and the scope of each observed result.

| Check | Observed result / scope |
| --- | --- |
| Exact dependency resolution | uv 0.13.5, pyproject exact direct pins, 49 lock entries including project; Windows Python 3.12.10 |
| Fresh runtime-only install | `uv sync --locked --no-dev --no-build` in ignored `.venv-runtime-check`; 14 runtime dependencies; trusted app import passed |
| Unit + loopback HTTP | `uv run --locked pytest -q`: 22 passed (8 health/HTTP + 14 hardening validation cases); liveness 200, readiness 503; no unimplemented intake/approval/docs routes; caller flags cannot assert readiness |
| Static checks | Ruff on api, tests and control-image checker passed |
| Python dependency audit | pip-audit 2.10.1: no known vulnerabilities in 48 installed distributions; not an OS/image or universal security clearance |
| Image build | `infra/images/control.Dockerfile`, Linux amd64; Python 3.12.16 slim trixie digest `sha256:1148dbb014615300fa7e713b2f94f550c0d1c69780c0805f84f093ceee34dd0b`; binary wheels with required hashes; deny-by-default build context |
| Built local image identity | `sha256:6f768888022d817e095a3f6267882aaa93cc8d8d09dadb20a5c78bdfb8f55a2c`; local build only, no registry push/deployment |
| Trusted image smoke | Docker 29.9.1 in WSL; uid 10001, read-only root, no capabilities, no-new-privileges, no mounts/published ports, network none; configured 256MiB/0.5CPU/32 host PIDs. Health 200/503, Python 3.12.16, exact test container absent after cleanup |

The smoke checks configurations and trusted health behavior; it does NOT stress-test resource enforcement, establish malicious-code containment or satisfy deployed Phase 1 gates. Candidate code never ran on this development machine. Linux image Python differs from the local Windows interpreter; both are recorded, neither silently substituted for a future worker identity.

Reproduce the trusted image build on a Linux Docker host from repository root:

```sh
docker build --platform linux/amd64 -f infra/images/control.Dockerfile -t proofflow-control:phase1-local --iidfile /tmp/proofflow-control-image-id .
python3 scripts/check_control_image.py "$(cat /tmp/proofflow-control-image-id)"
```

The checker creates one generated-name local test container, no mounts/secrets/ports, and removes only that container. Do not pass a candidate image. Regenerate hashed requirements with `uv export --locked --no-dev --no-emit-project --no-header --no-annotate --format requirements-txt --output-file infra/images/control-requirements.txt` after reviewed dependency changes.

### Dependency and separate critical review

Reviewed scope: FastAPI/Pydantic schemas and Uvicorn trusted HTTP serving; httpx/pytest/Ruff/pip-audit are development checks only. Exact versions and metadata license inventory are in [THIRD_PARTY_NOTICES](../THIRD_PARTY_NOTICES.md); lock includes package hashes. Only public PyPI wheels installed, no dependency source build. The Docker Official Python image is pinned by resolved amd64 manifest digest; installed license files remain in image layers. Trivy 0.76.1 scanned the final image: [reviewed scan/package receipt](evidence/control-image-scan-2026-11-04.json). The initial bundled pip 25.0.1 had five MEDIUM/one LOW findings; installer was hash-pinned to pip 26.3 for build and pip then removed from runtime. Rebuilt image smoke/cleanup passed. Final Python result has no findings; Debian retains 45 HIGH package/advisory pairs (9 unique), 72 MEDIUM, 61 LOW and 7 UNKNOWN, no CRITICAL. No HIGH fix version was reported. Current health code does not process files, invoke shell/mounts or use SQL; this limited exposure is not proof of non-exploitability. Full reachability/vendor-fix and release attribution/provenance review remain open. No finding suppressed or image declared clean. Trivy archive checksum matched official release metadata; scanner is local development tooling, not in the service image.

Separate Codex critical pass: checked no candidate import/exec/dispatcher, no provider key access, no readiness override, loopback default for development, no exposed documentation or intake routes, restrictive build context, non-root runtime, exact-hash dependencies and named test cleanup. Corrected deprecated Starlette TestClient use by testing via HTTPX ASGITransport plus a real HTTP process test. Container checks are explicitly labeled trusted/local and do not claim runsc or enforced guest limits. These checks are not independent human approval; that review gap stays open.

NOT RUN: deployed TLS/private topology/database, gVisor identity, benign pandas, hostile resource/network/output/watchdog/cleanup probes, real Vultr models/JSON/coding, provider spend reservations, deployed image provenance/reachability approval and all later product paths. Credit coverage and bounded spending still block deployed work; activation is now verified. No Phase 1 completion or feature advancement beyond this foundation is claimed.

### Security follow-up from the verified foundation checkpoint

Continued from clean local/remote `1798c30accf9f4d333bfb21595e62dd73aac4a5c`. The previous image still carried 11 setuid/setgid utility files. They were already constrained by no-new-privileges/capability removal in the smoke configuration, but the HTTP service has no reason to retain those permission bits. The Dockerfile now strips them under `/usr` while preserving package contents, license notices and scanner visibility. This is defense in depth, not a vendor patch.

The checker now reads the actual service PID 1 UID/GID, all five capability sets and NoNewPrivs, inventories `/usr` without following symlinks, checks Debian aliases and empty fstab, and fails on incomplete inventory. It records relevant executable/module presence and mapped libraries. Against the old image it correctly failed on 11 setid utilities; named-container cleanup was confirmed afterward. Rebuilt image: no setid files found, PID 1 UID/GID 10001, capabilities zero, NoNewPrivs=1, health 200/503 and cleanup passed. Fourteen synthetic validation cases cover privileged identities, every capability set, missing evidence, inventory errors and scope mismatch; they are not containment probes. Total suite: 22 passed; Ruff passed.

All nine unique HIGH advisories were checked against the linked Debian tracker pages. None lists the installed trixie package as fixed. Each result and source is recorded in the [image receipt](evidence/control-image-scan-2026-11-04.json):

| Advisory | Current health-image assessment, not a deployed waiver |
| --- | --- |
| [CVE-2026-76642](https://security-tracker.debian.org/tracker/CVE-2026-76642) | Mount-helper hooks need privileges; no health mount path, capabilities, setid utilities or fstab entries |
| [CVE-2026-78408](https://security-tracker.debian.org/tracker/CVE-2026-78408) | nsenter exists; no privileged nsenter/cgroup operation or dispatcher |
| [CVE-2026-78409](https://security-tracker.debian.org/tracker/CVE-2026-78409) | Same mount restrictions; affected-version discrepancy remains open: Debian flags 2.41.5 while [upstream](https://github.com/util-linux/util-linux/security/advisories/GHSA-8f2p-47x3-43mv) says >=2.42. No not-affected claim |
| [CVE-2026-78410](https://security-tracker.debian.org/tracker/CVE-2026-78410) | Privileged restricted bind-mount prerequisite absent in checked configuration |
| [CVE-2026-54369](https://security-tracker.debian.org/tracker/CVE-2026-54369) | No privileged pathname ACL caller; libacl not in observed service maps |
| [CVE-2025-69720](https://security-tracker.debian.org/tracker/CVE-2025-69720) | infocmp is present; health never invokes it. A subprocess feature would require new review |
| [CVE-2026-119373](https://security-tracker.debian.org/tracker/CVE-2026-119373) | SQLite remains installed; health has no SQL path and library not mapped at observation |
| [CVE-2026-16742](https://security-tracker.debian.org/tracker/CVE-2026-16742) | systemd-derived libraries are flagged, but systemd-homed executable absent; does not assess the future VM host |
| [CVE-2026-9538](https://security-tracker.debian.org/tracker/CVE-2026-9538) | Perl-base present, Archive/Tar.pm absent from `/usr`; no archive/Perl application path |

Rescan of the rebuilt image retains **45 HIGH, 72 MEDIUM, 61 LOW, 7 UNKNOWN, zero CRITICAL** package/advisory findings; Python findings remain zero. No suppressions or package removals. The receipt now inventories all remaining unique advisory IDs by severity. Individual lower-severity review remains open; prioritize mapped libc/libgcc/libbz2/zlib before outbound DNS or broader input processing. Mapped libraries are not proof of exploitation, and absent mappings cannot establish future safety. No exploit code executed. Do not mix unstable libraries into stable Debian to manufacture a clean scan.

Separate Codex critical pass: checked the negative failure path and cleanup, source hashes, image identity, inventory scope, no package/notice deletion, and no security-policy relaxation. All mitigation claims are conditional on this health-only configuration; future API/worker/VM and deployed controls need fresh evidence. No independent human reviewer, production approval or Phase 1 acceptance is claimed.

### Billing follow-up: official evidence and operational decision

The [billing FAQ](https://docs.vultr.com/platform/billing/faq), updated October 23 and read with its tax answer expanded, says advertised prices exclude tax and taxes appear separately on invoices. The [account-limits guide](https://docs.vultr.com/platform/billing/manage-account-limits) describes maximum instance count/cost and requests to adjust those allocations. The [payment guide](https://docs.vultr.com/platform/billing/make-account-payments) warns about overdue bills; it does not establish credit-only enforcement. [Stopped-instance guidance](https://docs.vultr.com/support/platform/billing/are-stopped-instances-still-billed-on-vultr), updated October 26, requires destruction to stop VM billing. An in-guest shutdown or application request budget does not stop that charge.

The event still promises $200, service use during the event and payment-method setup for later continuation, without an explicit non-overage/tax-coverage clause. Prior authenticated balance/expiry evidence remains $200/December 4; this follow-up did not obtain a new account-specific coverage agreement. Decision: **retain provisioning and paid inference BLOCKED**. A sufficient unblock would be official account/event terms confirming eligible Compute/Inference/tax treatment and a provider-enforced non-overage bound, together with final quotes and project reservation limits. No personal-spending exception, card/deposit, resource creation, subscription, paid call or support message. This records an evidence gap, not a claim that charges inevitably occur or that the provider has no possible special arrangement. Do not repeat the same owner question or reread unchanged sources every run; resume billing when new account/event evidence arrives. Continue authorized independent foundation work.

### No-cloud worker component follow-up

Continued from clean local/remote `7d5153f1e2b60a17164054541b59bad8d1e489e4`. Added trusted bounded output collector and raw diagnostic buffer; see [sandbox implementation/evidence](sandbox.md#phase-1-local-collector-and-log-implementation--nov-4). **30 Windows tests passed, 24 Linux collector tests passed separately**; Ruff passed. Windows explicitly skips the Linux cases rather than pretending to validate Linux flags. Exact bytes/hash, shared bounds, special-file/device rejection before data I/O, replacement/late writes, redacted failures and descriptor cleanup are covered. No candidate code executed. The collector cannot establish writer termination, isolation or cleanup of a runtime that does not exist yet. Those deployed gates remain NOT RUN.

No dependency or control image change. Trusted image smoke was rerun to inspect bzip2recover presence: absent; health 200/503, privilege checks and named-container cleanup passed. Existing scanner counts remain historical evidence for that same immutable image, not a new clean scan. Six priority MEDIUM advisories were examined against Debian primary sources and recorded in the [scan receipt](evidence/control-image-scan-2026-11-04.json):

- [CVE-2026-6238](https://security-tracker.debian.org/tracker/CVE-2026-6238) and [CVE-2026-5435](https://security-tracker.debian.org/tracker/CVE-2026-5435) concern deprecated DNS printing/debugging functions, not ordinary resolver use. No such health application call identified; no blanket libc waiver.
- [CVE-2026-42250](https://security-tracker.debian.org/tracker/CVE-2026-42250) affects bzip2recover; that executable is absent. Loaded libbz2 alone does not establish this CLI path.
- [CVE-2026-102010](https://security-tracker.debian.org/tracker/CVE-2026-102010) concerns a libstdc++ heap operation. Mapped libgcc is not evidence of that operation; libstdc++ was absent from recorded service maps. Native dependency changes need re-review.
- [CVE-2026-27171](https://security-tracker.debian.org/tracker/CVE-2026-27171) affects CRC combine/gen64; no use in these modules identified. [CVE-2026-85091](https://security-tracker.debian.org/tracker/CVE-2026-85091) concerns nonblocking gz* writes; none identified. Debian/version-range discrepancy is retained, not used to exclude the finding.

The reviewed installed trixie packages remain listed as vulnerable; no vendor patch or suppression applied. Other lower-severity findings, unknowns and deployed review remain open. No future worker/pandas/provider safety is inferred. The separate critical pass in sandbox.md documents trusted procfs/local filesystem and stopped-writer prerequisites. No independent human review. Credit-only $150/$25 limits and billing block unchanged; no service activation, paid calls or repeated account question.

## Historical preparation record — 2026-10-24

Status on **2026-10-24 KST: READY FOR KICKOFF; Phase 1 not started**. Useful preparation is complete; external entry dependencies remain. This is not a passed Phase 1 or a deployed system. No cloud resource, subscription, inference request or candidate execution was created. The owner corrected the premature start instruction, authorized account/quote inspection only, and prohibited enabling any billable service now. At kickoff, Phase 1 still ends with a verified checkpoint and stop before Phase 2.

## Observed starting state and blockers

- Local branch `main`, clean; `git fetch --prune origin` succeeded. Local/tracking/remote HEAD was `be67be18e3d88d91b0b65bdb7d24aed3d268e127`. Remote is exactly `https://github.com/arslanabdulghaffar/ProofFlow.git`. Existing preparation/history preserved.
- Read AGENTS, resume/progress, requirements matrix, decisions/risks, product/contract/threat/rules and Phase 1 sandbox/inference/release/test plans. Phase 0's full PDF review remains in source-review.md. The PDF is engineering source material, not authority to cross user gates.
- **Timing, resolved:** trusted clock 2026-10-23 20:59:52 UTC / Oct 24 05:59:52 KST. The [official dashboard](https://lablab.ai/ai-hackathons/vultr-hackathon/live) opens Nov 3 15:00 UTC / Nov 4 00:00 KST and closes Nov 8 22:00 UTC / Nov 9 07:00 KST. The [sponsor](https://community.vultr.com/e/vultr-agent-rush-hackathon) also lists the future build. Owner confirms no early permission and says the earlier assertion was premature. Wait for kickoff; do not ask the timing question again.
- **Account, authenticated inspection:** owner signed in. Billing and the official `/billing/?promo=HACKATHON` route show identity verification through a linked payment method. The payment-form summary shows Total Available Credit $0.00 and an option to link a card with a $0 deposit. No redeemed event-credit ledger, expiry or covered-service terms were shown. This is not sufficient evidence of the account's final eligible balance, nor proof of ineligibility. No payment details were entered, card linked, code applied or terms accepted. Account limits, current subscription conditions and enrollment remain unverified.
- **Charges/caps:** public catalogue and authenticated unsubmitted compute previews inspected. No purchase attempted. Final fees, credit coverage, inference charges, bounded liability and provisioning approval remain unresolved. The $150/$25 authority remains conditional on verified eligible credits; the latest instruction prohibits billable activation now regardless of estimates.

## Concrete proposed resources

Use Seoul (`icn`), Ubuntu 24.04 LTS x86-64, on-demand AMD High Performance shared CPU. Both plans and Seoul/Ubuntu were selectable in the authenticated preview; deployment entitlement and future capacity remain unproven. No silent alternate region, paid resize or preemptible substitution. Worker sizing preserves headroom for two capped executions and runtime overhead; usable capacity remains subject to measurement.

| Role / plan ID | Specification in public catalogue | USD/hour | USD/month field |
| --- | --- | --- | --- |
| Control: `vhp-2c-4gb-amd` | 2 vCPU, 4096 MiB RAM, 100 GB local disk, 5120 GB transfer | 0.033 | 24 |
| Worker: `vhp-4c-8gb-amd` | 4 vCPU, 8192 MiB RAM, 180 GB local disk, 6144 GB transfer | 0.066 | 48 |
| Combined | Separate control and execution hosts | **0.099** | **72** |

Source: unauthenticated GET [Vultr public plans API](https://api.vultr.com/v2/plans?per_page=500), selected records saved with retrieval timestamp in [catalogue evidence](evidence/vultr-plans-2026-10-24.json). The receipt also includes regular-performance alternatives; they are not selected. Authenticated console preview uses IDs `vhp-2c-4gb` and `vhp-4c-8gb` (AMD disk/CPU in the displayed plan data, without the API's `-amd` suffix); freeze the accepted provisioning identifier at kickoff.

Authenticated preview at `https://console.vultr.com/deploy-beta/`: control $24/month, worker $48/month, both Seoul/Ubuntu 24.04 LTS/Public IPv4. Automatic backups defaulted ON ($4.80/$9.60 per month) and re-enabled after switching plans. They were turned OFF in the unsubmitted forms; DDoS was OFF, no paid extras selected. Final preview totals were $24/$48, displaying rounded $0.04/$0.07 hourly. The selection table displayed $0.036/$0.071 hourly while the configuration header displayed $0.033/$0.066. This discrepancy is preserved, not silently resolved. Use the larger rounded combined $0.11/hour for provisional estimates until the actual billing basis is confirmed: **$7.92 for 72 hours**, compute only. No Deploy click occurred. The preview did not include a configured VPC/firewall or tax/coverage confirmation; it is not yet a complete deployable quote. Browser returned to Billing afterward.

Arithmetic from API hourly fields alone: 24h = $2.376; 72h = $7.128; 127h = $12.573; 336h = $33.264, compute only. These are lower than the conservative console-based estimate above and are not adopted as billing truth. The API reports `invoice_type=monthly`; reconcile billing before treating any hourly estimate as the liability bound. [Billing documentation](https://docs.vultr.com/support/platform/billing/how-am-i-billed-for-my-servers) states a one-hour minimum, 672-hour monthly maximum for non-GPU servers, and continued charges for stopped resources.

No managed database, load balancer, paid backup, object storage, extra IP, extra disk, GPU or Marketplace image is in the initial probe proposal. PostgreSQL uses control-local storage. Private networking, base IPv4, firewall, transfer/tax and OS choices must be checked for charges in the final account quote. Temporary HTTPS uses an owner-controlled hostname if available; public release/anonymous intake remains separately gated. Phase 1 can expose only the approved health/test surface with operator access.

## Spending approval packet — incomplete, do not provision

| Item | Current value / required evidence |
| --- | --- |
| Authorized total / inference ceiling | $150 / $25 from owner; eligible credits only |
| Advertised event credit | $200 on public event page; not verified for owner |
| Actual redeemed credit balance, eligibility and expiry | NOT VERIFIED; authenticated payment summary $0.00, identity-verification step; no redeemed-event balance/terms shown |
| Service coverage / subscription minimum / renewal | UNKNOWN; verify compute, inference and later storage separately |
| Phase 1 usage plan | At most 72 hours initially; conservative compute estimate $7.92 plus at most $2 token probes, before unknown fees/minimums; this estimate is not an approved bill |
| Conservative project allocation | Compute $72 + inference $25 + later storage $18 + incidental/tax/transfer $10 + contingency $20 = $145; $5 unallocated |
| Enforced cap today | NONE; no service or spend mechanism exists yet |
| Out-of-pocket authorization | NONE; no card charge, deposit or uncovered liability authorized |
| Final provisioning approval | NOT AUTHORIZED NOW; owner explicitly says no provisioning/subscription/billable service. Revisit complete quote/terms at kickoff |

Account resource limits bound allocations; they are not evidence of a lifetime dollar cap. [Limits documentation](https://docs.vultr.com/platform/billing/manage-account-limits) describes instance counts and cost thresholds. [Stopping a VM does not stop billing](https://docs.vultr.com/support/platform/billing/are-stopped-instances-still-billed-on-vultr). A local budget ledger or alert cannot bound continued provider charges during a control-plane outage.

Before provisioning, record the actual start/end UTC, covered services, expiry, accrued costs, outstanding reservations, recurring minimums and taxes. Require evidence of provider-enforced non-overage/expiry or explicit owner approval of bounded residual out-of-pocket exposure. If neither exists, remain blocked. A termination plan needs named project-only resource IDs, preserved evidence and explicit disposal authorization; deletion is not implicitly authorized here. Do not claim a timer alone guarantees a hard cap or silently delete an active judging deployment. Do not schedule future monitoring without a request.

For inference, implement durable reservation before every network request; count retries and unknown timeout usage against both the $2 probe allocation and $25 aggregate. Select rates only after reconciling the live catalogue with the [older usage guide](https://docs.vultr.com/support/products/serverless/how-do-i-monitor-the-usage-and-cost-of-my-vultr-serverless-inference-subscription). New calls fail closed when billing is unknown or remaining balance cannot cover the conservative reservation. This mechanism is planned, not implemented.

## Owner account and secret setup

1. Login is complete. Remaining owner actions: confirm event/Discord enrollment; at kickoff obtain the official gift code and redeem only through the documented event flow. Resolve the account's payment-verification requirement using the [draft organizer questions](rules.md#draft-questions-for-the-owner-to-send-if-needed) before adding a payment method. No organizer message has been sent and no payment setup is requested now.
2. Establish the redeemed credit balance, expiry, covered services, inference minimums and post-credit payment behavior. Keep full account identifiers/payment information outside committed receipts; report only non-secret decision facts. A $0-deposit card option does not establish zero future liability.
3. At kickoff recheck these VM previews, disable the automatic backup default again, finish networking/fee details, and inspect the inference charge notice without subscribing. The [provisioning guide](https://docs.vultr.com/products/compute/serverless-inference/provisioning) requires charges acknowledgement. Complete the quote/liability packet before requesting actual spending approval; no question is pending now.
4. After timing and spending authorization: create a dedicated SSH key locally through a secure terminal; only its public key is registered. Verify host fingerprints through the console before SSH. Keep the private key outside Git and chat. Do not paste private-key material into cloud-init or command arguments.
5. After subscription authorization: place the inference key directly into a restricted controller file such as `/etc/proofflow/secrets/vultr-inference-key` through a secure interactive terminal or secret manager. The service receives only its path via `VULTR_INFERENCE_KEY_FILE`. No key in chat, shell history/arguments, Git, browser environment variables, screenshots, prompts, worker or candidate mounts. Confirm permissions and a redacted authentication outcome without printing contents.
6. Use separate controller/worker mTLS identities. The worker holds no inference/GitHub/cloud-admin credentials. A cloud provisioning API credential, if needed later, stays in the administrator environment; no broad key is needed just to inspect this public catalogue. No product GitHub App is required in Phase 1.

## Deployed acceptance sequence

Every row below is **NOT RUN**. Failed or uncertain critical results block candidate admission and Phase 1 completion. Record source commit, actual host/OS/runtime/image identities, UTC timestamps, bounded commands/configuration, expected vs observed outcome, exit/signal, actual resource counters, output hashes and cleanup state. Public receipts omit account identifiers, secrets and private host details. Keep raw restricted evidence outside Git; commit reviewed synthetic/redacted results and their hashes.

| Order / gate | Required evidence on the approved deployed path | Trace / acceptance |
| --- | --- | --- |
| 0 timing/account/caps | Current opening/permission, authenticated quote/coverage, final spend authority and enforceable limits | R06-01/02, R46-01/03/04; BLOCKED now |
| 1 trusted foundation | Locked dependencies; immutable image/runtime hashes; private DB and worker; operator HTTPS health; no exposed Docker socket; fail readiness if identity/config missing | R11-04/05, R14-01/02/04, R39-02/04 |
| 2 resource/runtime identity | Host evidence of explicit runsc/systrap; non-root/read-only/no capabilities; trusted Python/pandas fixed task; no secret mounts | R26-01/02/03, T07; guest-authored dmesg is insufficient |
| 3 independent limits | CPU saturation/throttling counters; memory allocation cap without host OOM; guest fork AND thread limits/hard-limit raise denied; output/scratch/shared-memory bytes and inodes exhausted safely | R26-05, R27-02, T07; host pids-limit is not guest task proof |
| 4 network/host separation | IPv4, IPv6, DNS, metadata, private controller/worker addresses and a controlled external listener denied; host-side positive control proves the test target is reachable outside guest; synthetic host marker inaccessible | R26-04, T07/T10; a dead target is not proof of containment |
| 5 timeout/output/cleanup | 20s independent watchdog kills descendants; all writers gone before collection; bounded survivor output retains benign bytes; no-follow regular-file collector rejects links/FIFOs/extras/oversize; bounded logs flagged; no container/process/mount/staging leak on normal exit, failure, timeout or controller disconnect | R26-06, R27-03/07, T07/T08/T15 |
| 6 real inference | Authenticated models and bounded real JSON/coding calls through Vultr; IDs/usage/rate/reservation/latency/schema recorded; generated code remains inert until gates 2–5 pass; then execute only on worker and check synthetic expected output independently | R14-05, R24-01–05; fake-provider tests labeled separately |
| 7 critical review/checkpoint | Review failures and residual risks; trusted install/build/secret checks; update all durable evidence/status; commit/push/readback; STOP before Phase 2 | Owner checkpoint policy; no independent human sign-off claimed |

Testing CPU, RAM, processes, writable storage or network in isolation does not replace the other gates. Re-run the fixed benign task and controller health after resource stress probes to establish recovery. Any guest-limit incompatibility, writer uncertainty, cleanup leak, cost uncertainty or provider failure is recorded explicitly; no fallback to plain Docker, fabricated result or feature expansion past it.

## Separate critical review of this preparation

Codex performed a distinct review pass; it is not independent human approval. Timing is resolved as wait-for-kickoff. Corrections: distinguished selectable catalogue plans from deployment entitlement; preserved conflicting rate displays; reserved $72 compute without claiming spend enforcement; noted automatic-backup default; required a network positive control; kept candidate execution behind all containment gates; made the Phase 1 stop instruction durable.

Contract/architecture cross-check found one business ambiguity: declared missing attribute on a filtered-out transaction (Q08). [Contract](contract.md#pre-freeze-ambiguity-found-in-preparation-review) records a plain example and recommended hold rule, unapproved until Phase 2 freeze. No new owner question is necessary for preparation or Phase 1. [Architecture](architecture.md) now explicitly requires cleanup success before approval/completion eligibility and applies global verifier/runtime invalidation to all affected pipelines. Duplicate representative links, conflicting groups, source occurrence accounting, immutable batch binding versus revocation, money wire formats and optional rollup collection were cross-checked without changing approved meaning. Schemas/hash vectors remain Phase 2 work. No runtime/security result is inferred; the human reviewer gap remains open.
