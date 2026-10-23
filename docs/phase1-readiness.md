# Phase 1 entry and deployment proposal

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
