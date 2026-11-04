"""Explicit root Linux integration probes with reviewed diagnostic code only.

These are containment fixtures, never a production selector or candidate runner.
The exact production service properties and immutable verifier image are used.
"""

import argparse
import json
import os
import subprocess
import time
from pathlib import Path

from verifier.host import DIRECTORY, UNIT, _state, _stop, properties, run
from verifier.protocol import MAX_RESPONSE
from worker.host import HOST_ENV, command, synced_write

ISOLATION = """
import errno,json,os,socket
assert os.getuid()==10002 and os.getgid()==10002
print('uid',flush=True)
status=open('/proc/self/status').read()
assert 'CapEff:\\t0000000000000000' in status and 'NoNewPrivs:\\t1' in status
print('caps',flush=True)
assert not os.path.exists('/etc/proofflow') and not os.path.exists('/var/run/docker.sock')
assert not os.path.exists('/var/lib/proofflow-verifier/request')
assert not any('KEY' in key or 'PASSWORD' in key or 'TOKEN' in key for key in os.environ)
print('files',flush=True)
for family in (socket.AF_INET,socket.AF_INET6,socket.AF_UNIX):
    try: socket.socket(family,socket.SOCK_STREAM)
    except OSError as error: assert error.errno in (errno.EPERM,errno.EAFNOSUPPORT,errno.EACCES)
    else: raise AssertionError('network permitted')
try: open('/opt/proofflow/write-marker','w')
except OSError as error: assert error.errno in (errno.EROFS,errno.EACCES)
else: raise AssertionError('writable root')
print('passed',flush=True)
"""


def fixture(image, code, *, disconnect=False):
    _stop()
    for name in ("request", "response"):
        (DIRECTORY / name).unlink(missing_ok=True)
        synced_write(DIRECTORY / name, b"")
    plan = properties(image)
    started = time.monotonic()
    args = ["/usr/bin/systemd-run", "--quiet", "--unit=" + UNIT,
            *["--property=" + key + "=" + value for key, value in plan.items()],
            "/usr/local/bin/python3", "-I", "-B", "-c", code]
    try:
        if disconnect:
            # This short-lived controller exits once systemd accepted the service.
            process = subprocess.Popen(  # noqa: S603 - fixed trusted diagnostic fixtures
                args, env=HOST_ENV, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            assert process.wait(timeout=8) == 0
        else:
            command(args, timeout=8)
        state = _state()
        group = Path("/sys/fs/cgroup" + state["ControlGroup"])
        if state["SubState"] == "running":
            assert (group / "memory.max").read_text().strip() == "536870912"
            assert (group / "memory.swap.max").read_text().strip() == "0"
            assert (group / "pids.max").read_text().strip() == "32"
            quota, period = (group / "cpu.max").read_text().split()
            assert quota == period
        while state["SubState"] not in ("exited", "failed", "dead"):
            assert time.monotonic() - started < 18, "independent watchdog failed"
            time.sleep(0.1)
            state = _state()
        raw = (DIRECTORY / "response").read_bytes()
        assert len(raw) <= MAX_RESPONSE
        return state, raw, time.monotonic() - started
    finally:
        _stop()
        for name in ("request", "response"):
            (DIRECTORY / name).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    assert os.geteuid() == 0
    # Production invocation establishes rootfs digest/private slot and rejection path.
    receipt = run(b'{}', image=args.image, image_sha256=args.sha256)
    assert receipt["report"]["status"] == "rejected" and receipt["cleanup_confirmed"] is True
    checks = ["fixed_protocol_rejection"]
    state, raw, _ = fixture(args.image, ISOLATION)
    assert state["Result"] == "success" and state["ExecMainStatus"] == "0", (state, raw)
    assert raw == b"uid\ncaps\nfiles\npassed\n"
    checks.append("uid_capabilities_secret_files_readonly_ipv4_ipv6_unix_denied")
    state, _, elapsed = fixture(args.image, "while True: pass", disconnect=True)
    assert state["Result"] == "timeout" and 9 <= elapsed <= 18
    checks.append("independent_wall_timeout_after_controller_exit")
    state, _, _ = fixture(args.image, "x=bytearray(700*1024*1024)")
    assert state["Result"] == "oom-kill"
    checks.append("memory_swap_limit_oom_cleanup")
    state, raw, _ = fixture(args.image, "import os\nwhile True: os.write(1,b'x'*65536)")
    assert state["Result"] != "success" and len(raw) == MAX_RESPONSE
    checks.append("output_file_hard_limit")
    code = """
import errno,os,time
children=[]
try:
    for i in range(40):
        pid=os.fork()
        if not pid: time.sleep(60); os._exit(0)
        children.append(pid)
except OSError as error:
    assert error.errno==errno.EAGAIN
    print('task_denied',flush=True)
else: raise AssertionError('task ceiling failed')
"""
    state, raw, _ = fixture(args.image, code)
    assert state["ExecMainStatus"] == "0" and raw == b"task_denied\n"
    checks.append("task_ceiling_and_descendant_cleanup")
    assert not (Path("/sys/fs/cgroup/system.slice") / UNIT).exists()
    assert sorted(p.name for p in DIRECTORY.iterdir()) == ["lock"]
    print(json.dumps({"fixture_only": True, "rootfs_sha256": args.sha256,
                      "checks": checks, "passed": len(checks), "cleanup_confirmed": True}))


if __name__ == "__main__":
    main()
