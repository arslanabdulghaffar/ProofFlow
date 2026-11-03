"""Bounded UTF-8 CSV preservation. No code import, inferred dtype or skipped row."""

import csv
import hashlib
import io
from dataclasses import dataclass

from contracts.codec import InputError, canonical_bytes

TRANSACTION_FIELDS = ("merchant_id", "transaction_id", "customer_id", "amount", "currency",
                      "occurred_at")
CUSTOMER_FIELDS = ("merchant_id", "customer_id", "canonical_customer_id")
MAX_CSV_BYTES = 5 * 1024 * 1024
MAX_ROWS = 10000
MAX_COLUMNS = 32
MAX_CELL_BYTES = 4096


def _name(value):
    if type(value) is not str or not value or "\x00" in value:
        return False
    try:
        return len(value.encode("utf-8", errors="strict")) <= MAX_CELL_BYTES
    except UnicodeError:
        return False


@dataclass(frozen=True)
class ParsedTable:
    kind: str
    raw_sha256: str
    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]

    def transaction_row_id(self, ordinal: int) -> str:
        if (self.kind != "transactions" or type(ordinal) is not int
                or not 1 <= ordinal <= len(self.rows)):
            raise InputError("SOURCE_OCCURRENCE_INVALID")
        return f"tx:{self.raw_sha256}:{ordinal}"

    def worker_jsonl(self) -> bytes:
        records = []
        for ordinal, row in enumerate(self.rows, 1):
            value = dict(zip(self.columns, row, strict=True))
            if self.kind == "transactions":
                value["source_row_id"] = self.transaction_row_id(ordinal)
            # Escaping can expand CSV bytes; the worker's combined bound is checked
            # separately by parse_sources, never raised to accommodate expansion.
            records.append(canonical_bytes(value, max_bytes=1024 * 1024) + b"\n")
        return b"".join(records)


def _quote_grammar(text: str):
    """Reject bare quotes that csv.reader(strict=True) still accepts as field text."""
    state = "start"
    for char in text:
        if state == "quoted":
            if char == '"':
                state = "closed"
        elif state == "closed":
            if char == '"':
                state = "quoted"
            elif char == "," or char in "\r\n":
                state = "start"
            else:
                raise InputError("CSV_QUOTING_INVALID")
        elif char == '"':
            if state != "start":
                raise InputError("CSV_QUOTING_INVALID")
            state = "quoted"
        elif char == "," or char in "\r\n":
            state = "start"
        else:
            state = "unquoted"
    if state == "quoted":
        raise InputError("CSV_QUOTING_INVALID")


def parse_csv(raw: bytes, *, kind: str, aliases: dict[str, str] | None = None,
              customer_attributes: tuple[str, ...] = ()) -> ParsedTable:
    if type(raw) is not bytes or not raw or len(raw) > MAX_CSV_BYTES:
        raise InputError("CSV_BYTE_LIMIT")
    if kind not in ("transactions", "customers"):
        raise InputError("SOURCE_KIND_INVALID")
    if (type(customer_attributes) is not tuple or len(customer_attributes) > 4
            or any(not _name(name) for name in customer_attributes)
            or len(set(customer_attributes)) != len(customer_attributes)
            or set(customer_attributes) & (set(TRANSACTION_FIELDS) | set(CUSTOMER_FIELDS)
                                           | {"source_row_id"})):
        raise InputError("ATTRIBUTE_DECLARATION_INVALID")
    required = (TRANSACTION_FIELDS if kind == "transactions"
                else CUSTOMER_FIELDS + customer_attributes)
    aliases = {} if aliases is None else aliases
    if (type(aliases) is not dict or len(aliases) > MAX_COLUMNS
            or any(not _name(key) or not _name(value)
                   for key, value in aliases.items())
            or len(set(aliases.values())) != len(aliases)):
        raise InputError("HEADER_ALIAS_INVALID")
    all_fields = set(TRANSACTION_FIELDS) | set(CUSTOMER_FIELDS) | set(customer_attributes)
    if not set(aliases.values()) <= all_fields:
        raise InputError("HEADER_ALIAS_INVALID")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeError:
        raise InputError("CSV_INVALID_UTF8") from None
    if text.startswith("\ufeff") or "\x00" in text:
        raise InputError("CSV_UNSUPPORTED_ENCODING_OR_BINARY")
    _quote_grammar(text)
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    try:
        headers = next(reader)
        if (not headers or len(headers) > MAX_COLUMNS or any(not x for x in headers)
                or any(len(x.encode()) > MAX_CELL_BYTES for x in headers)
                or len(set(headers)) != len(headers)):
            raise InputError("CSV_HEADERS_INVALID")
        columns = tuple(aliases.get(name, name) for name in headers)
        if len(set(columns)) != len(columns) or set(columns) != set(required):
            raise InputError("CSV_COLUMNS_MISMATCH")
        rows = []
        for row in reader:
            if len(rows) >= MAX_ROWS:
                raise InputError("CSV_ROW_LIMIT")
            if not row or len(row) != len(columns):
                raise InputError("CSV_RECORD_WIDTH")
            if any(len(value.encode()) > MAX_CELL_BYTES for value in row):
                raise InputError("CSV_CELL_LIMIT")
            rows.append(tuple(row))
    except (csv.Error, StopIteration, UnicodeError):
        raise InputError("CSV_SYNTAX_INVALID") from None
    return ParsedTable(kind, hashlib.sha256(raw).hexdigest(), columns, tuple(rows))


def parse_sources(transactions: bytes, customers: bytes, *, aliases=None,
                  customer_attributes: tuple[str, ...] = ()) -> tuple[ParsedTable, ParsedTable]:
    tx = parse_csv(transactions, kind="transactions", aliases=aliases,
                   customer_attributes=customer_attributes)
    customers_table = parse_csv(customers, kind="customers", aliases=aliases,
                                customer_attributes=customer_attributes)
    if len(tx.worker_jsonl()) + len(customers_table.worker_jsonl()) > 10 * 1024 * 1024:
        raise InputError("NORMALIZED_SOURCE_BYTE_LIMIT")
    return tx, customers_table
