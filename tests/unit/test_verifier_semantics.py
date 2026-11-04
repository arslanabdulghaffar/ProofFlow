"""Hand-computed synthetic expectations and incorrect-output mutations.

These fixtures contain data only. No submitted/model-generated Python runs here.
"""

import csv
import hashlib
import io
import json
from pathlib import Path

import pytest

from contracts.codec import InputError
from verifier.compare import compare_bytes

TIME = "2026-11-04T00:00:00Z"
UTC_TIME = "2026-11-04T00:00:00.000000Z"
TX = ("A", "T1", "C", "10.00", "USD", TIME)
CUSTOMER = ("A", "C", "ownerA")


def csv_bytes(headers, rows):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(headers)
    writer.writerows(rows)
    return stream.getvalue().encode()


def row(ordinal=1, merchant="A", transaction="T1", customer="C", owner="ownerA",
        amount=1000, currency="USD", timestamp=UTC_TIME, attributes=None):
    return {"source_row_id": ordinal, "merchant_id": merchant, "transaction_id": transaction,
            "customer_id": customer, "canonical_customer_id": owner, "amount_minor": amount,
            "currency": currency, "occurred_at_utc": timestamp, "attributes": attributes or {}}


def quarantine(ordinal, reason, duplicate=None):
    value = {"source_row_id": ordinal, "reason_code": reason}
    if duplicate is not None:
        value["duplicate_of_source_row_id"] = duplicate
    return value


def setup_case(rows=(TX,), customers=(CUSTOMER,), *, attributes=(), downstream=None, unit=None):
    tx = csv_bytes(("merchant_id", "transaction_id", "customer_id", "amount", "currency",
                    "occurred_at"), rows)
    cs = csv_bytes(("merchant_id", "customer_id", "canonical_customer_id", *attributes), customers)
    contract = json.loads(Path("contracts/examples/synthetic-v1.1.json").read_bytes())
    contract["downstream"].update(downstream or {})
    contract["downstream"]["customer_attributes"] = list(attributes)
    if unit is not None:
        contract["amount_unit"] = unit
    return tx, cs, json.dumps(contract).encode()


def compare(case, ledger=(), unresolved=(), rollups=None):
    digest = hashlib.sha256(case[0]).hexdigest()

    def encode(records):
        prepared = []
        for original in records:
            value = original.copy()
            for key in ("source_row_id", "duplicate_of_source_row_id"):
                if key in value and type(value[key]) is int:
                    value[key] = f"tx:{digest}:{value[key]}"
            prepared.append(json.dumps(value).encode() + b"\n")
        return b"".join(prepared)

    files = {"ledger.jsonl": encode(ledger), "unresolved.jsonl": encode(unresolved)}
    if rollups is not None:
        files["rollups.jsonl"] = encode(rollups)
    return compare_bytes(*case, files)


def codes(result):
    return {finding.check_id for finding in result.findings}


def test_exact_source_derivation_and_output_hashes_do_not_grant_activation():
    result = compare(setup_case(), [row()])
    assert result.findings == () and result.expected.blocking_occurrences == 0
    assert result.expected.ledger[0]["amount_minor"] == 1000
    assert len(result.output_hashes) == 2
    assert not hasattr(result, "verified") and not hasattr(result, "approved")


@pytest.mark.parametrize("filter_kind", ["date", "currency", "both"])
def test_q08_missing_attribute_holds_every_exact_occurrence_despite_exclusion(filter_kind):
    downstream = {}
    if filter_kind in ("date", "both"):
        downstream.update(occurred_at_from_utc="2026-11-05T00:00:00.000000Z",
                          occurred_at_before_utc="2026-11-06T00:00:00.000000Z")
    if filter_kind in ("currency", "both"):
        downstream["include_currencies"] = ["JPY"]
    case = setup_case((TX, TX), (CUSTOMER + ("",),), attributes=("segment",), downstream=downstream)
    expected_q = [quarantine(i, "MISSING_ATTRIBUTE") for i in (1, 2)]
    correct = compare(case, unresolved=expected_q)
    assert correct.findings == ()
    assert correct.expected.blocking_occurrences == 2
    assert correct.expected.ledger == ()
    assert [r["reason_code"] for r in correct.expected.unresolved] == ["MISSING_ATTRIBUTE"] * 2
    for fact in correct.expected.facts:
        assert fact.violations == ("MISSING_ATTRIBUTE", "FILTERED_BY_CONTRACT")
        assert len(fact.failed_filters) == (2 if filter_kind == "both" else 1)
    filtered = compare(case, unresolved=[quarantine(i, "FILTERED_BY_CONTRACT") for i in (1, 2)])
    assert "V08" in codes(filtered) and filtered.expected.blocking_occurrences == 2
    hidden_duplicate = compare(case, unresolved=[expected_q[0],
                                                quarantine(2, "DUPLICATE_EXACT", 1)])
    assert {"V07", "V08"} <= codes(hidden_duplicate)


def test_exact_valid_duplicates_use_earliest_physical_occurrence_only():
    case = setup_case((TX, TX, TX))
    result = compare(case, [row()], [quarantine(2, "DUPLICATE_EXACT", 1),
                                   quarantine(3, "DUPLICATE_EXACT", 1)])
    assert result.findings == () and result.expected.blocking_occurrences == 0
    for target in (2, 3):
        wrong = compare(case, [row()], [quarantine(2, "DUPLICATE_EXACT", target),
                                       quarantine(3, "DUPLICATE_EXACT", 1)])
        assert "V07" in codes(wrong)
    wrong_first = compare(case, [row(2)], [quarantine(1, "DUPLICATE_EXACT", 2),
                                          quarantine(3, "DUPLICATE_EXACT", 2)])
    assert {"V07", "V08"} <= codes(wrong_first)


def test_valid_filtered_duplicates_each_have_filter_reason_without_representative():
    case = setup_case((TX, TX), downstream={"include_currencies": ["JPY"]})
    result = compare(case, unresolved=[quarantine(i, "FILTERED_BY_CONTRACT") for i in (1, 2)])
    assert result.findings == () and result.expected.blocking_occurrences == 0
    assert all("duplicate_of_source_row_id" not in item for item in result.expected.unresolved)


@pytest.mark.parametrize("amount", ["10.0", "11.00"])
def test_nonidentical_raw_amounts_conflict_even_when_normalized_equal(amount):
    case = setup_case((TX, TX[:3] + (amount,) + TX[4:]))
    result = compare(case, unresolved=[quarantine(i, "CONFLICTING_DUPLICATE") for i in (1, 2)])
    assert result.findings == () and result.expected.blocking_occurrences == 2
    wrong = compare(case, [row()], [quarantine(2, "DUPLICATE_EXACT", 1)])
    assert {"V07", "V08"} <= codes(wrong)


def test_all_violations_preserved_without_hiding_conflict_behind_bad_amount():
    case = setup_case((TX[:3] + ("bad",) + TX[4:], TX))
    result = compare(case, unresolved=[quarantine(1, "INVALID_AMOUNT"),
                                      quarantine(2, "CONFLICTING_DUPLICATE")])
    assert result.findings == () and result.expected.blocking_occurrences == 2
    assert result.expected.facts[0].violations == ("INVALID_AMOUNT", "CONFLICTING_DUPLICATE")


@pytest.mark.parametrize("customers,reason", [
    ((), "MISSING_CUSTOMER"), ((CUSTOMER, CUSTOMER), "AMBIGUOUS_CUSTOMER"),
    ((("A", "C", ""),), "MISSING_IDENTITY"),
])
def test_invalid_customer_exact_duplicates_are_all_blocking(customers, reason):
    case = setup_case((TX, TX), customers)
    result = compare(case, unresolved=[quarantine(i, reason) for i in (1, 2)])
    assert result.findings == () and result.expected.blocking_occurrences == 2


def test_total_preserving_cross_merchant_owner_swap_fails_v04():
    case = setup_case((TX[:3] + ("1.00",) + TX[4:], ("B", "T2", "C", "2.00", "USD", TIME)),
                      (CUSTOMER, ("B", "C", "ownerB")))
    correct = [row(amount=100), row(2, "B", "T2", owner="ownerB", amount=200)]
    assert compare(case, correct).findings == ()
    correct[0]["canonical_customer_id"], correct[1]["canonical_customer_id"] = "ownerB", "ownerA"
    result = compare(case, correct)
    assert codes(result) == {"V04"}  # V09 totals really do still match.


@pytest.mark.parametrize("field,value,check", [
    ("amount_minor", 1001, "V05"), ("currency", "JPY", "V06"),
    ("occurred_at_utc", "2026-11-04T00:00:00.000001Z", "V06"),
    ("merchant_id", "other", "V03"), ("canonical_customer_id", "other", "V04"),
])
def test_ledger_mutations_are_independently_rejected(field, value, check):
    record = row()
    record[field] = value
    assert check in codes(compare(setup_case(), [record]))


def test_no_all_rejected_shortcut_and_no_missing_or_double_counted_occurrences():
    case = setup_case()
    assert {"V08", "V09"} <= codes(compare(case, unresolved=[quarantine(1, "MISSING_CUSTOMER")]))
    assert "V02" in codes(compare(case))
    assert "V02" in codes(compare(case, [row(), row()]))
    assert "V02" in codes(compare(case, [row()], [quarantine(1, "FILTERED_BY_CONTRACT")]))


def test_half_open_date_boundaries_do_not_drop_start_or_include_end():
    end = "2026-11-05T00:00:00Z"
    case = setup_case((TX, ("A", "T2", "C", "10.00", "USD", end)), downstream={
        "occurred_at_from_utc": UTC_TIME, "occurred_at_before_utc": "2026-11-05T00:00:00.000000Z"})
    assert compare(case, [row()], [quarantine(2, "FILTERED_BY_CONTRACT")]).findings == ()
    assert "V08" in codes(compare(case, unresolved=[quarantine(i, "FILTERED_BY_CONTRACT")
                                                    for i in (1, 2)]))
    assert "V08" in codes(compare(case, [row(), row(2, transaction="T2",
                                                   timestamp="2026-11-05T00:00:00.000000Z")]))


def test_attributes_preserve_raw_strings_and_reject_changed_or_missing_values():
    case = setup_case(customers=(CUSTOMER + (" retail ",),), attributes=("segment",))
    assert compare(case, [row(attributes={"segment": " retail "})]).findings == ()
    assert "V10" in codes(compare(case, [row(attributes={"segment": "retail"})]))
    assert "V01" in codes(compare(case, [row()]))


def test_refunds_zero_large_exact_integers_and_rollups():
    values = [2**63 - 1, 2**63 - 1, -1, 0]
    rows = [("A", "T" + str(i), "C", str(value), "USD", TIME)
            for i, value in enumerate(values, 1)]
    case = setup_case(rows, unit="integer_minor", downstream={"rollup": "merchant_currency"})
    ledger = [row(i, transaction="T" + str(i), amount=value) for i, value in enumerate(values, 1)]
    rollup = {"merchant_id": "A", "currency": "USD", "transaction_count": 4,
              "amount_minor_total": "18446744073709551613"}
    result = compare(case, ledger, rollups=[rollup])
    assert result.findings == () and result.expected.rollups == (rollup,)
    for key, wrong in (("merchant_id", "B"), ("currency", "JPY"), ("transaction_count", 3),
                       ("amount_minor_total", "18446744073709551614")):
        assert "V10" in codes(compare(case, ledger, rollups=[{**rollup, key: wrong}]))
    assert "V10" in codes(compare(case, ledger, rollups=[rollup, rollup]))
    assert "V01" in codes(compare(case, ledger))


def test_genuinely_empty_eligible_sources_allow_empty_files_and_no_rollup_group():
    assert compare(setup_case((), ())).findings == ()
    case = setup_case((), (), downstream={"rollup": "merchant_currency"})
    result = compare(case, rollups=[])
    assert result.findings == () and result.expected.blocking_occurrences == 0


def test_malformed_output_has_exact_hash_and_cannot_self_grade():
    raw = b'{"PASS":true}\n'
    result = compare_bytes(*setup_case(), {"ledger.jsonl": raw, "unresolved.jsonl": b""})
    assert codes(result) == {"V01"}
    assert dict(result.output_hashes)["ledger.jsonl"] == hashlib.sha256(raw).hexdigest()
    with pytest.raises(InputError):
        compare_bytes(*setup_case(unit="infer"), {"ledger.jsonl": b"", "unresolved.jsonl": b""})
