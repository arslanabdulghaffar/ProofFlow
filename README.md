# ProofFlow

ProofFlow is a private prototype for repairing supported Python revenue-import pipelines, checking their actual records against human-approved business rules, and using an exact approved version for subsequent batches.

**Current Phase6 review materials:** an eight-slide editable deck, standalone cover,
139.04s real-AI demo and private release-package sources are prepared. See the
[package guide](release/README.md), [draft submission copy](release/submission-copy.md)
and [exact asset hashes](release/assets.json). Public URLs remain unset; no release or
submission has occurred. The owner deferred offline key custody. Phases0–5 are complete
at their verified private checkpoints; Phase6 still has public/disaster-recovery gates.

## Actual Vultr use

Vultr Compute hosts the private web API, trusted dispatcher, PostgreSQL state/budget
and restricted deterministic verifier on the control VM. A separate Compute VM runs
untrusted code under gVisor with enforced network/resource/lifecycle limits. Application
agent proposals come only from Vultr Serverless Inference (`qwen3.8-flash-next` in the
recorded run). Only the dispatcher receives provider credentials. The verifier checks
collected bytes and never executes candidate source. See [architecture](docs/architecture.md),
[sandbox](docs/sandbox.md) and [setup for review](release/setup.md).

**Phases 1–5 passed private technical acceptance and their remote checkpoints are verified.** Real Vultr repair, isolated execution, independent deterministic checks, exact-version approval, fresh batches and one separately approved private draft PR have evidence. Phase5 adds security/recovery hardening and a frozen96-job comparison. The deterministic baseline repaired18/18 cases versus ProofFlow15/18; no beyond-normalizer or witness-quality superiority is claimed. Both VMs received the reviewed Critical kernel fix and passed16 fresh containment probes. Native advisory and independent human-review limitations remain. Public demo/release work is Phase6 and is not complete. See [acceptance audit](docs/phase5-security-review.md), [measured comparison](eval/final-comparison-2026-11-06.md), [progress](docs/progress.md) and [resume instructions](docs/next-session.md).

The intended workflow is intake → original execution → independent checks → bounded Vultr-generated repair → fresh sandbox → independent verification → human approval → verified fresh batch. A separate operator approval permits an actual draft GitHub PR. Humans supply inputs and business decisions; they do not manually repair code or advance repair stages.

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

Trusted service development (uv 0.13.5):

```powershell
.\.venv-tools\Scripts\uv.exe sync --locked --no-build
.\.venv-tools\Scripts\uv.exe run --locked pytest -q
.\.venv-tools\Scripts\uv.exe run --locked ruff check api tests
.\.venv-tools\Scripts\uv.exe run --locked uvicorn api.app.main:app --host 127.0.0.1 --port 8000 --no-access-log --no-server-header --no-proxy-headers
```

The command above serves the trusted health shell, not the deployed product. Its readiness503 is not an end-to-end acceptance claim. The separate private product uses authenticated TLS over a Unix socket and pinned operator SSH forwarding, with no public provisioning. Worker RPC, runtime and provider evidence are documented in [sandbox](docs/sandbox.md) and phase acceptance receipts. Never execute uploaded/model source on the development or control computer; only the designated isolated worker may run it.

## Planned judge walkthrough

After a release is authorized: open the public demo, create a limited guest workspace, upload compatible unseen files or choose a labeled synthetic example, review the contract, run the job, inspect failures/diffs/receipts, approve the exact verified version, submit a fresh batch, and download its evidence. The operator separately demonstrates a draft PR with readback. This walkthrough is currently a specification.

The repository remains private. Publication, visibility changes and submission need a later explicit instruction. MIT is proposed for team-owned code; ownership and dependency/data attribution must be settled before issuing a license or publishing. The supplied handoff PDF is not redistributed here.
