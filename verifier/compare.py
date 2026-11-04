"""Compare collected bytes with immutable source-derived truth, never execute code.

This is a semantic component, not a release verdict. The dispatcher must still
bind actual execution/runtime/cleanup, exact contract approval, verifier identity
and independently executed canaries. Empty findings grant no activation.
"""

import hashlib
from collections import defaultdict
from dataclasses import dataclass

from contracts.codec import InputError
from contracts.policy import parse_contract
from contracts.source import parse_sources
from verifier.lineage import Finding, check_lineage
from verifier.outputs import MAX_OUTPUT_BYTES, DecodedOutputs, decode_outputs
from verifier.reference import ExpectedBatch, derive


@dataclass(frozen=True)
class Comparison:
    contract_sha256: str
    transactions_sha256: str
    customers_sha256: str
    output_hashes: tuple[tuple[str, str], ...]
    findings: tuple[Finding, ...]
    expected: ExpectedBatch


def _totals(ledger):
    totals = defaultdict(lambda: [0, 0])
    for row in ledger:
        values = totals[(row["merchant_id"], row["currency"])]
        values[0] += 1
        values[1] += row["amount_minor"]
    return dict(totals)


def _semantic(expected: ExpectedBatch, actual: DecodedOutputs) -> list[Finding]:
    findings = []
    expected_ledger = {row["source_row_id"]: row for row in expected.ledger}
    expected_unresolved = {row["source_row_id"]: row for row in expected.unresolved}
    facts = {fact.source_row_id: fact for fact in expected.facts}

    def fail(check, code, identifier=""):
        findings.append(Finding(check, code, identifier))

    for row in actual.ledger:
        identifier = row["source_row_id"]
        wanted = expected_ledger.get(identifier)
        if wanted is None:
            fail("V08", "UNJUSTIFIED_LEDGER_MEMBERSHIP", identifier)
            fact = facts.get(identifier)
            if fact and set(fact.violations) & {"DUPLICATE_EXACT", "CONFLICTING_DUPLICATE"}:
                fail("V07", "DUPLICATE_GROUP_IN_LEDGER", identifier)
            continue
        if row["amount_minor"] != wanted["amount_minor"]:
            fail("V05", "AMOUNT_MISMATCH", identifier)
        if (row["currency"] != wanted["currency"]
                or row["occurred_at_utc"] != wanted["occurred_at_utc"]):
            fail("V06", "CURRENCY_OR_TIME_MISMATCH", identifier)
        if row["attributes"] != wanted["attributes"]:
            fail("V10", "SOURCE_ATTRIBUTES_MISMATCH", identifier)
    for row in actual.unresolved:
        identifier = row["source_row_id"]
        wanted = expected_unresolved.get(identifier)
        if wanted is None or row["reason_code"] != wanted["reason_code"]:
            fail("V08", "UNJUSTIFIED_EXCLUSION", identifier)
        if (row["reason_code"] == "DUPLICATE_EXACT"
                or wanted is not None and wanted["reason_code"] == "DUPLICATE_EXACT"):
            if row != wanted:
                fail("V07", "DUPLICATE_REPRESENTATIVE_MISMATCH", identifier)
    if _totals(actual.ledger) != _totals(expected.ledger):
        fail("V09", "SOURCE_DERIVED_TOTALS_OR_COUNTS_MISMATCH")
    if expected.rollups is not None:
        expected_rollups = {(r["merchant_id"], r["currency"]): r for r in expected.rollups}
        actual_rollups = {(r["merchant_id"], r["currency"]): r for r in actual.rollups}
        if len(actual_rollups) != len(actual.rollups):
            fail("V10", "ROLLUP_DUPLICATE_GROUP")
        if actual_rollups.keys() != expected_rollups.keys():
            fail("V10", "ROLLUP_GROUPS_MISMATCH")
        for key in actual_rollups.keys() & expected_rollups.keys():
            if (actual_rollups[key]["transaction_count"]
                    != expected_rollups[key]["transaction_count"]):
                fail("V10", "ROLLUP_COUNT_MISMATCH")
            if (actual_rollups[key]["amount_minor_total"]
                    != expected_rollups[key]["amount_minor_total"]):
                fail("V10", "ROLLUP_TOTAL_MISMATCH")
    return findings


def compare_bytes(transactions: bytes, customers: bytes, contract_bytes: bytes,
                  files: dict[str, bytes]) -> Comparison:
    """No raw code parameter, path, caller-selected oracle or approval bypass.

    Invalid source/contract raises a fixed InputError; invalid candidate output
    becomes V01 evidence. All findings and source blocking counts must be checked.
    """
    contract = parse_contract(contract_bytes)
    tx, cs = parse_sources(transactions, customers, aliases=dict(contract.aliases),
                          customer_attributes=contract.attributes)
    expected = derive(tx, cs, contract)
    # Keep bounded malformed output reproducible without trusting JSON or names.
    output_hashes = ()
    if (type(files) is dict and set(files) <= {"ledger.jsonl", "unresolved.jsonl", "rollups.jsonl"}
            and all(type(raw) is bytes for raw in files.values())
            and sum(len(raw) for raw in files.values()) <= MAX_OUTPUT_BYTES):
        output_hashes = tuple(sorted((name, hashlib.sha256(raw).hexdigest())
                                     for name, raw in files.items()))
    try:
        actual = decode_outputs(files, customer_attributes=contract.attributes,
                                currencies=frozenset(dict(contract.exponents)),
                                include_rollups=contract.rollups)
    except InputError as error:
        # Unbounded or non-byte caller input is not hashable evidence. The worker
        # collector already binds real captured files in its separate receipt.
        findings = (Finding("V01", str(error), ""),)
    else:
        combined = check_lineage(tx, cs, actual) + tuple(_semantic(expected, actual))
        findings = tuple(sorted(set(combined),
                                key=lambda item: (item.check_id, item.source_row_id, item.code)))
    return Comparison(contract.sha256, tx.raw_sha256, cs.raw_sha256, output_hashes,
                      findings, expected)
