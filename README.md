# ProofFlow

ProofFlow is a planned product for repairing supported Python revenue-import pipelines, checking their actual records against human-approved business rules, and using an exact approved version for subsequent batches.

**Current status: Phase 0 preparation only. Core functionality is not implemented.** There is no running application, verified repair, measured benchmark, deployed sandbox, or completed product integration. See [progress](docs/progress.md) for the checkpoint and checks actually performed.

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

With Python 3.12 or newer, run `python scripts/check_preparation.py`. This checks documentation coverage and repository hygiene; it does **not** test the product. Application install, health, sandbox, smoke, build and deployment commands will be implemented during the authorized event window. No placeholder command reports those checks as passing.

## Planned judge walkthrough

After a release is authorized: open the public demo, create a limited guest workspace, upload compatible unseen files or choose a labeled synthetic example, review the contract, run the job, inspect failures/diffs/receipts, approve the exact verified version, submit a fresh batch, and download its evidence. The operator separately demonstrates a draft PR with readback. This walkthrough is currently a specification.

The repository remains private. Publication, visibility changes and submission need a later explicit instruction. MIT is proposed for team-owned code; ownership and dependency/data attribution must be settled before issuing a license or publishing. The supplied handoff PDF is not redistributed here.
