"""Synthetic provider envelopes; no real inference or model success asserted."""

import hashlib
import json

import pytest

from orchestrator.probe_response import (
    MAX_RESPONSE_BYTES,
    ProviderResponseError,
    parse_probe_response,
    strict_json_object,
)

MODEL = "qwen3.8-27b"


def envelope():
    return {"id": "chatcmpl-synthetic", "object": "chat.completion", "model": MODEL,
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": '{"answer":7}'}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}


def parse(value):
    return parse_probe_response(json.dumps(value).encode(), model=MODEL, completion_bound=512)


def test_exact_content_and_raw_response_hash_and_reported_usage():
    value = envelope()
    result = parse(value)
    assert result.content_json == b'{"answer":7}'
    assert result.response_sha256 == hashlib.sha256(json.dumps(value).encode()).hexdigest()
    assert result.usage.prompt_tokens == 10 and result.usage.total_tokens == 15


def test_missing_usage_stays_unknown_and_reasoning_is_not_double_counted():
    value = envelope()
    value["usage"]["completion_tokens_details"] = {"reasoning_tokens": 3}
    assert parse(value).usage.total_tokens == 15
    del value["usage"]
    assert parse(value).usage is None


@pytest.mark.parametrize("reason", ["length", "tool_calls", "error", "content_filter", None])
def test_nonstop_completion_rejected(reason):
    value = envelope()
    value["choices"][0]["finish_reason"] = reason
    with pytest.raises(ProviderResponseError, match="PROVIDER_COMPLETION_NOT_STOPPED"):
        parse(value)


@pytest.mark.parametrize("field,value", [("tool_calls", [{"name": "shell"}]),
                                         ("function_call", {"name": "shell"}),
                                         ("refusal", "no"), ("role", "system"),
                                         ("content", None)])
def test_no_tool_or_refusal_or_nonassistant_content(field, value):
    response = envelope()
    response["choices"][0]["message"][field] = value
    with pytest.raises(ProviderResponseError):
        parse(response)


@pytest.mark.parametrize("counts", [(True, 5, 6), (-1, 5, 4), (10, 513, 523),
                                    (262145, 5, 262150), (10, 5, 99), (None, 5, 5)])
def test_invalid_usage_never_becomes_zero_or_success(counts):
    value = envelope()
    value["usage"] = dict(zip(("prompt_tokens", "completion_tokens", "total_tokens"),
                             counts, strict=True))
    with pytest.raises(ProviderResponseError, match="INVALID_PROVIDER_USAGE"):
        parse(value)


@pytest.mark.parametrize("raw", [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1e999}',
                                 b'{"x":123456789012345678901}', b'{"x":"\\ud800"}',
                                 b'{} trailing', b'[]', b'\xff', b'{'])
def test_strict_json_rejects_ambiguous_or_invalid_data(raw):
    with pytest.raises(ProviderResponseError):
        strict_json_object(raw, max_bytes=MAX_RESPONSE_BYTES)


def test_structural_limits_and_escaped_quote_depth():
    for raw in (b'{"x":' + b'[' * 33 + b'0' + b']' * 33 + b'}',
                json.dumps({"x": [0] * 8192}).encode(), b' ' * (MAX_RESPONSE_BYTES + 1)):
        with pytest.raises(ProviderResponseError):
            strict_json_object(raw, max_bytes=MAX_RESPONSE_BYTES)
    assert strict_json_object(b'{"x":"[\\\"{]"}', max_bytes=100) == {"x": '["{]'}


def test_wrong_model_multiple_choices_and_nested_content_duplicate_fail():
    value = envelope()
    value["model"] = "other-provider"
    with pytest.raises(ProviderResponseError):
        parse(value)
    value = envelope()
    value["choices"].append(value["choices"][0])
    with pytest.raises(ProviderResponseError):
        parse(value)
    value = envelope()
    value["choices"][0]["message"]["content"] = '{"answer":7,"answer":0}'
    with pytest.raises(ProviderResponseError, match="JSON_DUPLICATE_KEY"):
        parse(value)
