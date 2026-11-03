"""Bounded JSON and versioned canonical bytes. No float/coercion/Unicode normalization."""

import hashlib
import json

CANONICAL_VERSION = "proofflow-json-v1"
MAX_DEPTH = 8
MAX_NODES = 8192
INT64_MIN, INT64_MAX = -(2**63), 2**63 - 1


class InputError(Exception):
    """Fixed diagnostic code; never attach uploaded data or native exception text."""


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise InputError("JSON_DUPLICATE_KEY")
        value[key] = item
    return value


def _integer(text):
    if len(text) > 20:
        raise InputError("JSON_INTEGER_RANGE")
    result = int(text)
    if not INT64_MIN <= result <= INT64_MAX:
        raise InputError("JSON_INTEGER_RANGE")
    return result


def _no_float(_):
    raise InputError("JSON_NONINTEGER_NUMBER")


def _validate(value):
    pending = [(value, 0)]
    count = 0
    while pending:
        item, depth = pending.pop()
        count += 1
        if count > MAX_NODES:
            raise InputError("JSON_NODE_LIMIT")
        kind = type(item)
        if kind in (dict, list):
            depth += 1
            if depth > MAX_DEPTH:
                raise InputError("JSON_DEPTH_LIMIT")
            children = len(item) * (2 if kind is dict else 1)
            if count + len(pending) + children > MAX_NODES:
                raise InputError("JSON_NODE_LIMIT")
            if kind is dict:
                for key, child in item.items():
                    if type(key) is not str:
                        raise InputError("JSON_KEY_TYPE")
                    pending.extend(((key, depth), (child, depth)))
            else:
                pending.extend((child, depth) for child in item)
        elif kind is str:
            try:
                item.encode("utf-8", errors="strict")
            except UnicodeError:
                raise InputError("JSON_INVALID_UNICODE") from None
        elif kind is int:
            if not INT64_MIN <= item <= INT64_MAX:
                raise InputError("JSON_INTEGER_RANGE")
        elif item is not None and kind is not bool:
            raise InputError("JSON_UNSUPPORTED_TYPE")


def parse_object(raw: bytes, *, max_bytes: int = 32768) -> dict:
    if type(raw) is not bytes or not raw or len(raw) > max_bytes:
        raise InputError("JSON_BYTE_LIMIT")
    try:
        text = raw.decode("utf-8", errors="strict")
        # Bound recursion before invoking the standard parser; strings are inert.
        depth = 0
        quoted = escaped = False
        for char in text:
            if quoted:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    quoted = False
            elif char == '"':
                quoted = True
            elif char in "[{":
                depth += 1
                if depth > MAX_DEPTH:
                    raise InputError("JSON_DEPTH_LIMIT")
            elif char in "]}":
                depth -= 1
        value = json.loads(text, object_pairs_hook=_pairs, parse_int=_integer,
                           parse_float=_no_float, parse_constant=_no_float)
    except (UnicodeError, ValueError, RecursionError):
        raise InputError("JSON_INVALID_ENCODING_OR_SYNTAX") from None
    if type(value) is not dict:
        raise InputError("JSON_OBJECT_REQUIRED")
    _validate(value)
    return value


def canonical_bytes(value: dict, *, max_bytes: int = 32768) -> bytes:
    """ASCII JSON, Unicode-scalar key order, lowercase escapes, compact separators.

    This is ProofFlow's explicit format, not an assertion of RFC8785 conformance.
    JSON escaped pairs are decoded before sorting; no NFC normalization occurs.
    """
    if type(value) is not dict:
        raise InputError("JSON_OBJECT_REQUIRED")
    _validate(value)
    result = json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"),
                        allow_nan=False).encode("ascii")
    if len(result) > max_bytes:
        raise InputError("JSON_BYTE_LIMIT")
    return result


def canonical_digest(value: dict) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()
