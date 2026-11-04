"""Synthetic bundle bytes only. No archive member is extracted or executed."""

import base64
import hashlib
import io
import json
import zipfile
from types import SimpleNamespace
from uuid import uuid4

from api.app.evidence_bundle import build_bundle


def test_hash_inventory_exact_source_outputs_and_protected_redaction():
    workspace = uuid4()
    source = {
        "pipeline": b"untrusted original",
        "contract": b"{}",
        "transactions": b"private synthetic source",
        "customers": b"private customer source",
    }
    stored = {hashlib.sha256(raw).hexdigest(): raw for raw in source.values()}
    report = {
        "semantic": {
            "report": {
                "result": {
                    "comparison": "match",
                    "output_hashes": {
                        "ledger.jsonl": hashlib.sha256(b"data\n").hexdigest(),
                        "unresolved.jsonl": hashlib.sha256(b"").hexdigest(),
                    },
                }
            }
        }
    }
    hidden = {
        "semantic": {
            "report": {
                "result": {
                    "comparison": "match",
                    "operation": "verify",
                    "findings": [{"expected_owner": "SECRET_OWNER"}],
                    "seed": "SECRET_SEED",
                }
            }
        }
    }
    record = {
        "assets": [
            {"kind": kind, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
            for kind, raw in source.items()
        ],
        "candidates": [{"ordinal": 1, "source": "untrusted model bytes"}],
        "original": {"report": report},
        "original_events": [],
        "executions": [
            {"purpose": "candidate", "attempt": 1, "result": report},
            {"purpose": "canary_ownership", "result": hidden},
        ],
        "calls": [
            {
                "request_id": str(uuid4()),
                "response_base64": base64.b64encode(
                    json.dumps(
                        {
                            "id": "provider-response-id",
                            "model": "reviewed-model",
                            "usage": {"total_tokens": 3},
                            "choices": [{"message": {"reasoning": "PRIVATE_REASONING"}}],
                        }
                    ).encode()
                ).decode(),
            }
        ],
        "repair": {"id": str(uuid4()), "state": "AWAITING_APPROVAL", "mode": "ai_repair"},
    }
    journals = SimpleNamespace(read=lambda _: {"ledger.jsonl": b"data\n", "unresolved.jsonl": b""})
    blob = build_bundle(
        record, workspace, SimpleNamespace(read=lambda w, digest: stored[digest]), journals
    )
    assert blob == build_bundle(
        record, workspace, SimpleNamespace(read=lambda w, d: stored[d]), journals
    )
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["activation_approved"] is False
        assert manifest["protected_canary_material_included"] is False
        assert set(archive.namelist()) == {f["path"] for f in manifest["files"]} | {"manifest.json"}
        for item in manifest["files"]:
            raw = archive.read(item["path"])
            assert hashlib.sha256(raw).hexdigest() == item["sha256"] and len(raw) == item["bytes"]
            assert not any(
                secret in raw for secret in (b"SECRET_OWNER", b"SECRET_SEED", b"PRIVATE_REASONING")
            )
        assert archive.read("candidate/pipeline.py") == b"untrusted model bytes"
        assert archive.read("original/pipeline.py") == source["pipeline"]
        assert archive.read("input/transactions.csv") == source["transactions"]
        assert all(not ((item.external_attr >> 16) & 0o111) for item in archive.infolist())
