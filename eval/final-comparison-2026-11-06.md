# Final synthetic comparison — November 6, 2026

All 96 predeclared jobs are accounted for. Private live receipts were collected and reconciled after the campaign ended at 14:26:18 UTC / 23:26:18 KST. This completes the planned one-repeat comparison, **not all of Phase 5 or public-release acceptance**. The reproducible [artifact](final-comparison-2026-11-06.json) contains the 24 synthetic cases, source-derived oracles, frozen plan, all run records and accounting. Candidate programs in that artifact are inert text and must execute only on the designated isolated worker.

| Approach | Correct repairs / 18 | Correct holds or clarification / 6 | Incorrect accepted / all accepted | Confirmed model calls |
| --- | ---: | ---: | ---: | ---: |
| A: full ProofFlow API workflow | 15/18 | 6/6 | 0/15 | 23 |
| B: accept a successful collected run, then independently grade it | 14/18 | 1/6 | 9/23 | 26 |
| C: repair core with verdict codes, without witness rows | 15/18 | 6/6 | 0/15 | 30 |
| D: fixed deterministic rebuild for this contract | 18/18 | 6/6 | 0/18 | 0 |

A and C have equal observed repair coverage. This experiment does not establish a witness-feedback quality advantage. D performs best within this deliberately narrow supported contract; it reuses the positive template from which the faulty programs were constructed. Do not claim that AI outperforms that rebuild or that these results generalize to arbitrary code or customer policies. The practical observation is that a successful process is insufficient for acceptance: B accepted nine incorrect outcomes, while the verification-gated approaches did not accept an incorrect outcome in this dataset.

## Design and limitations

Each of six families has three repairable cases and one ambiguous case: schema, units, joins, duplicates, completeness and downstream behavior. All four approaches receive the same case bytes, approved synthetic contract and fixed worker/verifier identities. Model jobs share the fixed Vultr `qwen3.8-flash-next` adapter, three-call/$0.10 maximum, token bounds and protected final grading. The predeclared ordering interleaves approaches; all 24 cases run once per approach. There is no repeated-trial consistency or statistical superiority claim.

The cases were generated and hashed before final model observations without calling the protected-canary data generator. They still share fault families and a positive source template with development. The arithmetic oracles were checked against the deterministic source reference; no independent human oracle review occurred. This is prospective synthetic evidence, not independently authored held-out customer data. Undefined units cause intake clarification; the other five ambiguous cases have explicit approved hold rules, so they do not measure the quality of model-authored business questions.

A uses actual intake, exact synthetic contract approval, original execution, queued repair and evidence export. No candidate was activated and no PR was created. C uses the repair core directly. Differences in orchestration mean A/C latency is not a pure witness ablation. All model-generated programs ran only on the deployed isolated worker. The fixed product image, worker and verifier stayed unchanged throughout this campaign.

## Preserved failures and amendments

- A `completeness-1`: the harness omitted two active original-run states. It stopped before repair; normal safety closure cancelled the original. Later SQL readback confirmed cleanup. Zero model calls; retained as a failed repair in the denominator.
- A `units-3` and `downstream-3`: three real calls each; product reported `attempts_exhausted`. Neither candidate became approved or active.
- C `duplicates-3`, `schema-3` and `units-3`: three real calls each; no accepted repair. Invalid proposals, execution failures and rejected outputs remain part of the bounded attempts.

After the first four dispatches, a recorded polling-only source amendment added the missing states and extracted continuation dispatch. It changed no case, prompt, model, price policy, runtime, grader, expected result or limit. No dispatched job was rerun. A later SSH preflight timeout, then management preflight failure, occurred before dispatch ten; a fresh read-only account/host/service check allowed only the undispatched suffix to continue. The transport root cause remains unknown. This is explicitly an amended-harness campaign, not an unchanged-source run.

All 96 closure receipts and all 24 ordinary API-workspace retirements were checked. The interrupted original's later cleanup evidence supplements, rather than replaces, its saved failed record. There are zero unresolved cleanup failures/unknowns in the reconciled records. This does not imply an absence of general infrastructure or security risks.

## Timing and cost

| Approach | Median / p95 seconds (n=24) | Input / output tokens | Provider usage estimate, USD | Conservative held reservations, USD |
| --- | ---: | ---: | ---: | ---: |
| A | 20.352 / 32.078 | 48,495 / 59,017 | 0.016664 | 0.640619 |
| B | 15.684 / 27.925 | 49,592 / 73,980 | 0.019769 | 0.724178 |
| C | 16.664 / 33.513 | 58,104 / 92,927 | 0.024408 | 0.835590 |
| D | 8.208 / 8.645 | 0 / 0 | 0 | 0 |

The 79 HTTP responses have matching actual request/quote/global-ledger receipts and parsed usage. Total per-call-rounded usage estimate is **$0.060841**; **$2.200387 remains conservatively reserved**. No refund/settlement was performed. These estimates are not invoices and exclude VM, storage, transfer, tax and other project charges. All costs, including failed attempts, remain in their denominators. Official same-model/rate quote refreshes were recorded before expiry; the actual rate was $0.10 input/$0.20 output per million tokens.

Latency is each measured adapter's elapsed job time, including failures and holds. It excludes between-job administrator preflight, quote refresh, recovery pauses and API-workspace retirement; it is not the entire campaign duration or a production SLA. The A interruption is included. B's incorrect-acceptance rate is 9/23, about 39.1%; A/C/D's zero observed incorrect acceptances are finite observations, not guarantees.

## Provenance and reproducibility

Plan digest: `7339b9245dc39c0180859a9d3bfd06405dbf014ba9e7cec31ff3ab4ba72e906b`.
Original frozen source digest: `13d33003d202e0afeefbd9d311b612b3ee7adb6be54466fe0f1332a33c181555`.
Original source checkpoint: `5911f2dffe0dc35ec817d527aa7764b5b4bfdadb`.
Polling amendment checkpoint: `7b115d3245eaf5ed60b00295a70b983d33b9124e`.

Product image: `200257609d3fa99f53829ab1cb9493e77a646f08afd2090abb947120d0388131`.
Worker runtime: `c826cf6662bcb4495cb744e34b9944044ade193fd870ca5a7bef140d3150dd78`.
Verifier rootfs: `0290920d63d9b55108c83d300922f5af84608147495f340e86025fc0e599e63b`.

The artifact lists original/amended source hashes and hashes of restricted live-receipt archives. Private provider bodies, protected canaries, account IDs and credentials are excluded. Hashes detect changed or mixed bytes; they do not independently prove a live call to someone without the underlying receipts. The offline artifact check rechecks case hashes, data-only oracles, denominators and metrics; it does not execute source, contact Vultr or rerun the benchmark:

```powershell
.venv/Scripts/python.exe -c "import json; from pathlib import Path; from eval.comparison_artifact import check; check(json.loads(Path('eval/final-comparison-2026-11-06.json').read_bytes())); print('Synthetic artifact accounting verified; no live calls or source execution')"
```

Do not rerun the one-shot campaign, continuation, collection or export commands merely to reproduce the table. Their saved intents prevent uncertain paid replay. Use the portable artifact checker for offline accounting. Future tuning must be labeled post-evaluation development; preserve this report and every failed run.
