# Vultr inference plan

Public primary documentation checked 2026-10-24; **no authenticated inference/model/account probe was run**. No subscription was provisioned. Catalogue metadata is not account access, coding reliability, latency, billing confirmation or model selection.

| Probe candidate | Listed input/output USD per million tokens | Listed context; subscription limits | Decision |
| --- | --- | --- | --- |
| qwen3.8-27b | 0.15 / 1.00 | 256K; 120 requests/min, 16 concurrent | First coding/JSON candidate, untested |
| qwen3.8-flash-next | 0.10 / 0.20 | 256K; 120/min, 16 concurrent | Lower-cost comparison, untested |
| deepseek-v4.1-flash | 0.15 / 0.60 | Catalogue 1M context | Optional third only if first two fail within pilot reserve |

Sources: [catalogue](https://api.vultrinference.com/docs/models), [Qwen 27B](https://api.vultrinference.com/docs/models/qwen3.8-27b), [Flash Next](https://api.vultrinference.com/docs/models/qwen3.8-flash-next). Rate/model snapshots must be refreshed at kickoff. The older [usage article](https://docs.vultr.com/support/products/serverless/how-do-i-monitor-the-usage-and-cost-of-my-vultr-serverless-inference-subscription) gives general 0.55/2.75 rates. This conflict remains unresolved for the account. Do not choose the cheaper claim as billing truth.

The [chat reference](https://api.vultrinference.com/docs/reference/create-chat-completion) documents `response_format` text/json_object/json_schema, `max_completion_tokens` including reasoning, deprecated `max_tokens`, and usage with reasoning-token details. Model pages advertise response_format but must be probed. Use one completion, nonstreaming initially, low temperature, strict application validation, and explicit completion cap <=8192. Never double-count reasoning already included in completion_tokens. Reject length-truncated JSON and unsupported/unknown fields; no automatic continuation outside the same five-call budget. Do not assume a reasoning-specific cap is enforced without advertised support and a probe.

[Limits](https://api.vultrinference.com/docs/concepts/limits) are much looser than project limits. Keep project 60s request/300s job deadlines even if the service can queue longer. Honor Retry-After only if remaining time/reservation allows; <=2 transport retries and <=5 total calls including format retries. Unknown billing after timeout retains its full conservative reservation until reconciled. Missing usage is unknown, never zero. All response code remains inert data until sandbox dispatch.

## Kickoff probe sequence (Phase 1, NOT RUN)

1. Confirm timing, account/credit eligibility, applicable subscription charges, billable rates and non-out-of-pocket bounds. Secret files stay on the controller. Capture redacted account evidence; do not send credentials to chat.
2. Authenticated GET models; store bounded metadata and date; test two listed candidates still available to this account.
3. Tiny strict JSON probe (<=512 completion tokens); invalid/unsupported mode is recorded. A supported JSON mode still needs discriminated schema validation.
4. Small coding repair and wrong-join task using only development synthetic data (<=2048 then <=4096 completion tokens if necessary); proposed code executes only after sandbox gates pass.
5. Ambiguous-policy task must request clarification; record failures honestly. Exercise timeout/429/malformed JSON/missing usage through explicitly labeled fault injection and, when observed, real provider responses. Do not intentionally spam the service to induce 429.
6. Capture actual request/response IDs, model/settings/prompt hash, elapsed time and token counts. Record reserved cost, estimated cost, reconciled billing, schema validity, execution and independent check results. Select once using development evidence, then pin configuration before final evaluation.

Strict proposal variants: propose_patch contains diagnosis, changed_file exactly pipeline.py, full candidate_source <=16 KiB, expected_effect and uncertainties; needs_clarification contains nonempty questions and no executable source. Reject path edits, unknown keys and requests to change trusted rules. Syntax parse is bounded without imports; static checks do not provide containment. Store candidate bytes/hash and server diff before running. Only the trusted verifier can authorize pending approval.

Context includes fixed system/prompt version, approved requirements, source, bounded safe stderr/check failures and first-failure witness, short prior attempt summaries. Exclude keys, hidden oracle/seeds, unrelated workspaces, verifier source, approval tokens and unnecessary personal data. No arbitrary tools or endpoint override. Provider outage preserves truthful failure; an existing approved version can process batches without a model call, but no fallback provider or stored patch may masquerade as new inference.
