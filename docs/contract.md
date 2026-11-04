# Synthetic merchant revenue contract

Status: **Phase2 bounded source/scalar/JSON parsers, output structure and partial V02–V04 checks implemented locally; Q08 resolved by owner on Nov4; v1.1 contract representation now frozen for implementation**. On 2026-10-24 the project owner approved, for synthetic demo data only: exact duplicates match every approved source field; the earliest physical source row represents them; conflicting transactions are all held; downstream support is limited to declared filters, customer attributes and merchant/currency rollups; every physical occurrence remains accounted for. This is not approval of real customer policies. The following finite definitions make that policy implementable. The product still obtains explicit approval of each exact contract before a job.

## Input and normalization

Support `pipeline.py` (UTF-8, <=16 KiB, standard library plus pinned pandas), `transactions.csv`, `customers.csv`, and declarative `contract.json` (<=32 KiB). Reject archives, binary/serialized objects, duplicate headers, invalid UTF-8, unknown columns except explicitly declared aliases/attributes, and executable policy fields. Limits: 5 MiB per CSV, 10 MiB data total, 10,000 records per table, 32 columns, 4 KiB per cell, objective <=2,000 characters; JSON depth <=8 (chosen bound).

Transactions require merchant_id, transaction_id, customer_id, amount, currency, occurred_at. Customers require merchant_id, customer_id, canonical_customer_id; optional attributes must be named by the contract. Input cells remain strings; aliases rename headers only. No trimming, case folding, Unicode normalization or numeric ID coercion is implicit. Empty required identifiers are missing. Synthetic IDs are 1–128 Unicode code points. CSV parsing assigns each logical data record its monotonically increasing physical occurrence ordinal (multiline quoted records count once); blank malformed records are rejected, not silently skipped. `source_row_id` binds the raw transaction asset SHA-256 plus that ordinal, so reordering that changes raw bytes creates a new manifest/IDs.

Identity is (merchant_id, transaction_id); customer lookup is (merchant_id, customer_id). Multiple lookup rows for the same composite key are AMBIGUOUS_CUSTOMER, even if the rows happen to agree; P0 does not silently deduplicate the lookup table.

Contracts explicitly choose `integer_minor` or `decimal_major`, allowed currencies and exponents (synthetic default USD:2, JPY:0), and offset-required timestamps. Parse decimals exactly without floats, exponents or thousands separators; reject fractional minor units, excess precision and signed-64-bit overflow. Refunds and zero are valid. Normalize ISO-8601 explicit offsets to UTC with six fractional digits; reject greater-than-microsecond precision, leap seconds and missing offsets. Allowed currencies and display units must never imply FX conversion. Summation uses arbitrary-precision integers; API/display totals are decimal strings.

## Duplicate algorithm and reason precedence

1. Compare raw string tuples after approved header alias mapping, excluding only generated source_row_id/ordinal. The tuple includes all six transaction fields and every contract-declared transaction extension (none in the initial profile). Customer attributes are checked independently through the unique lookup; they are not omitted silently from expected output.
2. Group by complete business identity. A group with more than one distinct raw tuple is conflicting: every member is held. Even `10.0` versus `10.00`, or two offset spellings of the same instant, are not exact duplicates. Do not pick a representative in a conflicting group.
3. Compute every applicable source violation independently. Choose one primary reason in this order: MISSING_IDENTITY → UNKNOWN_UNIT → INVALID_CURRENCY → INVALID_AMOUNT → INVALID_TIMESTAMP → CONFLICTING_DUPLICATE → AMBIGUOUS_CUSTOMER → MISSING_CUSTOMER → MISSING_ATTRIBUTE → FILTERED_BY_CONTRACT → DUPLICATE_EXACT. The trusted report also records all applicable failures; primary reason selection cannot hide a conflicting group. Missing/contradictory contract-wide units fail contract approval before inference; UNKNOWN_UNIT remains a diagnostic for such input.
4. Only otherwise valid, filter-included exact groups may collapse. The minimum physical ordinal is the representative and is placed in the ledger. Each remaining occurrence goes to unresolved with `DUPLICATE_EXACT` and `duplicate_of_source_row_id` pointing directly to that representative in the same input manifest. No chain, self-reference, cross-batch link or link to an excluded/unresolved row is valid.
5. If an exact group is invalid/ambiguous, each occurrence gets its independently justified blocking reason. If it is valid but filtered out, every occurrence is FILTERED_BY_CONTRACT; no dangling duplicate links. Correct exact-duplicate/filter bookkeeping is nonblocking. Other reasons hold the entire batch; partial evidence may be shown but not published as completed.

Examples for the owner (illustrative expected outcomes, NOT executed tests):

| Input | Required outcome |
| --- | --- |
| r1 and r2 have identical M-A/T1/C7/10.00/USD/time strings | r1 ledger 1000; r2 DUPLICATE_EXACT → r1 |
| r1=10.00 and r2=11.00 for M-A/T1 | Both CONFLICTING_DUPLICATE; no activation |
| r1=10.0 and r2=10.00 for M-A/T1 | Both conflicting under exact-source equality |
| Same customer C7 under merchants A and B | Join within each merchant; never substitute A's canonical owner for B |
| Exact repeated transaction with missing customer | Every occurrence MISSING_CUSTOMER; none labeled a harmless duplicate |
| Conflicting group also has a malformed amount | Malformed row primary INVALID_AMOUNT, other row primary CONFLICTING_DUPLICATE; group remains blocked |
| Two identical valid rows outside approved date interval | Both FILTERED_BY_CONTRACT; count both exclusions; no representative |
| Negative valid amount or zero inside interval | Included; no undocumented “positive-only” filter |

## Precisely bounded downstream extension

Interface version `merchant_revenue_v1.1` explicitly extends PDF page 54; never silently add keys to version 1. Phase 2 freezes JSON Schema and examples before code. The owner approved this category of synthetic behavior; these are routine finite representation defaults.

Contract fields: `schema_version`, `profile`, fixed `identity`/`customer_join`, `column_aliases` (unique source→canonical names), `amount_unit`, `currency_exponents`, `duplicate_policy=collapse_exact_and_report`, `unresolved_policy=hold_batch`, `timezone_policy=explicit_offset_required`, and `downstream`.

`downstream` has exactly:

- `include_currencies`: null or nonempty subset of allowed currencies; exact membership, no coercion.
- `occurred_at_from_utc` / `occurred_at_before_utc`: both null or an ordered UTC interval [from, before). Inclusion is currency AND interval. No expressions, regex, arbitrary predicates or hidden filters. A valid excluded row carries FILTERED_BY_CONTRACT and the violated fixed filter identifiers in the trusted report. Invalid source data is held even if a filter might exclude it.
- `customer_attributes`: up to four declared names, each a nonempty bounded string field from the unique customer row (e.g. `segment`). Required on every uniquely matched source customer when declared, including transactions excluded by a date/currency filter; missing values are blocking MISSING_ATTRIBUTE (owner Q08 approval, Nov4). Candidate `attributes` must contain exactly these keys and exact original strings; empty `{}` when none declared. No derived attributes or extra personally identifying fields.
- `rollup`: either `none` or `merchant_currency`. If enabled, candidate writes `rollups.jsonl`, one record per nonempty included group, with exact keys merchant_id, currency, transaction_count, amount_minor_total. Count representatives only; sum signed minor units; omit empty groups and reject extras. Total is an arbitrary-precision integer encoded as a decimal **string** to avoid overflow. No customer-level, time-bucket or cross-currency rollups.

The ledger retains all eight page-54 fields (source_row_id, merchant_id, transaction_id, customer_id, canonical_customer_id, amount_minor, currency, occurred_at_utc) plus the fixed `attributes` object. amount_minor is an integer, never bool/float, in signed 64-bit range. Browser/API money uses strings and BigInt. Unresolved has source_row_id/reason_code plus duplicate_of_source_row_id only for DUPLICATE_EXACT. v1.1 adds INVALID_CURRENCY, MISSING_ATTRIBUTE and FILTERED_BY_CONTRACT to the reason enum. Unknown keys fail everywhere.

The fixed worker CLI receives read-only transactions/customers/requirements JSONL/JSON and output paths for ledger, unresolved, and (only when enabled) rollups. The collector allowlist, manifest, combined 10 MiB/20,000-line cap, export and verifier all include the optional rollup file. A missing enabled file or unexpected disabled file fails. Output schema versions, downstream contract and verifier digest are approval-bound. No implementation may enable rollups without all these changes together.

## Verifier obligations

V01 strict structure/types/manifest; V02 disjoint complete source occurrence partition; V03 source business identity; V04 unique composite ownership and source customer_id; V05 exact signed values; V06 currency/time; V07 duplicate representative/link/group checks; V08 independently justified exclusions/reasons; V09 independently derived per-merchant/currency sums and counts; V10 protected canary plus declared filter/attribute/rollup regressions.

V10 must mutate a filter boundary, lose/change an attribute, and corrupt each rollup field to demonstrate rejection. The reference computes expected membership/attributes/aggregates directly from immutable source and contract, never by trusting candidate ledger totals alone. No all-rejected shortcut; a genuinely empty eligible set is allowed only when the trusted derivation proves it. Empty files still must exist. The source partition is L ∪ Q = S and L ∩ Q = ∅; duplicates and permitted filters remain in Q with nonblocking justification.

The canonical total-preserving wrong-owner example (PDF p18) must fail V04 even if V09 totals match. Fresh canaries change IDs, ordering, merchant overlap and amounts. Canaries execute independently in fresh sandboxes and are separate from held-out evaluation. A witness is bounded evidence, never a substitute for complete-input checking.

Deferred: arbitrary downstream code, dynamic extension schemas, custom aggregation/grouping, normalization beyond header aliases, nullable/derived customer attributes, implicit currency/time/unit policy, real-customer semantics. Such intake must fail UNSUPPORTED_PROFILE or require owner clarification; it must not receive a preservation claim.

## Resolved preparation ambiguity — Q08

The preparation wording was ambiguous about empty required attributes on otherwise valid filtered-out transactions. On2026-11-04 KST the owner explicitly selected: “Hold the batch for the missing required field (recommended).” Resolution: MISSING_ATTRIBUTE is blocking and precedes FILTERED_BY_CONTRACT. A date/currency exclusion never masks missing declared customer attributes; exact duplicates of such a row are each accounted for with the blocking primary reason. The trusted report retains applicable filter failures as well. This is synthetic-only policy approval, not approval of real customer rules or automatic exact-version activation.

Frozen representation: [v1.1 JSON Schema](../schemas/merchant_revenue_v1.1.schema.json) and [synthetic example](../contracts/examples/synthetic-v1.1.json) precede semantic implementation. schema_version is merchant_revenue_v1.1, profile synthetic_merchant_revenue; all listed fields are mandatory, unknown keys forbidden. Fixed identity/customer-join arrays retain declared order. At most32 declared three-uppercase-ASCII currency codes/exponents0–9; no currency catalogue/FX claim. Attribute names are1–128 Unicode codepoints, distinct, non-NUL and not reserved source/generated columns; values retain the existing4KiB source-cell limit. Alias names are1–4096 UTF8 bytes, unique targets from the approved source/attribute set. Date endpoints must both be null or canonical six-digit UTC strings defining an ordered half-open interval. Runtime validation supplements structural [JSON Schema2020-12](https://json-schema.org/draft/2020-12/json-schema-validation) with these cross-field, byte and exact-number rules. Later policy/representation changes require a new version and new job/approval.


## Phase2 representation components — Nov4

`contracts/codec.py` implements `proofflow-json-v1`: ASCII JSON (also valid UTF-8), Unicode scalar key ordering, compact separators, Python JSON lowercase escapes/surrogate pairs, no Unicode normalization, duplicate keys, floats/nonfinite numbers or out-of-range signed64 integers. Negative zero canonicalizes to0. Objects/arrays have depth8 and8192 total nodes; canonical output must fit its caller's byte cap. This is explicitly not RFC8785. Hand-written exact byte/hash vectors include reordered keys, escaped controls, supplementary characters and composed/decomposed Unicode. Future frontend code must use server hashes or match these vectors, including lossless integers; ordinary JavaScript Number is insufficient for ledger values.

The CSV dialect is comma/double-quote UTF-8 without BOM/NUL, strict quoting, no skipped blank records or type inference, exact required columns after one-pass approved aliases. CR/LF within quoted cells are preserved. Raw asset hash plus1-based logical data record ordinal forms `tx:<64 lowercase hex>:<ordinal>`. The normalized worker JSONL must still fit the existing combined10MiB input cap; escaping can expand otherwise valid CSV and causes an explicit rejection rather than a larger limit. No source deduplication occurs in parsing.

Money accepts ASCII signed digits with an optional nonempty decimal fraction for decimal-major only, exponent0–9; no whitespace/coercion/rounding. Timestamp spelling is the finite `YYYY-MM-DDTHH:MM:SS` with an optional1–6 digit fraction and required `Z` or signed `HH:MM` offset subset and normalizes to six-digit UTC. Unknown offset `-00:00` is rejected under explicit-offset policy ([RFC3339 section4.3](https://www.rfc-editor.org/rfc/rfc3339.html#section-4.3)); no full ISO8601 compatibility is claimed.

`verifier/outputs.py` enforces structural V01 decoding: exact file/key sets, JSONL,10MiB/20,000 combined lines,128KiB per record, exact integers/strings and declared attribute keys. `verifier/lineage.py` checks occurrence partition V02, source identity V03 and composite customer ownership V04 directly from source. Its empty findings are not a verification verdict. The complete source-comparison component below now adds money/reasons/filter/duplicate/rollup checks. Protected canaries, bounded verifier deployment, execution eligibility and exact approval remain separate unfinished integration gates. Tests deliberately demonstrate that these partial checks alone do not reject wrong amounts or invented quarantine reasons. No caller may promote their result to VERIFIED.

## Implemented source derivation and comparison — Nov4

`contracts/policy.py` supplements the frozen schema with exact-type/cross-field/byte checks and produces immutable canonical policy bytes. `verifier/reference.py` derives source membership, primary and all applicable violations, failed filters, canonical ownership, attributes, amounts and optional rollups without reading candidate output. Amount precision depends on a declared currency exponent: when currency is invalid, that error blocks; independently malformed amount syntax is still recorded without inventing an exponent. Unreferenced customer lookup rows cannot create ledger transactions.

`verifier/compare.py` compares bounded captured output with the complete source derivation: V01 structure, V02 partition, V03 identity, V04 ownership, V05 exact signed amount, V06 currency/UTC time, V07 raw duplicate/group/representative links, V08 independently justified exclusions, V09 source-derived counts/sums, and V10 attribute/rollup extension checks. Filter boundary and same-total ownership mutations are tested. V10's independently executed protected-canary workflow is still NOT RUN. The component emits findings and blocking source counts, not VERIFIED/COMPLETED/activation. Correctly quarantining invalid data can match the contract while the batch remains held. The full product must also authenticate/bind execution, cleanup, original/contract/runtime/verifier/output hashes, canaries, revocation and exact approvals.

[Actual worker fixture evidence](evidence/phase2-semantics-2026-11-04.json) proves collected bytes from deliberate wrong-owner and wrong-filter programs are rejected by trusted local comparison, and correct missing-attribute accounting still reports2 blocking occurrences. No candidate code executes on the verifier or development host. This is not an autonomous repair or full deployed verifier claim.
