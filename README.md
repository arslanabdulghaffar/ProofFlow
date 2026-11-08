# ProofFlow

**Current status — November8:** the [public guest demo](https://158.247.227.66:8443)
has trusted TLS and accepted invited-guest workflows. Each guest window is individually
provisioned and limited to30 minutes; there is no anonymous signup or shared judge password.
The repository and release media remain private. Phase6 recovery/release work is ongoing;
full compromised-host recovery and publication/submission are not complete.
See [guest acceptance](docs/evidence/phase6-guest-operation-2026-11-08.json) and the
[release gate checklist](docs/release.md#stopgo-inventory-mapped-to-pdf-p53).

ProofFlow is a private prototype for repairing supported Python revenue-import pipelines, checking their actual records against human-approved business rules, and using an exact approved version for subsequent batches.

**Current Phase6 review materials:** an eight-slide editable deck, standalone cover,
139.04s real-AI demo and verified private release ZIP are prepared. See the
[package guide](release/README.md), [draft submission copy](release/submission-copy.md)
and [exact asset hashes](release/assets.json). The application URL is live; public
repository/video/slides and submission confirmation remain unavailable. The private v5
archive is a dated snapshot, not automatically rebuilt for later operational tools.
The owner deferred offline key custody. Phases0–5 are complete at verified checkpoints.

## Actual Vultr use

Vultr Compute hosts the private operator API, separate public guest API, trusted dispatcher,
PostgreSQL state/budget
and restricted deterministic verifier on the control VM. A separate Compute VM runs
untrusted code under gVisor with enforced network/resource/lifecycle limits. Application
agent proposals come only from Vultr Serverless Inference (`qwen3.8-flash-next` in the
recorded run). Only the dispatcher receives provider credentials. The verifier checks
collected bytes and never executes candidate source. See [architecture](docs/architecture.md),
[sandbox](docs/sandbox.md) and [setup for review](release/setup.md).

**Phases 1–5 passed private technical acceptance and their remote checkpoints are verified.** Real Vultr repair, isolated execution, independent deterministic checks, exact-version approval, fresh batches and one separately approved private draft PR have evidence. Phase5 adds security/recovery hardening and a frozen96-job comparison. The deterministic baseline repaired18/18 cases versus ProofFlow15/18; no beyond-normalizer or witness-quality superiority is claimed. Both VMs received the reviewed Critical kernel fix and passed16 fresh containment probes. Native advisory and independent human-review limitations remain. Public demo/release work is Phase6 and is not complete. See [acceptance audit](docs/phase5-security-review.md), [measured comparison](eval/final-comparison-2026-11-06.md), [progress](docs/progress.md) and [resume instructions](docs/next-session.md).

The demonstrated workflow is intake → original execution → independent checks → bounded Vultr-generated repair → fresh sandbox → independent verification → exact approval → verified fresh batch. A separate operator approval permits a draft GitHub PR. Humans supply inputs and business decisions; they do not manually repair code or advance repair stages. Automated acceptance approvals are labeled test actions and are not independent human sign-off.

## Start here

- [Resume instructions](docs/next-session.md), [phase plan and work packages](docs/phase-plan.md), [environment readiness](docs/environment-readiness.md).
- [Product and UX](docs/product.md), [contract proposal](docs/contract.md), [architecture](docs/architecture.md), [threat model](docs/threat-model.md).
- [All-page requirements traceability](docs/requirements-traceability.md), [decisions](docs/decisions.md), [owner questions and risks](docs/risks.md).
- [Rules and implementation timing](docs/rules.md), [source review](docs/source-review.md), [external evidence](docs/external-evidence.md).
- [Test plan](docs/test-plan.md), [evaluation and budget](eval/plan.md), [demo](docs/demo.md), [release](docs/release.md).

## Proposed scope

One UTF-8 Python file, small transaction/customer CSVs, a declarative approved contract, and one pinned Python/pandas runtime. Money uses exact integer minor units. Implemented checks cover every source occurrence, merchant/customer ownership, values, currencies, timestamps, duplicates, justified exclusions, and declared downstream behavior. These rules are approved for synthetic demo data only; real customer policies are not approved.

Vanilla HTML/CSS/JavaScript with generated TypeScript wire types and FastAPI/Pydantic run on a Vultr control VM with PostgreSQL state/queue. A separate Linux worker uses explicit gVisor `runsc`. Application agent LLM calls use Vultr Serverless Inference. Development tools such as Codex are separate from this runtime provider requirement.

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

## Invited demo walkthrough

An individually invited guest can upload compatible synthetic files, review the contract,
run the job, inspect failures/diffs/receipts, approve the exact verified version, submit a
fresh batch and download evidence. The owner launcher stages files but never uploads or
approves automatically. The separately approved private PR has recorded readback; another
PR still needs its own exact approval. Judges have not been issued shared access by this
repository. See [owner setup](release/setup.md) for the bounded guest launcher.

The repository remains private. Publication, visibility changes and submission need a later explicit instruction. MIT is proposed for team-owned code; ownership and dependency/data attribution must be settled before issuing a license or publishing. The supplied handoff PDF is not redistributed here.
