"""Pure protocol rejection and transfer-integrity checks; no candidate execution."""

import base64
import hashlib
from uuid import uuid4

import pytest

from orchestrator.worker_client import validate_capture
from worker.protocol import SupervisorError
from worker.service import WorkerService, decode_input
from worker.wire import private_address, strict_json


@pytest.mark.parametrize("data", [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}',
                                 b'{"a":' + b'[' * 13 + b'0' + b']' * 13 + b'}',
                                 b'[]', b'{"bad":"\xff"}'])
def test_strict_wire_rejects_ambiguous_or_unbounded_json(data):
    with pytest.raises(SupervisorError):
        strict_json(data)


@pytest.mark.parametrize("value", ["127.0.0.1", "0.0.0.0", "169.254.169.254", "8.8.8.8",  # noqa: S104
                                  "worker.example", "::1"])
def test_release_endpoint_must_be_literal_rfc1918(value):
    with pytest.raises(SupervisorError):
        private_address(value)


@pytest.mark.parametrize("message", [{"v": True, "op": "status"}, {"v": 1, "op": "shell"},
                                    {"v": 1, "op": "fence", "job": "../host", "generation": 1},
                                    {"v": 1, "op": "status", "path": "/etc/passwd"}])
def test_invalid_operations_never_reach_supervisor(message):
    with pytest.raises(SupervisorError):
        WorkerService(None).dispatch(message)


@pytest.mark.parametrize("value", ["YQ", "YQ==\n", "YR==", "!!!!", 0])
def test_base64_is_canonical_and_strict(value):
    with pytest.raises(SupervisorError):
        decode_input(value, 10)


def capture():
    execution, job = uuid4(), uuid4()
    data = {"ledger.jsonl": b'{"fixture":true}\n', "unresolved.jsonl": b""}
    receipt = {"execution": execution.hex, "job": job.hex, "generation": 1,
               "manifest": "a" * 64, "cleanup": "confirmed", "collected": True,
               "verification": "NOT_PERFORMED", "logs": [],
               "files": [{"name": name, "bytes": len(value),
                          "sha256": hashlib.sha256(value).hexdigest()}
                         for name, value in data.items()]}
    return execution, job, {"receipt": receipt, "files": {
        name: base64.b64encode(value).decode() for name, value in data.items()}}


@pytest.mark.parametrize("fault", ["hash", "extra", "job", "cleanup", "verified", "size_bool"])
def test_capture_rejects_corruption_or_wrong_identity(fault):
    execution, job, result = capture()
    assert validate_capture(result, execution, job, 1, "a" * 64)["unresolved.jsonl"] == b""
    if fault == "hash":
        result["files"]["ledger.jsonl"] = base64.b64encode(b"changed").decode()
    elif fault == "extra":
        result["files"]["../outside"] = ""
    elif fault == "size_bool":
        result["receipt"]["files"][0]["bytes"] = True
    else:
        field, value = {"job": ("job", uuid4().hex), "cleanup": ("cleanup", "uncertain"),
                        "verified": ("verification", "PASS")}[fault]
        result["receipt"][field] = value
    with pytest.raises(SupervisorError):
        validate_capture(result, execution, job, 1, "a" * 64)
