"""Strict frozen synthetic v1.1 policy. Parsing grants no execution/approval."""

import hashlib
import re
from dataclasses import dataclass

from contracts.codec import InputError, canonical_bytes, parse_object
from contracts.scalars import timestamp_utc
from contracts.source import CUSTOMER_FIELDS, TRANSACTION_FIELDS

VERSION = "merchant_revenue_v1.1"
FIXED = {
    "schema_version": VERSION, "profile": "synthetic_merchant_revenue",
    "identity": ["merchant_id", "transaction_id"],
    "customer_join": ["merchant_id", "customer_id"],
    "duplicate_policy": "collapse_exact_and_report", "unresolved_policy": "hold_batch",
    "timezone_policy": "explicit_offset_required",
}
FIELDS = frozenset(FIXED) | {"column_aliases", "amount_unit", "currency_exponents", "downstream"}
DOWNSTREAM = frozenset({"include_currencies", "occurred_at_from_utc", "occurred_at_before_utc",
                        "customer_attributes", "rollup"})
CURRENCY = re.compile(r"[A-Z]{3}", re.ASCII)


@dataclass(frozen=True)
class Contract:
    canonical: bytes
    amount_unit: str
    exponents: tuple[tuple[str, int], ...]
    aliases: tuple[tuple[str, str], ...]
    attributes: tuple[str, ...]
    include_currencies: tuple[str, ...] | None
    from_utc: str | None
    before_utc: str | None
    rollups: bool

    @property
    def sha256(self):
        return hashlib.sha256(self.canonical).hexdigest()


def _name(value, maximum):
    return (type(value) is str and 1 <= len(value) <= maximum and "\x00" not in value
            and len(value.encode()) <= 4096)


def parse_contract(raw: bytes) -> Contract:
    value = parse_object(raw)
    if set(value) != FIELDS:
        raise InputError("CONTRACT_FIELDS_INVALID")
    if any(type(value[key]) is not type(expected) or value[key] != expected
           for key, expected in FIXED.items()):
        raise InputError("UNSUPPORTED_PROFILE")
    if value["amount_unit"] not in ("integer_minor", "decimal_major"):
        raise InputError("UNKNOWN_UNIT")
    currencies = value["currency_exponents"]
    if (type(currencies) is not dict or not 1 <= len(currencies) <= 32
            or any(CURRENCY.fullmatch(key) is None or type(exponent) is not int
                   or not 0 <= exponent <= 9 for key, exponent in currencies.items())):
        raise InputError("CONTRACT_CURRENCIES_INVALID")
    downstream = value["downstream"]
    if type(downstream) is not dict or set(downstream) != DOWNSTREAM:
        raise InputError("CONTRACT_DOWNSTREAM_INVALID")
    attrs = downstream["customer_attributes"]
    reserved = set(TRANSACTION_FIELDS) | set(CUSTOMER_FIELDS) | {"source_row_id"}
    if (type(attrs) is not list or len(attrs) > 4 or any(not _name(name, 128) for name in attrs)
            or len(set(attrs)) != len(attrs) or reserved.intersection(attrs)):
        raise InputError("ATTRIBUTE_DECLARATION_INVALID")
    aliases = value["column_aliases"]
    if (type(aliases) is not dict or len(aliases) > 32
            or any(not _name(key, 4096) or not _name(target, 4096)
                   for key, target in aliases.items())
            or len(set(aliases.values())) != len(aliases)
            or not set(aliases.values()) <= (reserved - {"source_row_id"}) | set(attrs)):
        raise InputError("HEADER_ALIAS_INVALID")
    # Every required canonical field needs a representable physical header.
    # Aliasing away a canonical name without an inverse makes all CSVs invalid.
    for field in (reserved - {"source_row_id"}) | set(attrs):
        if field in aliases and field not in aliases.values():
            raise InputError("HEADER_ALIAS_UNREPRESENTABLE")
    include = downstream["include_currencies"]
    if include is not None and (type(include) is not list or not 1 <= len(include) <= 32
                               or any(type(item) is not str for item in include)
                               or len(set(include)) != len(include)
                               or not set(include) <= currencies.keys()):
        raise InputError("CONTRACT_FILTER_CURRENCIES_INVALID")
    first, before = downstream["occurred_at_from_utc"], downstream["occurred_at_before_utc"]
    if (first is None) != (before is None):
        raise InputError("CONTRACT_INTERVAL_INVALID")
    if first is not None:
        try:
            if timestamp_utc(first) != first or timestamp_utc(before) != before or first >= before:
                raise InputError("CONTRACT_INTERVAL_INVALID")
        except InputError:
            raise InputError("CONTRACT_INTERVAL_INVALID") from None
    if downstream["rollup"] not in ("none", "merchant_currency"):
        raise InputError("CONTRACT_ROLLUP_INVALID")
    return Contract(canonical_bytes(value), value["amount_unit"], tuple(sorted(currencies.items())),
                    tuple(sorted(aliases.items())), tuple(attrs),
                    tuple(include) if include is not None else None, first, before,
                    downstream["rollup"] == "merchant_currency")
