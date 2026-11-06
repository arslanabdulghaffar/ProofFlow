"""Fixed Linux data-only recovery into a temporary private directory, then cleanup."""

import base64
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from orchestrator.asset_backup import open_backup
from orchestrator.asset_recovery import materialize


def main():
    raw = sys.stdin.buffer.read(96 * 1024 * 1024 + 1)
    if len(raw) > 96 * 1024 * 1024:
        raise RuntimeError("RECOVERY_INPUT_LIMIT")
    value = json.loads(raw)
    if set(value) != {"envelope", "key", "current"}:
        raise RuntimeError("RECOVERY_INPUT_INVALID")
    payload = open_backup(
        base64.b64decode(value["envelope"], validate=True),
        base64.b64decode(value["key"], validate=True),
        now=datetime.now(UTC),
    )
    with TemporaryDirectory(prefix="proofflow-asset-recovery-") as target:
        fd = os.open(target, os.O_RDONLY | os.O_DIRECTORY)
        try:
            result = materialize(fd, payload, value["current"], now=datetime.now(UTC))
        finally:
            os.close(fd)
    if Path(target).exists():
        raise RuntimeError("RECOVERY_FIXTURE_CLEANUP_FAILED")
    print(json.dumps({**result, "temporary_asset_cleanup": "confirmed"}))


if __name__ == "__main__":
    main()
