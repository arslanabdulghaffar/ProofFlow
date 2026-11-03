"""Read-only kernel observations for fixed project execution units, on worker only."""

import json
import re
import time
from pathlib import Path

observed = {}
deadline = time.monotonic() + 35
while time.monotonic() < deadline:
    for directory in Path("/sys/fs/cgroup/system.slice").glob("proofflow-exec-*.service"):
        if not re.fullmatch(r"proofflow-exec-[0-9a-f]{32}\.service", directory.name):
            continue
        try:
            maximum = int((directory / "pids.max").read_text())
            current = int((directory / "pids.current").read_text())
            events = dict(
                line.split() for line in (directory / "pids.events").read_text().splitlines()
            )
            denied = int(events["max"])
        except FileNotFoundError:
            continue
        if maximum != 128 or not 0 <= current <= 128 or denied < 0:
            raise RuntimeError("KERNEL_PID_POLICY_MISMATCH")
        old = observed.setdefault(
            directory.name,
            {"pids_max": maximum, "sampled_peak": 0, "denied_by_kernel": 0, "samples": 0},
        )
        old["sampled_peak"] = max(current, old["sampled_peak"])
        old["denied_by_kernel"] = max(denied, old["denied_by_kernel"])
        old["samples"] += 1
    time.sleep(0.01)
Path("/var/lib/proofflow-setup/pids-observed.json").write_text(json.dumps(observed, sort_keys=True))
