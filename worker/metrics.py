"""Read-only host cgroup evidence. Never accepts guest claims or arbitrary paths."""

import os
import re
from uuid import UUID

from worker.protocol import SupervisorError, execution_name


def counters(text: str, required: set[str]) -> dict[str, int]:
    result = {}
    for line in text.splitlines():
        parts = line.split()
        if (len(parts) != 2 or not re.fullmatch(r"[a-z_]+", parts[0])
                or not re.fullmatch(r"[0-9]{1,20}", parts[1]) or parts[0] in result
                or int(parts[1]) > 2**64 - 1):
            raise SupervisorError("CGROUP_METRICS_INVALID")
        result[parts[0]] = int(parts[1])
    if not required <= result.keys():
        raise SupervisorError("CGROUP_METRICS_UNAVAILABLE")
    return result


class CgroupMetrics:
    def __init__(self, identifier: UUID):
        path = "/sys/fs/cgroup/system.slice/" + execution_name(identifier) + ".service"
        self.fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        self.samples = 0
        self.latest = {}
        self.sampled_max_pids = 0
        self.final_sample_available = False
        try:
            self.sample()  # Required host policy readback before the startup gate opens.
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def _read(self, name: str) -> str:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=self.fd)
        try:
            raw = os.read(descriptor, 4097)
            if len(raw) > 4096:
                raise SupervisorError("CGROUP_METRICS_LIMIT")
            try:
                return raw.decode("ascii").strip()
            except UnicodeError:
                raise SupervisorError("CGROUP_METRICS_INVALID") from None
        finally:
            os.close(descriptor)

    def sample(self):
        quota = self._read("cpu.max").split()
        if (len(quota) != 2 or not all(re.fullmatch(r"[0-9]{1,9}", n) for n in quota)
                or not 1 <= int(quota[0]) == int(quota[1])
                or self._read("memory.max") != "805306368"
                or self._read("memory.swap.max") != "0" or self._read("pids.max") != "128"):
            raise SupervisorError("CGROUP_KERNEL_LIMIT_MISMATCH")
        cpu = counters(self._read("cpu.stat"), {"usage_usec", "nr_throttled", "throttled_usec"})
        memory = counters(self._read("memory.events"), {"oom", "oom_kill", "max"})
        peak = counters("bytes " + self._read("memory.peak"), {"bytes"})["bytes"]
        pids = counters("tasks " + self._read("pids.current"), {"tasks"})["tasks"]
        self.sampled_max_pids = max(self.sampled_max_pids, pids)
        self.latest = {"cpu": cpu, "memory_events": memory, "memory_peak_bytes": peak}
        self.samples += 1

    def finish(self) -> dict:
        try:
            self.sample()
            self.final_sample_available = True
        except OSError:
            pass  # Kernel may already have removed the stopped cgroup. Never invent zeroes.
        return {"source": "host_cgroup_v2", "scope": "runtime_and_descendants_not_guest_only",
                "samples": self.samples, "final_sample_available": self.final_sample_available,
                "sampled_max_host_tasks": self.sampled_max_pids, "last_observed": self.latest,
                "limits": {"cpu_cores": 1, "memory_bytes": 805306368,
                           "swap_bytes": 0, "host_tasks": 128}}
