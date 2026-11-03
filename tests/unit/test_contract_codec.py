"""Trusted input and golden canonical vectors; no candidate execution."""

import hashlib

import pytest

from contracts.codec import InputError, canonical_bytes, canonical_digest, parse_object


@pytest.mark.parametrize("raw,code", [
    (b'{"x":1,"x":2}', "JSON_DUPLICATE_KEY"),
    (b'{"x":{"a":0,"a":1}}', "JSON_DUPLICATE_KEY"),
    (b'{"a":1,"\\u0061":2}', "JSON_DUPLICATE_KEY"),
    (b'{"x":1.0}', "JSON_NONINTEGER_NUMBER"),
    (b'{"x":1e0}', "JSON_NONINTEGER_NUMBER"),
    (b'{"x":NaN}', "JSON_NONINTEGER_NUMBER"),
    (b'{"x":Infinity}', "JSON_NONINTEGER_NUMBER"),
    (b'{"x":9223372036854775808}', "JSON_INTEGER_RANGE"),
    (b'{"x":-9223372036854775809}', "JSON_INTEGER_RANGE"),
    (b'{"x":"\\ud800"}', "JSON_INVALID_UNICODE"),
    (b'{"x":"\xff"}', "JSON_INVALID_ENCODING_OR_SYNTAX"),
    (b'{}{}', "JSON_INVALID_ENCODING_OR_SYNTAX"),
    (b'[]', "JSON_OBJECT_REQUIRED"),
    (b'', "JSON_BYTE_LIMIT"),
    (b' ' * 32769, "JSON_BYTE_LIMIT"),
    (b'{"x":' + b'[' * 8 + b'0' + b']' * 8 + b'}', "JSON_DEPTH_LIMIT"),
    (b'{"x":[' + b'0,' * 8192 + b'0]}', "JSON_NODE_LIMIT"),
])
def test_invalid_json_has_fixed_diagnostic(raw, code):
    with pytest.raises(InputError, match=f"^{code}$"):
        parse_object(raw)


def test_canonical_golden_vectors_are_exact_not_normalized():
    vectors = [
        ({}, b'{}', "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"),
        ({"b": 2, "a": 1}, b'{"a":1,"b":2}',
         "43258cff783fe7036d8a43033f830adfc60ec037382473548ac742b888292777"),
    ]
    for value, encoded, digest in vectors:
        assert canonical_bytes(value) == encoded
        assert canonical_digest(value) == digest
    value = {"😀": "é", "\ue000": "e\u0301", "a": "\n\t\"\\", "n": None}
    expected = (b'{"a":"\\n\\t\\\"\\\\","n":null,'
                b'"\\ue000":"e\\u0301","\\ud83d\\ude00":"\\u00e9"}')
    assert canonical_bytes(value) == expected
    assert parse_object(expected) == value
    assert canonical_digest({"s": "é"}) != canonical_digest({"s": "e\u0301"})
    assert canonical_digest(value) == hashlib.sha256(expected).hexdigest()


def test_exact_integer_bounds_and_brackets_in_strings():
    raw = b'{"min":-9223372036854775808,"max":9223372036854775807,"s":"[[[\\\""}'
    value = parse_object(raw)
    assert value["min"] == -(2**63)
    assert value["max"] == 2**63 - 1
    assert parse_object(canonical_bytes(value)) == value


@pytest.mark.parametrize("value", [{1: "x"}, {"x": 1.0}, {"x": b"s"}, {"x": (1,)},
                                    {"x": "\ud800"}, {"x": 2**63}])
def test_canonical_rejects_non_json_or_out_of_range_values(value):
    with pytest.raises(InputError):
        canonical_bytes(value)


def test_cycles_and_output_expansion_are_bounded():
    value = {}
    value["self"] = value
    with pytest.raises(InputError, match="JSON_DEPTH_LIMIT"):
        canonical_bytes(value)
    with pytest.raises(InputError, match="JSON_BYTE_LIMIT"):
        canonical_bytes({"s": "😀" * 3000})
