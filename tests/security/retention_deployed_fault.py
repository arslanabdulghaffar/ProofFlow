"""Trusted one-workspace crash probe; installed root-owned, never a candidate program."""

import importlib.util
import json
import os
import re
import sys
from pathlib import Path


def main():
    revision = sys.argv[1]
    if os.geteuid() != 10003 or re.fullmatch(r"[0-9a-f]{64}", revision) is None:
        raise RuntimeError("INVALID_PROBE_BOUNDARY")
    spec = importlib.util.spec_from_file_location(
        "trusted_retention", "/opt/proofflow-retention/" + revision + "/retention.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    plan = json.loads(sys.stdin.buffer.read(32769))
    if len(plan["jobs"]) != 1:
        raise RuntimeError("ONE_DISPOSABLE_JOB_REQUIRED")
    interrupted = False

    def crash(fd):
        nonlocal interrupted
        if "intent.json" not in os.listdir(fd):
            raise RuntimeError("EXPECTED_REAL_EXECUTION_JOURNAL")
        os.unlink("intent.json", dir_fd=fd)
        os.fsync(fd)
        interrupted = True
        raise OSError("EXPECTED_PARTIAL_RETIREMENT")

    module.empty_tree = crash
    try:
        module.retire(
            plan, Path("/run/proofflow-retention-assets"), Path("/run/proofflow-retention-jobs")
        )
    except OSError as error:
        if not interrupted or str(error) != "EXPECTED_PARTIAL_RETIREMENT":
            raise
    else:
        raise RuntimeError("FAULT_NOT_EXERCISED")
    print(json.dumps({"partial_journal_retirement": True, "metadata_completion_claimed": False}))


if __name__ == "__main__":
    main()
