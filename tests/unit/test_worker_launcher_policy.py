"""Pure policy and mocked rlimit tests. No main(), exec, candidate or real limits."""

import errno
from types import SimpleNamespace

import pytest

from worker import launcher
from worker.launcher import (
    CAPABILITY_FIELDS,
    LIMITS,
    LaunchRejected,
    apply_limits,
    check_process_status,
    close_extra_descriptors,
    fixed_arguments,
    fixed_environment,
)


def test_fixed_paths_interpreter_and_optional_rollup():
    base = fixed_arguments([])
    assert base[:6] == ("/usr/local/bin/python3", "-I", "-B", "-X", "utf8", "/input/pipeline.py")
    assert base[6:] == ("--transactions", "/input/transactions.jsonl", "--customers",
                        "/input/customers.jsonl", "--requirements", "/input/requirements.json",
                        "--ledger", "/output/ledger.jsonl",
                        "--unresolved", "/output/unresolved.jsonl")
    assert fixed_arguments(["--rollups"]) == base + ("--rollups", "/output/rollups.jsonl")


@pytest.mark.parametrize("options", [["--runtime=runc"], ["--rollups", "--rollups"],
                                     ["/host/code.py"], ["--", "--rollups"], ["-c", "pass"]])
def test_caller_cannot_change_path_runtime_or_command(options):
    with pytest.raises(LaunchRejected):
        fixed_arguments(options)


def test_environment_contains_only_fixed_values_and_single_thread_defaults(monkeypatch):
    monkeypatch.setenv("VULTR_API_KEY", "synthetic-noncredential-fixture")
    monkeypatch.setenv("LD_PRELOAD", "/synthetic/never-loaded")
    monkeypatch.setenv("PYTHONPATH", "/synthetic/never-loaded")
    environment = fixed_environment()
    assert set(environment) == {"PATH", "LANG", "LC_ALL", "TZ", "HOME", "TMPDIR",
                                "OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
                                "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "BLIS_NUM_THREADS"}
    assert all(value == "1" for name, value in environment.items() if "THREAD" in name)
    environment["PATH"] = "mutated"
    assert fixed_environment()["PATH"] == "/usr/local/bin:/usr/bin:/bin"


def status():
    return "NoNewPrivs:\t1\n" + "\n".join(name + ":\t0000000000000000"
                                           for name in CAPABILITY_FIELDS)


def test_zero_capabilities_and_no_new_privileges_required():
    check_process_status(status())
    bad = [status().replace("NoNewPrivs:\t1", "NoNewPrivs:\t0"),
           status().replace("CapBnd:\t0000000000000000", "CapBnd:\t1"),
           status().replace("CapPrm:\t0000000000000000", "CapPrm:\tunknown"),
           status() + "\nCapEff:\t0", "NoNewPrivs:\t1"]
    for value in bad:
        with pytest.raises(LaunchRejected):
            check_process_status(value)


class FixtureResource:
    def __init__(self, *, fail=False, mismatch=False):
        self.values, self.fail, self.mismatch = {}, fail, mismatch
        for i, name in enumerate(LIMITS):
            setattr(self, name, i)

    def setrlimit(self, resource_id, pair):
        if self.fail:
            raise OSError("synthetic unsupported limit")
        self.values[resource_id] = pair

    def getrlimit(self, resource_id):
        return (1, 999) if self.mismatch else self.values[resource_id]


def test_hard_and_soft_limits_equal_reviewed_bounds():
    resource = FixtureResource()
    apply_limits(resource)
    assert resource.values[resource.RLIMIT_NPROC] == (64, 64)
    assert resource.values[resource.RLIMIT_NOFILE] == (64, 64)
    assert resource.values[resource.RLIMIT_CORE] == (0, 0)
    assert resource.values[resource.RLIMIT_FSIZE] == (67108864, 67108864)


@pytest.mark.parametrize("fault", ["missing", "set_failure", "readback"])
def test_unavailable_or_ineffective_limits_reject_launch(fault):
    fixture = FixtureResource(fail=fault == "set_failure", mismatch=fault == "readback")
    if fault == "missing":
        del fixture.RLIMIT_NPROC
    with pytest.raises(LaunchRejected):
        apply_limits(fixture)


@pytest.mark.parametrize("fail_close", [False, True])
def test_all_nonstdio_descriptors_closed_even_above_lowered_limit(monkeypatch, fail_close):
    closed = []

    class Entries:
        def __enter__(self):
            return iter(SimpleNamespace(name=str(n)) for n in (0, 1, 2, 3, 7, 1000))

        def __exit__(self, *_):
            pass

    def close(descriptor):
        closed.append(descriptor)
        if descriptor == 3:
            raise OSError(errno.EBADF, "fixture inventory descriptor already closed")
        if fail_close:
            raise OSError(errno.EIO, "fixture failure")

    with monkeypatch.context() as patch:
        patch.setattr(launcher.os, "scandir", lambda _: Entries())
        patch.setattr(launcher.os, "close", close)
        if fail_close:
            with pytest.raises(LaunchRejected, match="DESCRIPTOR_CLOSE_FAILED"):
                close_extra_descriptors()
        else:
            close_extra_descriptors()
    assert closed == ([3, 7] if fail_close else [3, 7, 1000])
