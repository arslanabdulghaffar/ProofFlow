# ProofFlow

Owner-approved public release copy. Original code is MIT licensed; submission is pending.
Final form limits, enrollment and absolute closing time have not been verified in the
authenticated submission form. `submission.json` deliberately leaves public URLs blank.

## Short description

Repair merchant revenue imports with Vultr AI, check every source record, and approve
exact code before the next batch.

## Project description

A revenue import can finish successfully while assigning transactions to the wrong
merchant or customer. ProofFlow is a private prototype for operations engineers who
maintain small Python revenue imports. It proposes repairs and produces inspectable
record-level evidence before repaired code can process another batch.

The operator supplies Python, transaction/customer CSVs and a declarative contract.
After exact contract approval, the original executes on an isolated Vultr worker.
An independent deterministic verifier checks actual output against source-derived
expectations, including ownership, integer monetary values, duplicates and permitted
exclusions. Conflicting or incomplete source data holds the batch.

For a repairable mismatch, Vultr Serverless Inference proposes changed code. Each
candidate runs in a fresh gVisor sandbox with resource limits, denied network access
and no secrets. Protected checks and confirmed cleanup determine review eligibility.
Passing checks does not activate code: the exact source, contract, runtime and evidence
must be approved before a different batch executes and is checked again. GitHub draft
PR actions have a separate concrete approval and readback path.

The November8 recording shows one real Vultr call, changed source, three fresh matching
checks, evidence download, exact automated synthetic approval and a completed new batch.
A separate deliberate infinite loop is killed; worker receipts confirm cleanup and no
accepted output. The video labels its edits, paused frames and batch receipt summary.
Two recording-script errors remain preserved and reconciled; they were not hidden by
changing product states or rerunning paid repairs.

In the frozen synthetic comparison, full ProofFlow repaired15/18 cases and had0/15
incorrect acceptances. A success-only acceptance baseline had9/23 incorrect acceptances.
The fixed deterministic rebuild repaired18/18 and performed best on this narrow contract.
One repeat, shared templates and no independent human oracle review limit generalization;
we do not claim AI superiority, universal correctness or measured customer savings.

The implemented backend and private web app run on Vultr Compute. Vultr Serverless
Inference supplies application-agent proposals; a separate Compute worker executes
untrusted source. PostgreSQL preserves jobs, budgets, approvals and durable intents.
The verifier never runs candidate code. The owner is the only confirmed human contributor,
with Codex assisting engineering. Invited public guest TLS and external tests passed;
ownership/license clearance, independent human review and full disaster recovery remain open.

## Supporting evidence

- Real recorded run and edit disclosure: `docs/demo.md` and the Phase6 evidence JSON.
- Frozen denominators, failed attempts and costs: `eval/final-comparison-2026-11-06.md`.
- Vultr services and boundaries: root README, `docs/architecture.md` and `docs/sandbox.md`.
- Operational restrictions and recovery gaps: `docs/release.md` and `docs/risks.md`.

## Claims to retain when adapting this copy

“Independent verification” means separate trusted deterministic code; it does not mean
independent human review. This demo uses synthetic rules/data. The $0.027853 demo figure
is a reservation, not an invoice. A public-demo URL must refer to a real authorized
deployment; the operator's localhost SSH tunnel is not a public application URL.
