"""Exact hand-computed synthetic arithmetic and time fixtures."""

import pytest

from contracts.codec import InputError
from contracts.scalars import amount_minor, timestamp_utc


@pytest.mark.parametrize("text,unit,exp,expected", [
    ("10.00", "decimal_major", 2, 1000), ("-0.01", "decimal_major", 2, -1),
    ("+00010.0", "decimal_major", 2, 1000), ("-0", "integer_minor", 2, 0),
    ("9007199254740993", "integer_minor", 2, 9007199254740993),
    ("9223372036854775807", "integer_minor", 0, 2**63 - 1),
    ("-9223372036854775808", "integer_minor", 0, -(2**63)),
    ("-92233720368547758.08", "decimal_major", 2, -(2**63)),
    ("7", "decimal_major", 0, 7), ("1.000000001", "decimal_major", 9, 1000000001),
    ("0" * 4096, "integer_minor", 0, 0),
])
def test_money_is_exact(text, unit, exp, expected):
    assert amount_minor(text, unit=unit, exponent=exp) == expected


@pytest.mark.parametrize("text", ["", " 1", "1 ", "1,000", "1e2", "NaN", "١", "1.",
                                 ".1", "1.001", "1\n", "++1", "92233720368547758.08",
                                 "-92233720368547758.09", "9" * 4096, True, 1])
def test_bad_decimal_is_not_coerced(text):
    with pytest.raises(InputError, match="INVALID_AMOUNT"):
        amount_minor(text, unit="decimal_major", exponent=2)


def test_minor_units_and_contract_parameters():
    with pytest.raises(InputError, match="INVALID_AMOUNT"):
        amount_minor("1.0", unit="integer_minor", exponent=2)
    with pytest.raises(InputError, match="UNKNOWN_UNIT"):
        amount_minor("1", unit="infer", exponent=2)
    for exp in (-1, 10, True, 2.0):
        with pytest.raises(InputError, match="INVALID_CURRENCY_EXPONENT"):
            amount_minor("1", unit="decimal_major", exponent=exp)


@pytest.mark.parametrize("text,expected", [
    ("2026-11-04T00:00:00+09:00", "2026-11-03T15:00:00.000000Z"),
    ("2024-02-29T23:59:59.1-01:00", "2024-03-01T00:59:59.100000Z"),
    ("2026-11-04T00:00:00.000001Z", "2026-11-04T00:00:00.000001Z"),
    ("0001-01-01T00:00:00Z", "0001-01-01T00:00:00.000000Z"),
])
def test_time_normalizes_without_losing_microseconds(text, expected):
    assert timestamp_utc(text) == expected


@pytest.mark.parametrize("text", [
    "2026-11-04", "2026-11-04T00:00:00", "2026-11-04T00:00:00-00:00",
    "2026-11-04T00:00:00.1234567Z", "2026-11-04T00:00:60Z", "2026-11-04T24:00:00Z",
    "2026-02-29T00:00:00Z", "2026-11-04T00:00:00+24:00", "2026-11-04T00:00:00+00:60",
    "0001-01-01T00:00:00+01:00", "9999-12-31T23:59:59-01:00",
    "2026-11-04t00:00:00z", "2026-11-04T00:00:00Z\n", True,
])
def test_time_does_not_infer_or_round(text):
    with pytest.raises(InputError, match="INVALID_TIMESTAMP"):
        timestamp_utc(text)
