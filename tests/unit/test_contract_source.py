"""Source occurrence preservation and hostile CSV parser cases; trusted tests."""

import hashlib
import json

import pytest

from contracts.codec import InputError
from contracts.source import MAX_CSV_BYTES, parse_csv, parse_sources

HEADER = b"merchant_id,transaction_id,customer_id,amount,currency,occurred_at\n"
ROW = b"A,T1,001,10.00,USD,2026-11-04T00:00:00Z\n"
CUSTOMERS = b"merchant_id,customer_id,canonical_customer_id\nA,001,owner\n"


def test_every_duplicate_occurrence_remains_distinct_and_raw():
    raw = HEADER + ROW * 2
    tx, customers = parse_sources(raw, CUSTOMERS)
    assert tx.rows[0] == tx.rows[1]
    assert tx.rows[0][2:4] == ("001", "10.00")
    digest = hashlib.sha256(raw).hexdigest()
    assert tx.transaction_row_id(1) == f"tx:{digest}:1"
    assert tx.transaction_row_id(2) == f"tx:{digest}:2"
    records = [json.loads(line) for line in tx.worker_jsonl().splitlines()]
    assert records[0]["amount"] == "10.00"
    assert records[0]["source_row_id"] != records[1]["source_row_id"]
    assert b"source_row_id" not in customers.worker_jsonl()


def test_quoted_newlines_commas_escapes_and_unicode_are_preserved():
    raw = HEADER + '" A\r\n\nB ",T1,"x,""é""",1,USD,now\r\n'.encode()
    table = parse_csv(raw, kind="transactions")
    assert len(table.rows) == 1
    assert table.rows[0][:3] == (" A\r\n\nB ", "T1", 'x,"é"')
    assert len(table.worker_jsonl().splitlines()) == 1


def test_aliases_and_declared_attributes_are_exact():
    tx = parse_csv(HEADER.replace(b"amount", b"value") + ROW, kind="transactions",
                   aliases={"value": "amount"})
    assert tx.rows[0][3] == "10.00"
    customers = parse_csv(CUSTOMERS.replace(b"canonical_customer_id\n",
                                           b"canonical_customer_id,segment\n")
                          .replace(b"owner\n", b"owner, retail \n"), kind="customers",
                          customer_attributes=("segment",))
    assert customers.rows[0][-1] == " retail "


@pytest.mark.parametrize("raw,code", [
    (b"", "CSV_BYTE_LIMIT"), (b"x" * (MAX_CSV_BYTES + 1), "CSV_BYTE_LIMIT"),
    (HEADER + b"\xff", "CSV_INVALID_UTF8"),
    (b"\xef\xbb\xbf" + HEADER, "CSV_UNSUPPORTED_ENCODING_OR_BINARY"),
    (HEADER + b"\x00", "CSV_UNSUPPORTED_ENCODING_OR_BINARY"),
    (HEADER + b"\n", "CSV_RECORD_WIDTH"),
    (HEADER + b"a,b\n", "CSV_RECORD_WIDTH"),
    (HEADER + b'a"b,T,C,1,USD,now\n', "CSV_QUOTING_INVALID"),
    (HEADER + b'"a"x,T,C,1,USD,now\n', "CSV_QUOTING_INVALID"),
    (HEADER + b'"a,T,C,1,USD,now\n', "CSV_QUOTING_INVALID"),
    (HEADER + b"A,T,C," + b"1" * 4097 + b",USD,now\n", "CSV_CELL_LIMIT"),
    (HEADER + ROW * 10001, "CSV_ROW_LIMIT"),
    (HEADER.replace(b"amount", b"currency"), "CSV_HEADERS_INVALID"),
    (HEADER.replace(b"amount", b"other"), "CSV_COLUMNS_MISMATCH"),
])
def test_malformed_csv_never_skips_rows(raw, code):
    with pytest.raises(InputError, match=f"^{code}$"):
        parse_csv(raw, kind="transactions")


def test_cell_limit_is_utf8_bytes_and_empty_table_is_explicit():
    assert parse_csv(HEADER, kind="transactions").worker_jsonl() == b""
    raw = HEADER + ("é" * 2049 + ",T,C,1,USD,now\n").encode()
    with pytest.raises(InputError, match="CSV_CELL_LIMIT"):
        parse_csv(raw, kind="transactions")


@pytest.mark.parametrize("attributes", [("amount",), ("x", "x"), ("\ud800",), ("",),
                                       (["x"],), ("a", "b", "c", "d", "e")])
def test_invalid_attribute_declarations_have_fixed_errors(attributes):
    with pytest.raises(InputError, match="ATTRIBUTE_DECLARATION_INVALID"):
        parse_csv(CUSTOMERS, kind="customers", customer_attributes=attributes)


@pytest.mark.parametrize("aliases", [{"x": "amount", "y": "amount"}, {"x": "unknown"},
                                    {"\ud800": "amount"}, {"x": []}, {"": "amount"}])
def test_aliases_never_coerce_or_hide_duplicate_headers(aliases):
    with pytest.raises(InputError, match="HEADER_ALIAS_INVALID"):
        parse_csv(HEADER, kind="transactions", aliases=aliases)


def test_alias_shadow_and_occurrence_bounds():
    with pytest.raises(InputError, match="CSV_COLUMNS_MISMATCH"):
        parse_csv(HEADER, kind="transactions", aliases={"currency": "amount"})
    tx = parse_csv(HEADER + ROW, kind="transactions")
    for ordinal in (0, 2, True, "1"):
        with pytest.raises(InputError, match="SOURCE_OCCURRENCE_INVALID"):
            tx.transaction_row_id(ordinal)


def test_normalized_data_cannot_expand_past_worker_limit():
    # ASCII escaping expands each 3-byte codepoint to six bytes. Raw CSV fits5MiB.
    row = ("界" * 1300 + ",T,C,1,USD,now\n").encode()
    with pytest.raises(InputError, match="NORMALIZED_SOURCE_BYTE_LIMIT"):
        parse_sources(HEADER + row * 1300,
                      b"merchant_id,customer_id,canonical_customer_id\n" +
                      ("A,C," + "界" * 1300 + "\n").encode() * 1300)
