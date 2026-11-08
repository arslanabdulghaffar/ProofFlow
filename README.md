# ProofFlow

**Checked repairs before the next batch.** ProofFlow repairs supported Python revenue
imports using Vultr AI, executes each candidate in a fresh isolated worker, checks every
source occurrence, and requires exact-version approval before new batches.

Original project code is [MIT licensed](LICENSE). The owner authorized public release
on November 8, 2026. [Our hackathon entry](https://lablab.build/ai-hackathons/vultr-hackathon/neuralfoundry/proofflow-checked-repairs-before-the-next-batch) was submitted on November9 KST. Phases1–5 passed technical acceptance; delivery and remaining operational limits are tracked in [the release checklist](docs/release.md).

- [Live application](https://158.247.227.66:8443) — select synthetic-only consent, then
  **Start demo → Load synthetic example**. Each visitor gets a separate expiring guest
  workspace. No account, invitation or cloud credential is needed; capacity and budget limits apply.
- [Judge review guide](release/judges.md) — no login needed for the recording, slides or evidence.
- [Recorded demo, slides and cover](https://github.com/arslanabdulghaffar/ProofFlow/releases/tag/v0.1.0-hackathon)
  — use the narrated video and submission deck. The recording discloses editing and
  automated synthetic approvals; these do not constitute independent human review.
- [Setup and trust boundaries](release/setup.md), [measured comparison](eval/final-comparison-2026-11-06.md),
  [source-derived contract](docs/contract.md), [security limitations](docs/threat-model.md).

The narrow frozen benchmark repaired 15/18 cases with ProofFlow and 18/18 with the
fixed deterministic rebuild. We claim inspectable, approval-bound repairs, not AI
superiority or production certification. Full compromised-host recovery is unproven;
independent human review and offline key custody remain unavailable/deferred.

## Actual Vultr use

Vultr Compute hosts the private operator API, separate public guest API, trusted dispatcher,
PostgreSQL state/budget
and restricted deterministic verifier on the control VM. A separate Compute VM runs
untrusted code under gVisor with enforced network/resource/lifecycle limits. Application
agent proposals come only from Vultr Serverless Inference (`qwen3.8-flash-next` in the
recorded run). Only the dispatcher receives provider credentials. The verifier checks
collected bytes and never executes candidate source. See [architecture](docs/architecture.md),
[sandbox](docs/sandbox.md) and [setup for review](release/setup.md).

**Phases 1–5 passed private technical acceptance and their remote checkpoints are verified.** Real Vultr repair, isolated execution, independent deterministic checks, exact-version approval, fresh batches and one separately approved private draft PR have evidence. Phase5 adds security/recovery hardening and a frozen96-job comparison. The deterministic baseline repaired18/18 cases versus ProofFlow15/18; no beyond-normalizer or witness-quality superiority is claimed. Both VMs received the reviewed Critical kernel fix and passed16 fresh containment probes. Native advisory and independent human-review limitations remain. Phase6 submission and self-service judge access are verified; recovery and future-hosting limitations remain explicit. See [acceptance audit](docs/phase5-security-review.md), [measured comparison](eval/final-comparison-2026-11-06.md), [progress](docs/progress.md) and [resume instructions](docs/next-session.md).

The demonstrated workflow is intake → original execution → independent checks → bounded Vultr-generated repair → fresh sandbox → independent verification → exact approval → verified fresh batch. A separate operator approval permits a draft GitHub PR. Humans supply inputs and business decisions; they do not manually repair code or advance repair stages. Automated acceptance approvals are labeled test actions and are not independent human sign-off.

## Start here

- [Resume instructions](docs/next-session.md), [phase plan and work packages](docs/phase-plan.md), [environment readiness](docs/environment-readiness.md).
- [Product and UX](docs/product.md), [contract proposal](docs/contract.md), [architecture](docs/architecture.md), [threat model](docs/threat-model.md).
- [All-page requirements traceability](docs/requirements-traceability.md), [decisions](docs/decisions.md), [owner questions and risks](docs/risks.md).
- [Rules and implementation timing](docs/rules.md), [source review](docs/source-review.md), [external evidence](docs/external-evidence.md).
- [Test plan](docs/test-plan.md), [evaluation and budget](eval/plan.md), [demo](docs/demo.md), [release](docs/release.md).

## Proposed scope

One UTF-8 Python file, small transaction/customer CSVs, a declarative approved contract, and one pinned Python/pandas runtime. Money uses exact integer minor units. Implemented checks cover every source occurrence, merchant/customer ownership, values, currencies, timestamps, duplicates, justified exclusions, and declared downstream behavior. These rules are approved for synthetic demo data only; real customer policies are not approved.

Vanilla HTML/CSS/JavaScript with generated TypeScript wire types and FastAPI/Pydantic run on a Vultr control VM with PostgreSQL state/queue. A separate Linux worker uses explicit gVisor `runsc`. Application agent LLM calls use Vultr Serverless Inference.

No arbitrary repositories, package installation, candidate networking, live accounting writes, financial transfers, browser automation, enterprise SSO, large datasets, or certification claims. “Proof” means inspectable evidence for specified checks, not formal proof or universal correctness.

## Preparation check

With Python 3.12, run `python scripts/check_preparation.py` for documentation hygiene only.

On the configured owner computer, run `.venv/Scripts/python.exe scripts/check_operations.py`
for one read-only check of public TLS/liveness, services/storage, authenticated backup,
scheduled tasks and funding. It returns nonzero on an unavailable or unhealthy check.
`SCOPED_OK` is not release approval: public `/health/ready` remains503 while product
acceptance is incomplete. No guest, model call, restart, funding extension or new monitor
is created. [Operations guidance](docs/release.md#operational-signals-and-runbooks).

Trusted service development (uv 0.13.5):

```powershell
.\.venv-tools\Scripts\uv.exe sync --locked --no-build
.\.venv-tools\Scripts\uv.exe run --locked pytest -q
.\.venv-tools\Scripts\uv.exe run --locked ruff check api tests
.\.venv-tools\Scripts\uv.exe run --locked uvicorn api.app.main:app --host 127.0.0.1 --port 8000 --no-access-log --no-server-header --no-proxy-headers
```

The command above serves the trusted health shell, not the deployed product. Its readiness503 is not an end-to-end acceptance claim. The separate private product uses authenticated TLS over a Unix socket and pinned operator SSH forwarding, with no public provisioning. Worker RPC, runtime and provider evidence are documented in [sandbox](docs/sandbox.md) and phase acceptance receipts. Never execute uploaded/model source on the development or control computer; only the designated isolated worker may run it.

## Live demo walkthrough

Start a guest session and load the labeled synthetic example. Upload and review →
approve the exact contract → run original → inspect the ownership mismatch → request
repair → inspect the fresh checks → review/approve the exact version → run a fresh batch.
A guest cannot perform GitHub writes. Sessions last up to30 minutes; cleanup starts five
minutes early. See the [judge guide](release/judges.md).

The owner confirmed ownership and authorized MIT licensing, public release and hackathon submission on November8. Third-party dependencies retain their own licenses; see THIRD_PARTY_NOTICES.md. The supplied handoff PDF is not redistributed.
