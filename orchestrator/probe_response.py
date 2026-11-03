"""Bounded parsing of untrusted provider bytes, never execution or verification."""

import hashlib
import json
import math
import re
from dataclasses import dataclass

from orchestrator.probe_plan import INPUT_TOKEN_BOUND

MAX_RESPONSE_BYTES = 256 * 1024
MAX_CONTENT_BYTES = 64 * 1024
MAX_JSON_DEPTH = 32
MAX_JSON_NODES = 8192


class ProviderResponseError(Exception):
    """Fixed diagnostic code; never attach raw response text to an exception."""


@dataclass(frozen=True)
class ReportedUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(frozen=True)
class ProbeResponse:
    response_sha256: str
    provider_id: str
    model: str
    content_json: bytes
    usage: ReportedUsage | None


def _pairs(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProviderResponseError("JSON_DUPLICATE_KEY")
        result[key] = value
    return result


def _integer(text: str) -> int:
    if len(text) > 20:
        raise ProviderResponseError("JSON_INTEGER_TOO_LONG")
    return int(text)


def _constant(_: str):
    raise ProviderResponseError("JSON_NONFINITE_NUMBER")


def strict_json_object(raw: bytes, *, max_bytes: int) -> dict:
    if type(raw) is not bytes or not raw or len(raw) > max_bytes:
        raise ProviderResponseError("JSON_BYTE_LIMIT")
    try:
        text = raw.decode("utf-8", errors="strict")
        # Bound depth before invoking the recursive JSON decoder. Strings and
        # escaped quotes do not alter nesting; the decoder validates grammar.
        depth = 0
        in_string = escaped = False
        for char in text:
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
            elif char == '"':
                in_string = True
            elif char in "[{":
                depth += 1
                if depth > MAX_JSON_DEPTH:
                    raise ProviderResponseError("JSON_DEPTH_LIMIT")
            elif char in "]}":
                depth -= 1
        value = json.loads(text, object_pairs_hook=_pairs, parse_int=_integer,
                           parse_constant=_constant)
        if type(value) is not dict:
            raise ProviderResponseError("JSON_OBJECT_REQUIRED")
        pending = [value]
        nodes = 0
        while pending:
            item = pending.pop()
            nodes += 1
            if nodes > MAX_JSON_NODES:
                raise ProviderResponseError("JSON_NODE_LIMIT")
            if isinstance(item, dict):
                pending.extend(item.keys())
                pending.extend(item.values())
            elif isinstance(item, list):
                pending.extend(item)
            elif isinstance(item, str):
                item.encode("utf-8", errors="strict")  # Reject escaped lone surrogates.
            elif isinstance(item, float) and not math.isfinite(item):
                raise ProviderResponseError("JSON_NONFINITE_NUMBER")
        return value
    except (UnicodeError, ValueError, RecursionError):
        raise ProviderResponseError("INVALID_JSON") from None


def parse_probe_response(raw: bytes, *, model: str, completion_bound: int) -> ProbeResponse:
    value = strict_json_object(raw, max_bytes=MAX_RESPONSE_BYTES)
    identifier = value.get("id")
    if (type(identifier) is not str
            or not re.fullmatch(r"chatcmpl-[A-Za-z0-9_-]{1,128}", identifier)
            or value.get("object") != "chat.completion" or value.get("model") != model
            or "error" in value):
        raise ProviderResponseError("INVALID_PROVIDER_ENVELOPE")
    choices = value.get("choices")
    if type(choices) is not list or len(choices) != 1 or type(choices[0]) is not dict:
        raise ProviderResponseError("INVALID_PROVIDER_CHOICES")
    choice = choices[0]
    if type(choice.get("index")) is not int or choice["index"] != 0:
        raise ProviderResponseError("INVALID_PROVIDER_CHOICES")
    if choice.get("finish_reason") != "stop":
        raise ProviderResponseError("PROVIDER_COMPLETION_NOT_STOPPED")
    message = choice.get("message")
    if (type(message) is not dict or message.get("role") != "assistant"
            or message.get("tool_calls") not in (None, [])
            or message.get("function_call") is not None
            or message.get("refusal") not in (None, "")
            or type(message.get("content")) is not str):
        raise ProviderResponseError("INVALID_PROVIDER_MESSAGE")
    content = message["content"].encode("utf-8")
    strict_json_object(content, max_bytes=MAX_CONTENT_BYTES)
    usage = value.get("usage")
    reported = None
    if usage is not None:
        if type(usage) is not dict:
            raise ProviderResponseError("INVALID_PROVIDER_USAGE")
        counts = tuple(usage.get(k) for k in
                       ("prompt_tokens", "completion_tokens", "total_tokens"))
        if (any(type(n) is not int or n < 0 for n in counts)
                or counts[0] > INPUT_TOKEN_BOUND or counts[1] > completion_bound
                or counts[2] != counts[0] + counts[1]):
            raise ProviderResponseError("INVALID_PROVIDER_USAGE")
        reported = ReportedUsage(*counts)
    # Usage is provider-reported, not billing evidence; no reservation settlement.
    return ProbeResponse(hashlib.sha256(raw).hexdigest(), identifier, model, content, reported)
