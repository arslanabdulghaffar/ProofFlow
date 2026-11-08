# Contributing

This repository contains the ProofFlow application, tests and reproducible engineering
evidence. Original project code is MIT-licensed. Read AGENTS.md, the contract and threat
model before changing runtime or approval boundaries. Use focused branches and preserve
existing work and history.

Each change identifies behavior, requirement IDs, acceptance evidence, risk, recovery, and remaining limits. Use READY, IN_PROGRESS, BLOCKED, REVIEW and DONE for tasks. Untested work stays REVIEW; phase DONE also requires the verified remote checkpoint.

Contract/verifier/runtime/permission/approval/schema changes receive automated checks and a separate critical review pass. A second human reviewer remains desired by the handoff but unconfirmed; the owner authorizes development to continue with this gap disclosed. Never call those checks independent human approval. The owner approved the duplicate/downstream policy for synthetic demo data on 2026-10-24; detailed examples and remaining material decisions are in the contract.

Use synthetic or licensed data and record provenance. Do not commit the source handoff PDF, extracted pages, credentials, `.env`, virtual environments, cloud dumps or runtime logs. Review additions before staging explicit paths. Pin trusted dependencies and images during Phase 1; review provenance, licenses and reachable vulnerabilities.

Before a checkpoint run the appropriate checks, `git diff --check`, the preparation checker while applicable, and a secret review. Record unavailable checks honestly. Use the phase-specific commit/push/readback sequence in AGENTS.md. No force pushes or protection bypasses.
