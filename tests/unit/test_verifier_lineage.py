"""Independent hand-written source/expected ownership and partition mutations."""

import json

import pytest

from contracts.source import parse_sources
from verifier.lineage import check_lineage
from verifier.outputs import decode_outputs

TX = (b"merchant_id,transaction_id,customer_id,amount,currency,occurred_at\n"
      b"A,T1,C7,1.00,USD,2026-11-04T00:00:00Z\n"
      b"B,T2,C7,2.00,USD,2026-11-04T00:00:00Z\n")
CUSTOMERS = b"merchant_id,customer_id,canonical_customer_id\nA,C7,owner-A\nB,C7,owner-B\n"


def fixture(customers=CUSTOMERS):
    tx, cs = parse_sources(TX, customers)
    ledger = [{"source_row_id": tx.transaction_row_id(ordinal), "merchant_id": merchant,
               "transaction_id": transaction, "customer_id": "C7",
               "canonical_customer_id": "owner-" + merchant, "amount_minor": amount,
               "currency": "USD", "occurred_at_utc": "2026-11-04T00:00:00.000000Z",
               "attributes": {}}
              for ordinal, merchant, transaction, amount in ((1, "A", "T1", 100),
                                                             (2, "B", "T2", 200))]
    return tx, cs, ledger


def check(tx, cs, ledger, unresolved=()):
    files = {"ledger.jsonl": b"".join(json.dumps(row).encode() + b"\n" for row in ledger),
             "unresolved.jsonl": b"".join(json.dumps(row).encode() + b"\n" for row in unresolved)}
    decoded = decode_outputs(files, customer_attributes=(), currencies=frozenset({"USD"}),
                             include_rollups=False)
    return check_lineage(tx, cs, decoded)


def test_matching_source_partition_and_composite_ownership():
    tx, cs, ledger = fixture()
    assert check(tx, cs, ledger) == ()
    assert check(tx, cs, ledger[::-1]) == ()


def test_total_preserving_owner_swap_is_detected():
    tx, cs, ledger = fixture()
    ledger[0]["canonical_customer_id"], ledger[1]["canonical_customer_id"] = (
        ledger[1]["canonical_customer_id"], ledger[0]["canonical_customer_id"])
    assert sum(row["amount_minor"] for row in ledger) == 300
    findings = check(tx, cs, ledger)
    assert [finding.code for finding in findings] == ["CANONICAL_CUSTOMER_MISMATCH"] * 2
    assert all(finding.check_id == "V04" for finding in findings)


@pytest.mark.parametrize("field,value", [("merchant_id", "B"), ("transaction_id", "T99"),
                                       ("customer_id", "C99")])
def test_candidate_cannot_rewrite_source_identity(field, value):
    tx, cs, ledger = fixture()
    ledger[0][field] = value
    findings = check(tx, cs, ledger)
    assert len(findings) == 1 and findings[0].check_id == "V03"


def test_duplicate_drop_and_foreign_rows_fail_partition():
    tx, cs, ledger = fixture()
    for changed in (ledger[:1], ledger + ledger[:1], []):
        assert any(item.check_id == "V02" for item in check(tx, cs, changed))
    foreign = {**ledger[0], "source_row_id": "tx:" + "f" * 64 + ":1"}
    assert any(item.code == "FOREIGN_SOURCE_OCCURRENCE"
               for item in check(tx, cs, ledger + [foreign]))
    quarantine = {"source_row_id": ledger[0]["source_row_id"], "reason_code": "MISSING_CUSTOMER"}
    assert any(item.code == "SOURCE_OCCURRENCE_COUNT"
               for item in check(tx, cs, ledger, [quarantine]))


@pytest.mark.parametrize("customers", [
    b"merchant_id,customer_id,canonical_customer_id\nB,C7,owner-B\n",
    CUSTOMERS + b"A,C7,owner-A\n",
    CUSTOMERS + b"A,C7,other-owner\n",
])
def test_missing_and_ambiguous_customer_never_justify_ledger_owner(customers):
    tx, cs, ledger = fixture(customers)
    assert any(item.code == "CUSTOMER_LOOKUP_NOT_UNIQUE" for item in check(tx, cs, ledger))


def test_partial_checks_do_not_pretend_to_cover_money_or_reason_semantics():
    tx, cs, ledger = fixture()
    ledger[0]["amount_minor"] = 999
    assert check(tx, cs, ledger) == ()  # Later V05/V09 must reject this.
    unresolved = [{"source_row_id": row["source_row_id"], "reason_code": "MISSING_CUSTOMER"}
                  for row in ledger]
    assert check(tx, cs, [], unresolved) == ()  # Later V08 must reject this.
