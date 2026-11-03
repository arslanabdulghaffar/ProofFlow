# ProofFlow

ProofFlow is a planned product for repairing supported Python revenue-import pipelines, checking their actual records against human-approved business rules, and using an exact approved version for subsequent batches.

**Phase 1 IN PROGRESS; cloud spending gates remain blocked. Credits are activated.** The official event is live. A trusted local health service and locked Python dependencies now exist; readiness deliberately returns 503. There is no deployed application, real inference, verified repair, benchmark, sandbox or completed product integration. See [Phase 1 readiness](docs/phase1-readiness.md) for the inspected VM quote, setup steps and exact acceptance checklist, and [progress](docs/progress.md) for checks actually performed.

The intended workflow is intake → original execution → independent checks → bounded Vultr-generated repair → fresh sandbox → independent verification → human approval → verified fresh batch. A separate operator approval permits an actual draft GitHub PR. Humans supply inputs and business decisions; they do not manually repair code or advance repair stages.

## Start here

- [Resume instructions](docs/next-session.md), [phase plan and work packages](docs/phase-plan.md), [environment readiness](docs/environment-readiness.md).
- [Product and UX](docs/product.md), [contract proposal](docs/contract.md), [architecture](docs/architecture.md), [threat model](docs/threat-model.md).
- [All-page requirements traceability](docs/requirements-traceability.md), [decisions](docs/decisions.md), [owner questions and risks](docs/risks.md).
- [Rules and implementation timing](docs/rules.md), [source review](docs/source-review.md), [external evidence](docs/external-evidence.md).
- [Test plan](docs/test-plan.md), [evaluation and budget](eval/plan.md), [demo](docs/demo.md), [release](docs/release.md).

## Proposed scope

One UTF-8 Python file, small transaction/customer CSVs, a declarative approved contract, and one pinned Python/pandas runtime. Money uses exact integer minor units. Independent checks cover every source occurrence, merchant/customer ownership, values, currencies, timestamps, duplicates, justified exclusions, and declared downstream behavior. The owner approved the narrow duplicate/downstream policy for synthetic demo data only; it is not an implemented capability or approval of real customer policies.

Next.js/React/TypeScript and FastAPI/Pydantic run on a Vultr control VM with PostgreSQL state/queue. A separate Linux worker uses explicit gVisor `runsc`. Application agent LLM calls use Vultr Serverless Inference. Development tools such as Codex are separate from this runtime provider requirement.

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

`GET /health/live` returns 200 for process liveness. `GET /health/ready` returns 503 until actual infrastructure checks are implemented and pass. No public upload, execution or approval API exists. The private authenticated worker RPC and immutable image import have local trusted tests; see [sandbox](docs/sandbox.md). Never run a submitted/model candidate here. Local checks do not establish deployed containment or provider success.

## Planned judge walkthrough

After a release is authorized: open the public demo, create a limited guest workspace, upload compatible unseen files or choose a labeled synthetic example, review the contract, run the job, inspect failures/diffs/receipts, approve the exact verified version, submit a fresh batch, and download its evidence. The operator separately demonstrates a draft PR with readback. This walkthrough is currently a specification.

The repository remains private. Publication, visibility changes and submission need a later explicit instruction. MIT is proposed for team-owned code; ownership and dependency/data attribution must be settled before issuing a license or publishing. The supplied handoff PDF is not redistributed here.
