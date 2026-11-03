"""Deployed infrastructure fixtures only; stops on the first failed critical gate."""

import json
import sys
import time

from vultr_phase1 import PRIVATE, ROOT, Admin

a = Admin()
r = a.host(
    "control",
    "umask 077; cat > /opt/proofflow-control/probe_worker_controller.py",
    stdin=(ROOT / "scripts/probe_worker_controller.py").read_bytes(),
)
if r.returncode:
    raise RuntimeError("PROBE_UPLOAD_FAILED")
out = PRIVATE / "evidence"
out.mkdir(exist_ok=True)
names = sys.argv[1:] or [
    "filesystem",
    "forks",
    "threads",
    "cpu",
    "storage",
    "inodes",
    "logs",
    "symlink",
    "fifo",
    "hardlink",
    "extra",
    "output_bytes",
    "output_lines",
    "memory",
    "timeout",
    "descendants",
    "benign",
]
allowed = {
    "filesystem",
    "forks",
    "threads",
    "cpu",
    "storage",
    "inodes",
    "logs",
    "symlink",
    "fifo",
    "hardlink",
    "extra",
    "output_bytes",
    "output_lines",
    "memory",
    "timeout",
    "descendants",
    "benign",
}
if not set(names) <= allowed:
    raise RuntimeError("UNKNOWN_DEPLOYED_PROBE")
for name in names:
    started = time.monotonic()
    r = a.host(
        "control",
        "/usr/bin/python3 -I -B /opt/proofflow-control/probe_worker_controller.py " + name,
        timeout=90,
    )
    if r.returncode:
        print("CONTROLLER_PROBE_FAILURE", name, r.stderr.decode()[-1500:], flush=True)
        raise SystemExit(1)
    result = json.loads(r.stdout)
    result["controller_roundtrip_seconds"] = round(time.monotonic() - started, 3)
    (out / (name + "-" + result["execution"] + ".json")).write_text(
        json.dumps(result, sort_keys=True, indent=2)
    )
    rec = result["receipt"]
    obs = result.get("observed", {})
    if rec["cleanup"] != "confirmed":
        raise RuntimeError("CRITICAL_CLEANUP_GATE_FAILED")
    if name in {"symlink", "fifo", "hardlink", "extra", "output_bytes", "output_lines"}:
        passed = rec["collected"] is False and rec["outcome"] == "output_rejected"
    elif name == "forks":
        passed = (
            obs.get("children_started") == 63
            and obs.get("errno") == 11
            and obs.get("hard_limit_raise_succeeded") is False
        )
    elif name == "threads":
        passed = (
            obs.get("threads_started") == 63
            and obs.get("error") is not None
            and obs.get("hard_limit_raise_succeeded") is False
        )
    elif name == "filesystem":
        passed = (
            all(
                obs.get(n) in (2, 13, 30) for n in ("host_marker", "host_credential", "input_write")
            )
            and obs.get("root_write") == 30
        )
    elif name == "cpu":
        cpu = rec["resource_observation"]["last_observed"]["cpu"]
        passed = (
            obs.get("elapsed_seconds", 0) >= 3
            and cpu["nr_throttled"] > 0
            and cpu["usage_usec"] >= 2000000
        )
    elif name == "storage":
        passed = (
            all(
                63 * 1024 * 1024 <= obs.get(n, {}).get("bytes_written", 0) <= 64 * 1024 * 1024
                and obs[n]["errno"] == 28
                for n in ("/scratch", "/output", "/dev/shm", "/tmp", "combined_aliases")  # noqa: S108
            )
            and obs.get("aliases_share_bytes") is True
        )
    elif name == "inodes":
        passed = all(
            1000 <= obs.get(n, {}).get("files_created", 0) <= 1023 and obs[n]["errno"] == 28
            for n in ("/scratch", "/output")
        )
    elif name == "logs":
        passed = (
            rec["collected"]
            and sum(x["retained"] for x in rec["logs"]) == 102400
            and sum(x["received"] for x in rec["logs"]) >= 524288
        )
    elif name == "memory":
        passed = (
            rec.get("unit_result") == "oom-kill"
            or rec.get("resource_observation", {})
            .get("last_observed", {})
            .get("memory_events", {})
            .get("oom_kill", 0)
            > 0
        )
    elif name in {"timeout", "descendants"}:
        passed = rec["outcome"] == "timeout" and result["controller_roundtrip_seconds"] < 30
    else:
        passed = obs.get("sums") == {"A": 150, "B": 350} and obs.get("uid") == 10001
    print(
        json.dumps(
            {
                "probe": name,
                "acceptance": passed,
                "observed": obs,
                "outcome": rec["outcome"],
                "error": rec.get("error"),
                "cleanup": rec["cleanup"],
                "seconds": result["controller_roundtrip_seconds"],
            }
        ),
        flush=True,
    )
    if not passed:
        print("CRITICAL_GATE_FAILED_STOPPING_DEPENDENT_PROBES", flush=True)
        raise SystemExit(1)
a.close()
