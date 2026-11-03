"""Fixed in-container bootstrap; invoke only on the designated isolated worker.

This does not establish runtime identity, network denial, mount quotas, a wall
watchdog or writer termination. The supervisor must enforce and probe those.
Never invoke main() on the control/development host. Local tests use pure policy
helpers and mock resource APIs only; they never exec a candidate or set limits.
"""

import errno
import os
import stat
import sys

CANDIDATE_UID = 10001
LIMITS = {"RLIMIT_CORE": 0, "RLIMIT_NOFILE": 64, "RLIMIT_NPROC": 64,
          "RLIMIT_FSIZE": 64 * 1024 * 1024}
CAPABILITY_FIELDS = ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")


class LaunchRejected(Exception):
    """Fixed bootstrap failure; never include candidate bytes or host paths."""


def fixed_arguments(options: list[str]) -> tuple[str, ...]:
    if options not in ([], ["--rollups"]):
        raise LaunchRejected("UNSUPPORTED_LAUNCH_OPTION")
    args = ("/usr/local/bin/python3", "-I", "-B", "-X", "utf8", "/input/pipeline.py",
            "--transactions", "/input/transactions.jsonl",
            "--customers", "/input/customers.jsonl",
            "--requirements", "/input/requirements.json",
            "--ledger", "/output/ledger.jsonl", "--unresolved", "/output/unresolved.jsonl")
    return args + (("--rollups", "/output/rollups.jsonl") if options else ())


def fixed_environment() -> dict[str, str]:
    # Construct from literals, never copy the controller/launcher environment.
    # Supervisor must also prevent environment injection BEFORE bootstrap starts.
    return {"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
            "TZ": "UTC", "HOME": "/scratch", "TMPDIR": "/scratch",
            "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1", "VECLIB_MAXIMUM_THREADS": "1", "BLIS_NUM_THREADS": "1"}


def check_process_status(text: str) -> None:
    fields = {}
    for line in text.splitlines():
        key, separator, value = line.partition(":")
        if separator:
            if key in fields:
                raise LaunchRejected("DUPLICATE_PROCESS_STATUS")
            fields[key] = value.strip()
    try:
        if (fields["NoNewPrivs"] != "1"
                or any(int(fields[field], 16) != 0 for field in CAPABILITY_FIELDS)):
            raise LaunchRejected("UNSAFE_PROCESS_PRIVILEGES")
    except (KeyError, ValueError):
        raise LaunchRejected("INVALID_PROCESS_STATUS") from None


def apply_limits(resource_api) -> None:
    for name, bound in LIMITS.items():
        try:
            resource_id = getattr(resource_api, name)
            resource_api.setrlimit(resource_id, (bound, bound))
            if resource_api.getrlimit(resource_id) != (bound, bound):
                raise LaunchRejected("LIMIT_READBACK_MISMATCH")
        except (AttributeError, OSError, ValueError):
            raise LaunchRejected("REQUIRED_LIMIT_UNAVAILABLE") from None


def close_extra_descriptors() -> None:
    descriptors = []
    with os.scandir("/proc/self/fd") as entries:
        for entry in entries:
            if len(descriptors) >= 1024 or not entry.name.isascii() or not entry.name.isdecimal():
                raise LaunchRejected("INVALID_DESCRIPTOR_INVENTORY")
            descriptor = int(entry.name)
            if descriptor >= 3:
                descriptors.append(descriptor)
    # Inventory includes scandir's now-closed descriptor. Close every inherited
    # high descriptor too, including those above the newly lowered NOFILE limit.
    for descriptor in descriptors:
        try:
            os.close(descriptor)
        except OSError as error:
            if error.errno != errno.EBADF:
                raise LaunchRejected("DESCRIPTOR_CLOSE_FAILED") from None


def main() -> int:
    try:
        args = fixed_arguments(sys.argv[1:])
        if (sys.platform != "linux" or os.getpid() != 1
                or os.getresuid() != (CANDIDATE_UID,) * 3
                or os.getresgid() != (CANDIDATE_UID,) * 3
                or any(group != CANDIDATE_UID for group in os.getgroups())):
            raise LaunchRejected("UNSAFE_LAUNCH_IDENTITY")
        with open("/proc/self/status", encoding="ascii") as source:
            check_process_status(source.read(32 * 1024))
        for name in ("pipeline.py", "transactions.jsonl", "customers.jsonl", "requirements.json"):
            info = os.stat("/input/" + name, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise LaunchRejected("UNSAFE_STAGED_INPUT")
        import resource  # Unix only; not imported by portable policy tests.
        apply_limits(resource)
        close_extra_descriptors()
        os.umask(0o077)
        os.chdir("/scratch")
        os.execve(args[0], args, fixed_environment())  # noqa: S606 - fixed isolated-worker argv
    except (LaunchRejected, OSError, ValueError):
        os.write(2, b"WORKER_LAUNCH_REJECTED\n")
        return 78
    return 78  # execve must never return success without replacing this process.


if __name__ == "__main__":
    raise SystemExit(main())
