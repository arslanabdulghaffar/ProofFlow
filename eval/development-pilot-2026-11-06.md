# Development model pilot — November6 KST

Twelve real jobs used Vultr qwen3.8-flash-next, the designated isolated worker and the protected verifier. The four cases were disclosed development examples: units, composite join, downstream repair and downstream source ambiguity. This is one run per case/arm, not held-out testing or a quality ranking.

| Arm | Repairable correct | Ambiguous correctly held | Incorrect acceptances | Model calls | Median job time |
| --- | --- | --- | --- | --- | --- |
| A: production repair core with witness feedback | 3/3 | 1/1 | 0/3 accepted | 4 | 16.43s |
| B: execution-only acceptance | 3/3 | 0/1 | 1/4 accepted | 5 | 16.01s |
| C: verifier verdict without witness rows | 3/3 | 1/1 | 0/3 accepted | 6 | 17.71s |
| D: deterministic rebuild | NOT RUN | NOT RUN | Undefined | 0 | NOT RUN |

B's acceptance was fixed before protected grading. A/C use the production prompt, verifier and canary functions, but this harness bypasses API/queue/approval UX and is not the complete product benchmark. All observed worker cleanup was confirmed. The downstream ambiguity tests an approved source-validation hold, not an unanswered business-policy question. No model asked for clarification; clarification quality and human oracle review remain unmeasured. Witness benefits cannot be inferred from one small exposed sample where A and C tie on outcomes.

All arms shared the model, contract/source/interface, three-call ceiling,8192 completion-token bound and$0.10/job reservation cap. Launch job IDs, mounted sources and case hashes were fixed before calls; arm order was hash-interleaved. The reporting manifest was assembled afterward and is explicitly accounting, not retrospective preregistration. D is displayed as NOT RUN by the accounting tool; prior positive-control executions are not relabeled D.

Fifteen actual immutable PostgreSQL provider receipts reconcile IDs, request models, response hashes, usage and conservative reservations. Token-usage estimate is$0.011443; call reservations$0.417795 remain held, not invoiced or settled. Full$1.20 pilot allowance now persists within the unchanged$5 development allocation (shared total$1.311412). This shared persistence was corrected after the run; initial launch checked available allocation with product admission closed and enforced local/global caps before calls. Future launch reserves shared allowance before any call. No personal spending/new resource was authorized or used.

The observed range8.83–27.71s describes12 jobs only, not a load-test tail estimate. Low mean token cost does not justify reducing worst-case reservation below the admitted-call bound. Final evaluation still needs genuinely separate frozen cases, all four documented arms, dedicated bounded durable storage, fresh rates and honest denominators. [Source-bound receipts and accounting](../docs/evidence/phase5-model-pilot-retention-2026-11-06.json).
