"""Manifest-only checks; no runtime install, runtime invocation or guest execution."""

import hashlib
import json
from pathlib import Path

import pytest

from worker.protocol import SupervisorError
from worker.runtime_bundle import parse_manifest

MANIFEST = Path(__file__).resolve().parents[2] / "infra/gvisor/runsc-release.json"


def test_exact_reviewed_bundle_contains_companions():
    raw = MANIFEST.read_bytes()
    expected = json.loads(raw)["members"]["runsc"]["sha256"]
    parsed = parse_manifest(raw, hashlib.sha256(raw).hexdigest(), expected)
    assert len(parsed["members"]) == 8 and "gvisor-bin/gvisor_sentry" in parsed["members"]


@pytest.mark.parametrize("fault", ["missing", "extra", "path", "bool", "hash", "launcher"])
def test_bad_bundle_rejected(fault):
    value = json.loads(MANIFEST.read_bytes())
    launcher = value["members"]["runsc"]["sha256"]
    if fault == "missing":
        del value["members"]["gvisor-bin/gvisor_sentry"]
    elif fault == "extra":
        value["members"]["extra"] = value["members"]["runsc"]
    elif fault == "path":
        value["members"]["../escape"] = value["members"].pop("runsc")
    elif fault == "bool":
        value["members"]["runsc"]["bytes"] = True
    elif fault == "hash":
        value["members"]["runsc"]["sha256"] = "untrusted"
    else:
        launcher = "a" * 64
    raw = json.dumps(value).encode()
    with pytest.raises(SupervisorError):
        parse_manifest(raw, hashlib.sha256(raw).hexdigest(), launcher)


def test_manifest_change_invalidates_pin():
    raw = MANIFEST.read_bytes()
    with pytest.raises(SupervisorError, match="RUNTIME_BUNDLE_DIGEST_MISMATCH"):
        parse_manifest(raw + b"\n", hashlib.sha256(raw).hexdigest(), "a" * 64)
