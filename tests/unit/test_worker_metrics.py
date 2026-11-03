"""Pure counter-parser fixtures; no host resource changes or guest execution."""

import pytest

from worker.metrics import CgroupMetrics, counters
from worker.protocol import SupervisorError


def test_counters_preserve_actual_values():
    assert counters("usage_usec 42\nnr_throttled 3\n", {"usage_usec"}) == {
        "usage_usec": 42, "nr_throttled": 3,
    }


def test_deployed_ubuntu_cpu_stat_namespaced_counter():
    actual = ("usage_usec 3109479\nuser_usec 2336177\nsystem_usec 773302\n"
              "core_sched.force_idle_usec 0\nnr_periods 669\nnr_throttled 1\n"
              "throttled_usec 51921\nnr_bursts 0\nburst_usec 0\n")
    result = counters(actual, {"usage_usec", "nr_throttled", "throttled_usec"})
    assert result["core_sched.force_idle_usec"] == 0
    assert result["throttled_usec"] == 51921


@pytest.mark.parametrize("name", [".usage_usec", "core..usage_usec", "core.", "../usage_usec"])
def test_invalid_counter_names_remain_rejected(name):
    with pytest.raises(SupervisorError, match="CGROUP_METRICS_INVALID"):
        counters(name + " 1", set())


@pytest.mark.parametrize("text", ["usage_usec -1", "usage_usec True", "usage_usec 1.0",
                                 "usage_usec 1\nusage_usec 2", "usage_usec 18446744073709551616",
                                 "wrong 3", "usage_usec 1 extra"])
def test_bad_or_missing_metrics_are_never_zeroed(text):
    with pytest.raises(SupervisorError):
        counters(text, {"usage_usec"})


@pytest.mark.parametrize("name,value", [("cpu.max", "max 100000"),
                                       ("cpu.max", "200000 100000"),
                                       ("memory.max", "max"), ("memory.swap.max", "max"),
                                       ("pids.max", "1024")])
def test_kernel_limit_mismatch_rejects_before_collecting_counters(name, value):
    values = {"cpu.max": "100000 100000", "memory.max": "805306368",
              "memory.swap.max": "0", "pids.max": "128"}
    values[name] = value
    fixture = object.__new__(CgroupMetrics)
    fixture._read = values.__getitem__  # Explicit pure fixture, no kernel access.
    with pytest.raises(SupervisorError, match="CGROUP_KERNEL_LIMIT_MISMATCH"):
        fixture.sample()
