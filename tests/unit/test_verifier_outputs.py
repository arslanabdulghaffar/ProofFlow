"""Candidate output bytes are data, never trusted reports or executable code."""

import json

import pytest

from contracts.codec import InputError
from verifier.outputs import decode_outputs

ROW_ID = "tx:" + "a" * 64 + ":1"
LEDGER = {"source_row_id": ROW_ID, "merchant_id": "A", "transaction_id": "T",
          "customer_id": "C", "canonical_customer_id": "owner", "amount_minor": 100,
          "currency": "USD", "occurred_at_utc": "2026-11-04T00:00:00.000000Z", "attributes": {}}


def encode(value):
    return json.dumps(value, separators=(",", ":")).encode() + b"\n"


def decode(files, *, attrs=(), rollups=False):
    return decode_outputs(files, customer_attributes=attrs, currencies=frozenset({"USD"}),
                          include_rollups=rollups)


def test_valid_bytes_decode_without_any_success_verdict():
    result = decode({"ledger.jsonl": encode(LEDGER), "unresolved.jsonl": b""})
    assert result.ledger == (LEDGER,)
    assert result.unresolved == () and result.rollups is None
    assert not hasattr(result, "verified") and not hasattr(result, "passed")
    assert decode({"ledger.jsonl": b"", "unresolved.jsonl": b""}).ledger == ()


@pytest.mark.parametrize("field,value", [
    ("amount_minor", True), ("amount_minor", 1.0), ("amount_minor", "100"),
    ("amount_minor", 2**63), ("merchant_id", ""), ("merchant_id", "x" * 129),
    ("source_row_id", ROW_ID.replace(":1", ":01")), ("source_row_id", "../secret"),
    ("source_row_id", ROW_ID.replace(":1", ":10001")), ("currency", "JPY"),
    ("occurred_at_utc", "2026-11-04T00:00:00Z"), ("attributes", {"extra": "x"}),
    ("PASS", True),
])
def test_ledger_structure_cannot_coerce_or_add_authority(field, value):
    with pytest.raises(InputError):
        decode({"ledger.jsonl": encode({**LEDGER, field: value}), "unresolved.jsonl": b""})


@pytest.mark.parametrize("raw", [b"\n", b"PASS\n", b'{"x":1,"x":2}\n', b"{}\n\n",
                                 b'{}\x1e{}', b'{}\x00', b'\xef\xbb\xbf{}'])
def test_no_logs_blank_rows_or_non_json_framing(raw):
    with pytest.raises(InputError):
        decode({"ledger.jsonl": raw, "unresolved.jsonl": b""})


def test_missing_and_unexpected_files_fail_including_disabled_rollups():
    for files in ({"ledger.jsonl": b""},
                  {"ledger.jsonl": b"", "unresolved.jsonl": b"", "report.json": b"PASS"},
                  {"ledger.jsonl": b"", "unresolved.jsonl": b"", "rollups.jsonl": b""}):
        with pytest.raises(InputError, match="OUTPUT_FILES_MISMATCH"):
            decode(files)
    with pytest.raises(InputError, match="OUTPUT_FILES_MISMATCH"):
        decode({"ledger.jsonl": b"", "unresolved.jsonl": b""}, rollups=True)


def test_required_attributes_exact_strings_and_jsonl_string_separators():
    line = {**LEDGER, "attributes": {"segment": "retail\u2028line\nline"}}
    assert decode({"ledger.jsonl": encode(line), "unresolved.jsonl": b""},
                  attrs=("segment",)).ledger[0]["attributes"] == line["attributes"]
    for value in ("", None, 1, "x" * 4097, "\x00"):
        line["attributes"]["segment"] = value
        with pytest.raises(InputError, match="OUTPUT_ATTRIBUTES_INVALID"):
            decode({"ledger.jsonl": encode(line), "unresolved.jsonl": b""}, attrs=("segment",))


def test_unresolved_link_presence_depends_on_exact_reason():
    row = {"source_row_id": ROW_ID, "reason_code": "DUPLICATE_EXACT"}
    with pytest.raises(InputError, match="OUTPUT_DUPLICATE_LINK_INVALID"):
        decode({"ledger.jsonl": b"", "unresolved.jsonl": encode(row)})
    row["duplicate_of_source_row_id"] = ROW_ID.replace(":1", ":2")
    assert len(decode({"ledger.jsonl": b"", "unresolved.jsonl": encode(row)}).unresolved) == 1
    row["reason_code"] = "FILTERED_BY_CONTRACT"
    with pytest.raises(InputError, match="UNRESOLVED_STRUCTURE_INVALID"):
        decode({"ledger.jsonl": b"", "unresolved.jsonl": encode(row)})
    row.pop("duplicate_of_source_row_id")
    row["reason_code"] = "MODEL_APPROVED"
    with pytest.raises(InputError, match="OUTPUT_REASON_INVALID"):
        decode({"ledger.jsonl": b"", "unresolved.jsonl": encode(row)})


def test_rollup_uses_exact_large_decimal_string_not_float_or_int():
    rollup = {"merchant_id": "A", "currency": "USD", "transaction_count": 2,
              "amount_minor_total": "18446744073709551614"}
    files = {"ledger.jsonl": b"", "unresolved.jsonl": b"", "rollups.jsonl": encode(rollup)}
    assert decode(files, rollups=True).rollups == (rollup,)
    for value in ("01", "-0", "+1", "1.0", "1e3", 123, True, "9" * 24):
        files["rollups.jsonl"] = encode({**rollup, "amount_minor_total": value})
        with pytest.raises(InputError, match="ROLLUP_TOTAL_INVALID"):
            decode(files, rollups=True)


def test_global_file_line_and_byte_limits():
    with pytest.raises(InputError, match="OUTPUT_BYTE_LIMIT"):
        decode({"ledger.jsonl": b"x" * (10 * 1024 * 1024), "unresolved.jsonl": b"x"})
    with pytest.raises(InputError, match="OUTPUT_LINE_LIMIT"):
        decode({"ledger.jsonl": b"{}\n" * 10000, "unresolved.jsonl": b"{}\n" * 10001})
    with pytest.raises(InputError, match="JSON_BYTE_LIMIT"):
        decode({"ledger.jsonl": b" " * (128 * 1024 + 1), "unresolved.jsonl": b""})
