# External evidence register

Verification date for this Phase 0 review: **2026-10-24, Asia/Seoul**. Public primary documentation was consulted; account-specific access/terms/billing and deployed behavior were not tested. A successful page read is not a successful integration. Recheck temporal facts at kickoff and before release. Source index below retains every PDF reference; context-only references have not been independently revalidated here.

| Topic | Primary evidence | Finding / limit |
| --- | --- | --- |
| Event and timing | [Event](https://lablab.ai/ai-hackathons/vultr-hackathon), [dashboard](https://lablab.ai/ai-hackathons/vultr-hackathon/live), [sponsor](https://community.vultr.com/e/vultr-agent-rush-hackathon) | Track 1 requirements and Nov 3–8 window confirmed; opening 15:00 UTC vs sponsor session16:00; no early-core permission located |
| Pre-existing work | [General guide](https://lablab.ai/guide/ai-hackathons) | General event-window core expectation; explicit event clarification still controls |
| Submission | [Tutorial](https://lablab.ai/ai-articles/hackathon-guidelines) | Public guidance available; authenticated event form/owner registration NOT CHECKED |
| Inference subscription | [Provisioning](https://docs.vultr.com/products/compute/serverless-inference/provisioning) | Subscription creation requires charges acknowledgement; no account subscription or eligibility established |
| Models/rates | [Live docs catalogue](https://api.vultrinference.com/docs/models), [27B](https://api.vultrinference.com/docs/models/qwen3.8-27b), [Flash Next](https://api.vultrinference.com/docs/models/qwen3.8-flash-next) | IDs/rates/capabilities listed in inference.md; authenticated availability and coding latency NOT RUN |
| Response parameters/usage | [Chat reference](https://api.vultrinference.com/docs/reference/create-chat-completion), [limits](https://api.vultrinference.com/docs/concepts/limits) | JSON modes and completion/reasoning usage documented; project caps tighter; enforce/verify per model |
| Pricing conflict | [Older usage guide](https://docs.vultr.com/support/products/serverless/how-do-i-monitor-the-usage-and-cost-of-my-vultr-serverless-inference-subscription) | General rates differ from catalogue; actual account charge and subscription minimum unknown |
| VM platform | [gVisor platforms](https://gvisor.dev/docs/architecture_guide/platforms/) | systrap is recommended for VM use; selected Vultr compatibility remains untested |
| Runtime identity | [gVisor Docker](https://gvisor.dev/docs/user_guide/quick_start/docker/) | Explicit runsc registration/selection; guest dmesg is forgeable, insufficient security identity |
| Resource model | [gVisor resources](https://gvisor.dev/docs/architecture_guide/resources/), [Docker constraints](https://docs.docker.com/engine/containers/resource_constraints/) | Guest processes/threads differ from host processes; host PID cap alone cannot prove guest limit. Separate probes required |
| Security/upload | [gVisor security](https://gvisor.dev/docs/architecture_guide/security/), [OWASP uploads](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html) | Isolation has residual risks; bounded allowlisted parsing/storage needed. No security tests performed |
| Durable queue | [PostgreSQL18 SELECT](https://www.postgresql.org/docs/18/sql-select.html) | SKIP LOCKED supports queue-like contention avoidance but not general consistent views; fencing/side-effect protocol is our design |
| GitHub draft/readback | [PR API](https://docs.github.com/en/rest/pulls/pulls), [Git refs](https://docs.github.com/en/rest/git/refs) | Draft flag and reference APIs exist. Installed App permissions/actual product write remain untested |
| Signed deliveries | [GitHub webhook validation](https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries) | HMAC raw-byte and constant-time comparison guidance; ProofFlow freshness/event headers are our own protocol |
| Object storage cost | [Vultr billing](https://docs.vultr.com/support/platform/billing/how-is-object-storage-billed) | Standard tier listed 18 USD/month; revise the PDF's10 USD allowance. Proration/credit coverage/account charges remain unknown |
| Backup compatibility | [Vultr matrix](https://docs.vultr.com/products/storage/object-storage/s3-compatibility-matrix), [restic S3 setup](https://restic.readthedocs.io/en/stable/030_preparing_a_new_repo.html) | Generic S3-compatible setup is documented; actual endpoint backup/restore/prune/locking NOT RUN |
| Toolchain | [Node releases](https://nodejs.org/en/about/previous-releases), [Node distribution](https://nodejs.org/dist/v24.22.1/), [uv installation](https://docs.astral.sh/uv/getting-started/installation/) | Node 24 LTS and isolated PyPI uv tooling used; local archive/wheel hashes and checks in environment-readiness.md |
| Prior art | [Datafold](https://docs.datafold.com/data-migration-automation/datafold-migration-agent), [ADP-MA abstract](https://arxiv.org/abs/2602.00307), [AegisFlow abstract](https://arxiv.org/abs/2610.06971), [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent) | Overlap exists; paper/vendor performance claims not reproduced. Full-paper technical review and baseline revision pin deferred before any detailed comparative claim |

Local authenticated GitHub identity/read/advertised write facts are recorded separately from these public sources. Repository ruleset enumeration returned403; no protection bypass or absence-of-protection claim. No cloud API, inference POST, product PR write, payment, organizer message, public release or submission was performed.

## Complete PDF source index

Index entries below record reference provenance, not endorsement, implementation or completed tests. “Public recheck” means relevant public material consulted on 2026-10-24 with the limitations above; “context only” means read in the PDF but not revalidated externally this session.

| ID | PDF page | Source | Review status |
| --- | --- | --- | --- |
| S01 | 56 | [lablab.ai - Agent Rush event](https://lablab.ai/ai-hackathons/vultr-hackathon) | Public recheck; see limits above |
| S02 | 56 | [lablab.ai - live dashboard](https://lablab.ai/ai-hackathons/vultr-hackathon/live) | Public recheck; see limits above |
| S03 | 56 | [Vultr - official event listing](https://community.vultr.com/e/vultr-agent-rush-hackathon) | Public recheck; see limits above |
| S04 | 56 | [lablab.ai - participation guide](https://lablab.ai/guide) | Context only; external recheck deferred |
| S05 | 56 | [lablab.ai - submission tutorial](https://lablab.ai/ai-articles/hackathon-guidelines) | Public recheck; see limits above |
| S06 | 56 | [lablab.ai - AI hackathons guide](https://lablab.ai/guide/ai-hackathons) | Public recheck; see limits above |
| S07 | 56 | [Vultr - inference provisioning](https://docs.vultr.com/products/compute/serverless-inference/provisioning) | Public recheck; see limits above |
| S08 | 56 | [Vultr - live model catalogue](https://api.vultrinference.com/v1/models) | Public model docs rechecked; authenticated catalogue NOT RUN |
| S09 | 56 | [Vultr - inference usage and cost](https://docs.vultr.com/support/products/serverless/how-do-i-monitor-the-usage-and-cost-of-my-vultr-serverless-inference-subscription) | Public recheck; see limits above |
| S10 | 56 | [gVisor - Docker quick start](https://gvisor.dev/docs/user_guide/quick_start/docker/) | Public recheck; see limits above |
| S11 | 57 | [gVisor - security model](https://gvisor.dev/docs/architecture_guide/security/) | Public recheck; see limits above |
| S12 | 57 | [Docker - Engine security](https://docs.docker.com/engine/security/) | Context only; external recheck deferred |
| S13 | 57 | [OWASP - file upload cheat sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html) | Public recheck; see limits above |
| S14 | 57 | [Datafold - Migration Agent](https://docs.datafold.com/data-migration-automation/datafold-migration-agent) | Public recheck; see limits above |
| S15 | 57 | [Soda - quickstart](https://docs.soda.io/quickstart) | Context only; external recheck deferred |
| S16 | 57 | [Khurana - ADP-MA](https://arxiv.org/abs/2602.00307) | Public recheck; see limits above |
| S17 | 57 | [Awan et al. - AegisFlow](https://arxiv.org/abs/2610.06971) | Public recheck; see limits above |
| S18 | 57 | [SWE-agent - mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent) | Public recheck; see limits above |
| S19 | 57 | [OpenHands - project website](https://www.openhands.dev/) | Context only; external recheck deferred |
| S20 | 57 | [AgentDojo paper](https://arxiv.org/abs/2406.13352) | Context only; external recheck deferred |
| S21 | 58 | [tau-bench paper](https://arxiv.org/abs/2406.12045) | Context only; external recheck deferred |
| S22 | 58 | [Vultr - Agent Arena winners](https://blogs.vultr.com/agent-arena-hackathon-cerebral-valley-2026) | Context only; external recheck deferred |
| S23 | 58 | [Nusa repository](https://github.com/a8nova/nusa) | Context only; external recheck deferred |
| S24 | 58 | [Skeleton Key repository](https://github.com/Carldtitan/skeleton_key) | Context only; external recheck deferred |
| S25 | 58 | [GitHub - pull requests API](https://docs.github.com/en/rest/pulls/pulls) | Public recheck; see limits above |
| S26 | 58 | [GitHub - Git references API](https://docs.github.com/en/rest/git/refs) | Public recheck; see limits above |
| S27 | 58 | [GitHub - webhook signature validation](https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries) | Public recheck; see limits above |
| S28 | 58 | [PostgreSQL - SELECT and locking](https://www.postgresql.org/docs/current/sql-select.html) | Public recheck; see limits above |
| S29 | 58 | [Ramp - accounts payable](https://ramp.com/accounts-payable) | Context only; external recheck deferred |
| S30 | 58 | [Vic.ai - PO matching overview](https://help.vic.ai/en/articles/8148444-po-matching-overview) | Context only; external recheck deferred |
| S31 | 59 | [Didero - PO management](https://www.didero.ai/agentic-systems/po-management) | Context only; external recheck deferred |
| S32 | 59 | [FiftyOne - agents documentation](https://docs.voxel51.com/agents/index.html) | Context only; external recheck deferred |
| S33 | 59 | [Atlas - AI-safe migrations](https://atlasgo.io/use-cases/ai-safe-migrations) | Context only; external recheck deferred |
| S34 | 59 | [pgroll repository](https://github.com/xataio/pgroll) | Context only; external recheck deferred |
| S35 | 59 | [Deque - axe MCP server](https://docs.deque.com/devtools-server/4.0.0/en/axe-mcp-server/) | Context only; external recheck deferred |
| S36 | 59 | [Playwright - test agents](https://github.com/microsoft/playwright/blob/main/docs/src/test-agents-js.md) | Context only; external recheck deferred |
| S37 | 59 | [OWASP - LLM prompt injection](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html) | Context only; external recheck deferred |
| S38 | 59 | [Vultr - agent sandboxing guide](https://docs.vultr.com/how-to-set-up-agent-sandboxing-on-vultr-cloud-compute) | Context only; external recheck deferred |
| S39 | 59 | [Hypothesis - documentation](https://hypothesis.readthedocs.io/en/latest/) | Context only; external recheck deferred |
| S40 | 59 | [lablab.ai - winning guide](https://lablab.ai/guide/how-to-win-an-ai-hackathon) | Context only; external recheck deferred |
| S41 | 59 | [Vultr - S3 compatibility matrix](https://docs.vultr.com/products/storage/object-storage/s3-compatibility-matrix) | Public recheck; see limits above |
| S42 | 59 | [restic - repository setup](https://restic.readthedocs.io/en/stable/030_preparing_a_new_repo.html) | Public recheck; see limits above |
