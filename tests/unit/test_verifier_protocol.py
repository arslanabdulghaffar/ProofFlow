"""Trusted verifier protocol/canary data tests; never execute candidate code."""

import json
from pathlib import Path

import pytest

from contracts.codec import InputError, canonical_bytes, parse_object
from contracts.policy import parse_contract
from contracts.source import parse_sources
from verifier.canaries import generate
from verifier.protocol import MAX_REQUEST, decode, encode, process, sha
from verifier.reference import derive

CONTRACT = Path("contracts/examples/synthetic-v1.1.json").read_bytes()


def request(operation="canary", **overrides):
    value = {"operation": operation, "contract": encode(CONTRACT),
             "seed": "af" * 32, "case": "ownership"}
    value.update(overrides)
    return canonical_bytes(value, max_bytes=MAX_REQUEST)


def result(raw):
    response = parse_object(process(raw), max_bytes=16 * 1024 * 1024)
    assert response["request_sha256"] == sha(raw)
    return response


def test_canary_fresh_reproducible_composite_and_duplicate():
    first = result(request())["result"]
    assert result(request())["result"] == first
    other = result(request(seed="be" * 32))["result"]
    assert other["transactions_sha256"] != first["transactions_sha256"]
    tx, cs = parse_sources(decode(first["transactions_csv"], 10000),
                          decode(first["customers_csv"], 10000))
    truth = derive(tx, cs, parse_contract(CONTRACT))
    assert len(truth.ledger) == 3 and len(truth.unresolved) == 1
    assert truth.blocking_occurrences == 0
    assert {r["amount_minor"] for r in truth.ledger} == {0, 123, -123}
    assert len({r["customer_id"] for r in truth.ledger}) == 1
    assert len({r["canonical_customer_id"] for r in truth.ledger}) == 2
    assert truth.unresolved[0]["reason_code"] == "DUPLICATE_EXACT"


@pytest.mark.parametrize("unit,exponent", [("integer_minor", 9), ("decimal_major", 0),
                                          ("decimal_major", 9)])
def test_canary_contract_units_aliases_narrow_interval_attributes(unit, exponent):
    value = json.loads(CONTRACT)
    value["amount_unit"] = unit
    value["currency_exponents"] = {"XYZ": exponent, "ABC": 0}
    value["column_aliases"] = {"merchant": "merchant_id", "money": "amount", "tier": "segment"}
    value["downstream"].update(customer_attributes=["segment"], include_currencies=["XYZ"],
        occurred_at_from_utc="0001-01-01T00:00:00.000000Z",
        occurred_at_before_utc="0001-01-01T00:00:00.000001Z", rollup="merchant_currency")
    contract = parse_contract(canonical_bytes(value))
    for case, blocked in (("ownership", 0), ("quarantine", 5)):
        tx, cs = generate(contract, "ab" * 32, case)
        parsed = parse_sources(tx, cs, aliases=dict(contract.aliases),
                               customer_attributes=contract.attributes)
        truth = derive(*parsed, contract)
        assert truth.blocking_occurrences == blocked
        assert truth.rollups is not None
        if case == "quarantine":
            reasons = [r["reason_code"] for r in truth.unresolved]
            assert "MISSING_ATTRIBUTE" in reasons and reasons.count("FILTERED_BY_CONTRACT") == 2


def test_report_matches_but_holds_invalid_canary():
    contract = parse_contract(CONTRACT)
    tx, cs = generate(contract, "ac" * 32, "quarantine")
    expected = derive(*parse_sources(tx, cs), contract)
    outputs = {"ledger.jsonl": encode(b"".join(canonical_bytes(r) + b"\n"
                                               for r in expected.ledger)),
               "unresolved.jsonl": encode(b"".join(canonical_bytes(r) + b"\n"
                                                   for r in expected.unresolved))}
    raw = canonical_bytes({"operation": "verify", "contract": encode(CONTRACT),
                           "transactions": encode(tx), "customers": encode(cs), "outputs": outputs})
    report = result(raw)["result"]
    assert report["comparison"] == "match" and report["blocking_occurrences"] == 4
    assert "VERIFIED" not in json.dumps(report) and "approved" not in report
    outputs["ledger.jsonl"] = encode(b"PASS\n")
    mutated = json.loads(raw)
    mutated["outputs"] = outputs
    report = result(canonical_bytes(mutated))["result"]
    assert report["comparison"] == "mismatch" and report["findings"][0]["check"] == "V01"


@pytest.mark.parametrize("change", [{"seed": "z" * 64}, {"seed": True}, {"case": "caller"},
                                    {"pipeline": "print('PASS')"}, {"operation": "exec"},
                                    {"contract": "!!!!"}, {"contract": "e30="}])
def test_protocol_rejects_invalid_or_executable_fields(change):
    response = result(request(**change))
    assert response["status"] == "rejected" and "result" not in response


def test_alias_must_leave_required_fields_representable():
    value = json.loads(CONTRACT)
    value["column_aliases"] = {"merchant_id": "amount"}
    with pytest.raises(InputError, match="HEADER_ALIAS_UNREPRESENTABLE"):
        parse_contract(canonical_bytes(value))
    value["column_aliases"]["amount"] = "merchant_id"
    contract = parse_contract(canonical_bytes(value))
    tx, cs = generate(contract, "cd" * 32, "ownership")
    parsed = parse_sources(tx, cs, aliases=dict(contract.aliases))
    assert derive(*parsed, contract).blocking_occurrences == 0


def test_reject_noncanonical_base64_and_oversize_before_decode():
    for data, limit in (("AB==", 3), ("YQ==\n", 3), ("YWE=", 1), (True, 1)):
        with pytest.raises(InputError):
            decode(data, limit)


def test_wrong_owner_report_has_source_derived_bounded_witness():
    contract = parse_contract(CONTRACT)
    tx, cs = generate(contract, "de" * 32, "ownership")
    expected = derive(*parse_sources(tx, cs), contract)
    rows = [dict(row) for row in expected.ledger]
    original = rows[0]["canonical_customer_id"]
    rows[0]["canonical_customer_id"] = "incorrect-owner"
    files = {"ledger.jsonl": encode(b"".join(canonical_bytes(r) + b"\n" for r in rows)),
             "unresolved.jsonl": encode(b"".join(canonical_bytes(r) + b"\n"
                                                 for r in expected.unresolved))}
    raw = canonical_bytes({"operation": "verify", "contract": encode(CONTRACT),
                           "transactions": encode(tx), "customers": encode(cs), "outputs": files})
    report = result(raw)["result"]
    assert report["comparison"] == "mismatch"
    assert report["ownership_witnesses"][0]["expected_owner"] == original
    assert report["ownership_witnesses"][0]["actual_owner"] == "incorrect-owner"
