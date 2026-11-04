"""Trusted Linux file fixtures, never candidate code execution."""

import hashlib
import os
from pathlib import Path
from uuid import uuid4

import pytest

from api.app.evidence_bundle import JournalOutputs
from api.app.product_store import ProductFailure

pytestmark = pytest.mark.skipif(os.name != "posix", reason="descriptor walks and retention flock")


@pytest.mark.parametrize("attack", ["none", "symlink", "hardlink", "deleted", "hash", "special"])
def test_artifact_walk_rejects_links_tombstones_and_tampering(tmp_path, attack):
    execution, job = uuid4().hex, uuid4().hex
    target = tmp_path / execution / "captures" / execution
    target.mkdir(parents=True, mode=0o700)
    for directory in (target, target.parent, target.parent.parent, tmp_path):
        directory.chmod(0o700)
    for name in ("ledger.jsonl", "unresolved.jsonl"):
        (target / name).write_bytes(b"")
        (target / name).chmod(0o600)
    result = {
        "intent": {"execution": execution, "job": job},
        "semantic": {
            "report": {
                "result": {
                    "output_hashes": {
                        name: hashlib.sha256(b"").hexdigest()
                        for name in ("ledger.jsonl", "unresolved.jsonl")
                    }
                }
            }
        },
    }
    ledger = target / "ledger.jsonl"
    if attack == "symlink":
        ledger.unlink()
        ledger.symlink_to(target / "unresolved.jsonl")
    elif attack == "hardlink":
        os.link(ledger, target / "extra")
    elif attack == "deleted":
        (tmp_path / (".deleted-" + job)).touch()
    elif attack == "hash":
        ledger.write_bytes(b"tampered")
    elif attack == "special":
        ledger.unlink()
        os.mkfifo(ledger, 0o600)
    if attack == "none":
        assert JournalOutputs(Path(tmp_path)).read(result) == {
            "ledger.jsonl": b"",
            "unresolved.jsonl": b"",
        }
    else:
        with pytest.raises(ProductFailure):
            JournalOutputs(Path(tmp_path)).read(result)
