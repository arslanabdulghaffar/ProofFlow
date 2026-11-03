"""V01 structural decoding only. Success is NOT a semantic or execution verdict."""

import re
from dataclasses import dataclass

from contracts.codec import InputError, parse_object
from contracts.scalars import timestamp_utc

MAX_OUTPUT_BYTES = 10 * 1024 * 1024
MAX_OUTPUT_LINES = 20000
MAX_LINE_BYTES = 128 * 1024
ROW_ID = re.compile(r"tx:[0-9a-f]{64}:[1-9][0-9]{0,4}", re.ASCII)
TOTAL = re.compile(r"0|-?[1-9][0-9]{0,22}", re.ASCII)
REASONS = frozenset({
    "MISSING_IDENTITY", "UNKNOWN_UNIT", "INVALID_CURRENCY", "INVALID_AMOUNT",
    "INVALID_TIMESTAMP", "CONFLICTING_DUPLICATE", "AMBIGUOUS_CUSTOMER", "MISSING_CUSTOMER",
    "MISSING_ATTRIBUTE", "FILTERED_BY_CONTRACT", "DUPLICATE_EXACT",
})
LEDGER_KEYS = frozenset({
    "source_row_id", "merchant_id", "transaction_id", "customer_id", "canonical_customer_id",
    "amount_minor", "currency", "occurred_at_utc", "attributes",
})


@dataclass(frozen=True)
class DecodedOutputs:
    # Internal trusted result, never a VERIFIED status. Callers must compare with
    # immutable sources and check supervisor/runtime/cleanup/epoch evidence.
    ledger: tuple[dict, ...]
    unresolved: tuple[dict, ...]
    rollups: tuple[dict, ...] | None


def _id(value):
    return type(value) is str and 1 <= len(value) <= 128 and "\x00" not in value


def _row_id(value):
    return (type(value) is str and ROW_ID.fullmatch(value) is not None
            and int(value.rsplit(":", 1)[1]) <= 10000)


def _ledger(value, attributes, currencies):
    if set(value) != LEDGER_KEYS:
        raise InputError("LEDGER_KEYS_INVALID")
    if not _row_id(value["source_row_id"]):
        raise InputError("OUTPUT_SOURCE_ID_INVALID")
    if any(not _id(value[key]) for key in ("merchant_id", "transaction_id", "customer_id",
                                          "canonical_customer_id")):
        raise InputError("OUTPUT_IDENTITY_INVALID")
    if type(value["amount_minor"]) is not int:
        raise InputError("OUTPUT_AMOUNT_INVALID")
    if type(value["currency"]) is not str or value["currency"] not in currencies:
        raise InputError("OUTPUT_CURRENCY_INVALID")
    if timestamp_utc(value["occurred_at_utc"]) != value["occurred_at_utc"]:
        raise InputError("OUTPUT_TIMESTAMP_NOT_CANONICAL")
    attrs = value["attributes"]
    if type(attrs) is not dict or set(attrs) != set(attributes):
        raise InputError("OUTPUT_ATTRIBUTES_INVALID")
    for item in attrs.values():
        if type(item) is not str or not item or len(item.encode()) > 4096 or "\x00" in item:
            raise InputError("OUTPUT_ATTRIBUTES_INVALID")


def _unresolved(value):
    reason = value.get("reason_code")
    if type(reason) is not str or reason not in REASONS:
        raise InputError("OUTPUT_REASON_INVALID")
    expected = {"source_row_id", "reason_code"}
    if reason == "DUPLICATE_EXACT":
        expected.add("duplicate_of_source_row_id")
        if not _row_id(value.get("duplicate_of_source_row_id")):
            raise InputError("OUTPUT_DUPLICATE_LINK_INVALID")
    if set(value) != expected or not _row_id(value.get("source_row_id")):
        raise InputError("UNRESOLVED_STRUCTURE_INVALID")


def _rollup(value, currencies):
    if set(value) != {"merchant_id", "currency", "transaction_count", "amount_minor_total"}:
        raise InputError("ROLLUP_KEYS_INVALID")
    if not _id(value["merchant_id"]):
        raise InputError("OUTPUT_IDENTITY_INVALID")
    if type(value["currency"]) is not str or value["currency"] not in currencies:
        raise InputError("OUTPUT_CURRENCY_INVALID")
    count, total = value["transaction_count"], value["amount_minor_total"]
    if type(count) is not int or not 1 <= count <= 10000:
        raise InputError("ROLLUP_COUNT_INVALID")
    if type(total) is not str or TOTAL.fullmatch(total) is None:
        raise InputError("ROLLUP_TOTAL_INVALID")


def decode_outputs(files: dict[str, bytes], *, customer_attributes: tuple[str, ...],
                   currencies: frozenset[str], include_rollups: bool) -> DecodedOutputs:
    """Decode a bounded in-memory collector result; never open candidate paths.

    Parameters come from the trusted contract, not candidate metadata. Semantic
    validation, source partition, ownership, totals and Q08 are separate gates.
    """
    if (type(customer_attributes) is not tuple or len(customer_attributes) > 4
            or any(type(name) is not str or not name for name in customer_attributes)
            or len(set(customer_attributes)) != len(customer_attributes)
            or type(currencies) is not frozenset or not currencies
            or any(type(currency) is not str or not currency for currency in currencies)
            or type(include_rollups) is not bool):
        raise InputError("OUTPUT_POLICY_INVALID")
    expected = {"ledger.jsonl", "unresolved.jsonl"}
    if include_rollups:
        expected.add("rollups.jsonl")
    if type(files) is not dict or set(files) != expected:
        raise InputError("OUTPUT_FILES_MISMATCH")
    if any(type(value) is not bytes for value in files.values()):
        raise InputError("OUTPUT_BYTES_REQUIRED")
    if sum(len(value) for value in files.values()) > MAX_OUTPUT_BYTES:
        raise InputError("OUTPUT_BYTE_LIMIT")
    # LF only is a framing rule. JSON whitespace CR is accepted at the end of
    # each nonempty record; Unicode separators inside strings are ordinary data.
    line_count = sum(value.count(b"\n") + int(bool(value) and not value.endswith(b"\n"))
                     for value in files.values())
    if line_count > MAX_OUTPUT_LINES:
        raise InputError("OUTPUT_LINE_LIMIT")
    decoded = {}
    for name, raw in files.items():
        records = []
        lines = raw.split(b"\n")
        if lines[-1] == b"":
            lines.pop()
        for line in lines:
            value = parse_object(line, max_bytes=MAX_LINE_BYTES)
            if name == "ledger.jsonl":
                _ledger(value, customer_attributes, currencies)
            elif name == "unresolved.jsonl":
                _unresolved(value)
            else:
                _rollup(value, currencies)
            records.append(value)
        decoded[name] = tuple(records)
    return DecodedOutputs(decoded["ledger.jsonl"], decoded["unresolved.jsonl"],
                          decoded.get("rollups.jsonl"))
