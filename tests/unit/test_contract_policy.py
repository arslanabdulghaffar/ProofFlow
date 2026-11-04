"""Frozen wire representation tests; approval remains a separate product action."""

import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from contracts.codec import InputError
from contracts.policy import FIELDS, VERSION, parse_contract

EXAMPLE = Path("contracts/examples/synthetic-v1.1.json")


def test_frozen_example_and_canonical_identity():
    value = json.loads(EXAMPLE.read_bytes())
    parsed = parse_contract(EXAMPLE.read_bytes())
    assert parsed.amount_unit == "decimal_major" and dict(parsed.exponents) == {"JPY": 0, "USD": 2}
    assert parsed.attributes == () and parsed.include_currencies is None and not parsed.rollups
    reordered = {key: value[key] for key in reversed(value)}
    assert parse_contract(json.dumps(reordered).encode()).sha256 == parsed.sha256
    with pytest.raises(FrozenInstanceError):
        parsed.amount_unit = "infer"
    schema = json.loads(Path("schemas/merchant_revenue_v1.1.schema.json").read_bytes())
    assert set(schema["required"]) == set(schema["properties"]) == FIELDS
    assert schema["properties"]["schema_version"]["const"] == VERSION


@pytest.mark.parametrize("key,value", [
    ("schema_version", "merchant_revenue_v1"), ("profile", "real_customer_policy"),
    ("identity", ["transaction_id"]), ("customer_join", ["customer_id"]),
    ("duplicate_policy", "pick_first"), ("unresolved_policy", "drop"),
    ("timezone_policy", "infer"), ("amount_unit", None),
    ("currency_exponents", {}), ("currency_exponents", {"USD": True}),
    ("currency_exponents", {"USD": 2.0}), ("currency_exponents", {"USD": "2"}),
    ("currency_exponents", {"usd": 2}), ("currency_exponents", {"USD": 10}),
    ("column_aliases", {"a": "amount", "b": "amount"}),
    ("column_aliases", {"a": "source_row_id"}), ("column_aliases", {"a": "unknown"}),
    ("column_aliases", {"x\u0000": "amount"}), ("extra", "execute this"),
])
def test_unapproved_or_malformed_contract_is_rejected(key, value):
    contract = json.loads(EXAMPLE.read_bytes())
    contract[key] = value
    with pytest.raises(InputError):
        parse_contract(json.dumps(contract).encode())


@pytest.mark.parametrize("key,value", [
    ("include_currencies", []), ("include_currencies", ["EUR"]),
    ("include_currencies", ["USD", "USD"]), ("include_currencies", [True]),
    ("customer_attributes", ["merchant_id"]), ("customer_attributes", ["x", "x"]),
    ("customer_attributes", ["x" * 129]), ("customer_attributes", ["x\x00"]),
    ("customer_attributes", [{"execute": "x"}]), ("rollup", "customer_currency"),
    ("occurred_at_from_utc", "2026-11-04T00:00:00.000000Z"),
    ("arbitrary_filter", "amount > 0"),
])
def test_downstream_is_finite_and_exact(key, value):
    contract = json.loads(EXAMPLE.read_bytes())
    contract["downstream"][key] = value
    with pytest.raises(InputError):
        parse_contract(json.dumps(contract).encode())


def test_interval_calendar_spelling_and_order():
    contract = json.loads(EXAMPLE.read_bytes())
    for first, before in (("2026-11-04T00:00:00Z", "2026-11-05T00:00:00Z"),
                          ("2026-02-30T00:00:00.000000Z", "2026-11-05T00:00:00.000000Z"),
                          ("2026-11-05T00:00:00.000000Z", "2026-11-04T00:00:00.000000Z")):
        contract["downstream"].update(occurred_at_from_utc=first, occurred_at_before_utc=before)
        with pytest.raises(InputError, match="CONTRACT_INTERVAL_INVALID"):
            parse_contract(json.dumps(contract).encode())


def test_valid_alias_attribute_and_explicit_filters_survive_exactly():
    contract = json.loads(EXAMPLE.read_bytes())
    contract["column_aliases"] = {"value": "amount", "tier": "segment"}
    contract["downstream"].update(include_currencies=["USD"], customer_attributes=["segment"],
                                  rollup="merchant_currency",
                                  occurred_at_from_utc="2026-11-04T00:00:00.000000Z",
                                  occurred_at_before_utc="2026-11-05T00:00:00.000000Z")
    parsed = parse_contract(json.dumps(contract).encode())
    assert parsed.rollups and parsed.attributes == ("segment",)
    assert dict(parsed.aliases) == {"value": "amount", "tier": "segment"}
    assert json.loads(parsed.canonical) == contract
