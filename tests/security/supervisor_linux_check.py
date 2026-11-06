"""Trusted host integration fixtures only: no worker image, runsc or candidate code.

Run explicitly under local Linux root/systemd. Creates only generated private
roots/units, normal tmpfs mounts, fixed tiny files, bounded logs and sleeping
trusted processes. Tests real watchdog/cgroup/collector/cleanup composition.
"""

import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import replace
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from worker.protocol import ExecutionRequest, SupervisorError, authority_id  # noqa: E402
from worker.runtime import SystemdRunsc  # noqa: E402
from worker.staging import Staging, mount_inventory  # noqa: E402
from worker.supervisor import Supervisor  # noqa: E402


class TrustedFixtureRuntime(SystemdRunsc):
    """Test-only substitution. No fixture selection exists in production modules."""

    def __init__(self, mode="success"):
        self.mode = mode

    def validate(self):
        assert os.geteuid() == 0 and Path("/proc/1/comm").read_text().strip() == "systemd"

    def identity(self):
        return {"runtime": "trusted_local_fixture", "runsc": "NOT_RUN"}

    def _runtime_args(self, identifier, path):
        return [
            "/usr/bin/python3",
            "-I",
            str(Path(__file__).resolve()),
            "--service",
            self.mode,
            str(path / "output"),
        ]

    def write_config(self, request, path):
        (path / "config.json").write_text('{"fixture_only":true}')

    def delete_state(self, identifier, path):
        pass


def request():
    # Inert bytes are staged, never imported or executed by these fixtures.
    return ExecutionRequest(
        authority_id(), authority_id(), 1, b"# never executed fixture\n", b"", b"", b"{}"
    )


def service(mode, output):
    path = Path(output)
    if mode == "crash":
        os.write(2, b"TRUSTED_CRASH_FIXTURE PASS_IS_INERT\n" * 512)
        raise SystemExit(2)
    (path / "ledger.jsonl").write_bytes(b'{"fixture":true}\n')
    (path / "unresolved.jsonl").write_bytes(b"")
    if mode == "bad-output":
        (path / "unexpected.txt").write_bytes(b"fixture")
    if mode == "logs":
        for _ in range(128):
            os.write(1, b"o" * 4096)
            os.write(2, b"e" * 4096)
    if mode == "cpu":
        children = [os.fork()]
        if children[0] != 0:
            children.append(os.fork())
        until = time.monotonic() + 2
        while time.monotonic() < until:
            pass  # Fixed two-second trusted CPU fixture; never candidate code.
        if 0 in children:
            os._exit(0)
        for child in children:
            os.waitpid(child, 0)
    if mode == "sleep":
        child = os.fork()
        if child == 0:
            os.setsid()
        # Both parent and detached descendant are trusted sleepers in one cgroup.
        while True:
            time.sleep(1)


def child_supervisor(root, identifier):
    supervisor = Supervisor(Path(root), TrustedFixtureRuntime("sleep"))
    supervisor.recover()
    supervisor.execute(replace(request(), execution_id=UUID(hex=identifier)))


def wait_active(runtime, identifier, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = runtime.show(identifier)
        if state.get("ActiveState") == "active" and state.get("MainPID") not in ("0", None):
            return state
        time.sleep(0.03)
    raise AssertionError("Fixture service did not become active")


def main():
    root = Path(tempfile.mkdtemp(prefix="proofflow-supervisor-check-"))
    assert root.parent == Path(tempfile.gettempdir()) and root.name.startswith(
        "proofflow-supervisor-check-"
    )
    owned = []
    threads = []
    runtime = TrustedFixtureRuntime()
    supervisor = None
    checks = []
    try:
        supervisor = Supervisor(root, runtime)
        supervisor.recover()
        item = request()
        owned.append(item.execution_id)
        receipt = supervisor.execute(item)
        assert receipt["collected"] and receipt["cleanup"] == "confirmed", receipt
        assert receipt["outcome"] == "exited" and receipt["runtime_client_exit_code"] == 0, receipt
        assert not supervisor.staging.path(item.execution_id).exists()
        assert receipt["verification"] == "NOT_PERFORMED"
        observed = receipt["resource_observation"]
        assert observed["source"] == "host_cgroup_v2" and observed["samples"] >= 1
        assert observed["last_observed"]["cpu"]["usage_usec"] > 0
        assert observed["last_observed"]["memory_peak_bytes"] > 0
        assert observed["sampled_max_host_tasks"] > 0
        assert supervisor.execute(item) == receipt
        try:
            supervisor.acknowledge(item.execution_id, "incorrect-manifest")
        except SupervisorError as error:
            assert str(error) == "INVALID_CAPTURE_ACKNOWLEDGEMENT"
        else:
            raise AssertionError("Wrong manifest acknowledged capture")
        supervisor.acknowledge(item.execution_id, item.manifest_hash())
        assert not (root / "results" / item.execution_id.hex).exists()
        checks.append("real_service_capture_cleanup_exact_replay_no_reexecution")

        runtime.mode = "crash"
        item = request()
        owned.append(item.execution_id)
        receipt = supervisor.execute(item)
        assert not receipt["collected"] and receipt["cleanup"] == "confirmed", receipt
        assert receipt["outcome"] == "output_rejected" and receipt["error"] == "MISSING_OUTPUT_FILE"
        assert receipt["verification"] == "NOT_PERFORMED"
        preview = receipt["failure_log_preview"]
        assert sum(v["retained"] for v in preview) <= 4096
        assert base64.b64decode(preview[0]["base64"]).startswith(b"TRUSTED_CRASH_FIXTURE")
        assert preview[0]["truncated"]
        assert not supervisor.staging.path(item.execution_id).exists()
        checks.append("failed_collection_retains_bounded_inert_diagnostics_without_acceptance")

        runtime.mode = "cpu"
        item = request()
        owned.append(item.execution_id)
        receipt = supervisor.execute(item)
        assert receipt["cleanup"] == "confirmed" and receipt["collected"], receipt
        observed = receipt["resource_observation"]
        assert observed["last_observed"]["cpu"]["nr_throttled"] > 0, observed
        assert observed["last_observed"]["cpu"]["throttled_usec"] > 0, observed
        assert observed["samples"] > 1 and observed["sampled_max_host_tasks"] >= 2
        checks.append("host_kernel_cpu_throttling_and_memory_task_observations")
        runtime.mode = "success"

        # A rejected watchdog readback must never release ExecStartPre.
        original_show = runtime.show

        def wrong_policy(identifier):
            state = original_show(identifier)
            if state.get("ActiveState") == "activating":
                state["MemoryMax"] = "infinity"
            return state

        runtime.show = wrong_policy
        item = request()
        owned.append(item.execution_id)
        receipt = supervisor.execute(item)
        runtime.show = original_show
        assert receipt["error"] == "WATCHDOG_POLICY_MISMATCH", receipt
        assert not receipt["collected"] and receipt["cleanup"] == "confirmed"
        checks.append("wrong_watchdog_readback_prevents_fixture_start_and_cleans")

        # Simulate a delayed accepted start after the supervisor already removed staging.
        item = request()
        owned.append(item.execution_id)
        path = supervisor.staging.prepare(item)
        supervisor.staging.cleanup(item.execution_id)
        delayed = subprocess.run(  # noqa: S603 - fixed trusted fixture and owned UUID unit
            runtime._start_args(item.execution_id, path),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
        assert delayed.returncode != 0
        runtime.confirm_stopped(item.execution_id)
        assert not path.exists()
        checks.append("late_start_after_staging_removal_denied_by_independent_gate")

        runtime.mode = "logs"
        item = request()
        owned.append(item.execution_id)
        receipt = supervisor.execute(item)
        assert receipt["collected"] and sum(v["retained"] for v in receipt["logs"]) == 102400
        assert sum(v["received"] for v in receipt["logs"]) >= 1048576
        assert any(v["truncated"] for v in receipt["logs"])
        checks.append("real_simultaneous_stdout_stderr_flood_bounded_and_drained")

        retained = root / "results" / item.execution_id.hex
        os.utime(retained, (1, 1))  # Age only this trusted fixture's private copy.
        deadline = time.monotonic() + 3
        while retained.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not retained.exists(), "Running supervisor did not prune expired fixture capture"
        assert supervisor.execute(item) == receipt  # Historical replay never reruns deleted bytes.
        original_prune = supervisor.staging.prune_results

        def failed_maintenance(_):
            raise SupervisorError("FIXTURE_MAINTENANCE_FAULT")

        supervisor.staging.prune_results = failed_maintenance
        deadline = time.monotonic() + 3
        while supervisor._recovered and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not supervisor._recovered
        try:
            supervisor.execute(request())
        except SupervisorError as error:
            assert str(error) == "WORKER_MAINTENANCE_FAILED"
        else:
            raise AssertionError("Maintenance failure allowed admission")
        supervisor.staging.prune_results = original_prune
        supervisor.recover()
        checks.append("resident_capture_expiry_and_fail_closed_maintenance_recovery")

        runtime.mode = "bad-output"
        item = request()
        owned.append(item.execution_id)
        receipt = supervisor.execute(item)
        assert receipt["outcome"] == "output_rejected" and not receipt["collected"]
        assert receipt["cleanup"] == "confirmed"
        checks.append("extra_output_rejected_and_all_mounts_cleaned")

        runtime.mode = "sleep"
        item = request()
        owned.append(item.execution_id)
        result = []
        thread = threading.Thread(target=lambda: result.append(supervisor.execute(item)))
        threads.append(thread)
        thread.start()
        state = wait_active(runtime, item.execution_id)
        assert state["RuntimeMaxUSec"] == "20s" and state["KillMode"] == "control-group", state
        assert state["MemoryMax"] == "805306368" and state["TasksMax"] == "128"
        supervisor.journal.cancel(item.execution_id, item.job_id, item.generation)
        thread.join(timeout=10)
        assert not thread.is_alive() and result[0]["outcome"] == "cancelled", result
        runtime.confirm_stopped(item.execution_id)
        checks.append("durable_cancel_kills_detached_descendant_before_collection")

        # An injected normal-unmount/cleanup fault must quarantine admission.
        runtime.mode = "success"
        original_cleanup = supervisor.staging.cleanup

        def failed_cleanup(_):
            raise SupervisorError("FIXTURE_CLEANUP_FAULT")

        supervisor.staging.cleanup = failed_cleanup
        item = request()
        owned.append(item.execution_id)
        receipt = supervisor.execute(item)
        assert receipt["cleanup"] == "uncertain"
        try:
            supervisor.execute(request())
        except SupervisorError as error:
            assert str(error) == "WORKER_QUARANTINED"
        else:
            raise AssertionError("Cleanup fault allowed admission")
        supervisor.staging.cleanup = original_cleanup
        supervisor.recover()
        checks.append("cleanup_failure_quarantines_then_recovery_reclaims_owned_resources")
        supervisor.close()
        supervisor = None

        identifier = authority_id()
        owned.append(identifier)
        child = subprocess.Popen(  # noqa: S603 - fixed trusted local fixture
            [
                sys.executable,
                "-I",
                str(Path(__file__).resolve()),
                "--child",
                str(root),
                identifier.hex,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        try:
            state = wait_active(runtime, identifier)
            group = Path("/sys/fs/cgroup" + state["ControlGroup"])
            time.sleep(0.2)
            assert len((group / "cgroup.procs").read_text().split()) >= 2
            start = time.monotonic()
            child.kill()  # Kill only our supervisor fixture, NOT its systemd service.
            child.wait(timeout=2)
            deadline = start + 23
            while time.monotonic() < deadline:
                state = runtime.show(identifier)
                if state["ActiveState"] in ("inactive", "failed"):
                    break
                time.sleep(0.1)
            assert state.get("Result") == "timeout", state
            assert time.monotonic() - start < 23
            runtime.confirm_stopped(identifier)
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=2)
            child.stderr.close()
        supervisor = Supervisor(root, runtime)
        supervisor.recover()
        assert not supervisor.staging.path(identifier).exists()
        assert supervisor.journal.receipt(identifier)["outcome"] == "interrupted"
        checks.append(
            "independent_20s_systemd_watchdog_after_supervisor_SIGKILL_and_restart_cleanup"
        )
    finally:
        for identifier in owned:
            runtime.stop_and_confirm(identifier)
        for thread in threads:
            thread.join(timeout=10)
            assert not thread.is_alive(), "Trusted fixture supervisor thread did not exit"
        if supervisor:
            supervisor.close()
        for identifier in owned:
            Staging(root).cleanup(identifier)
            runtime.forget(identifier)
        assert not any(p.startswith(str(root) + "/") for p in mount_inventory())
        assert root.name.startswith("proofflow-supervisor-check-")
        shutil.rmtree(root)  # Exact generated private root, after all mounts/writers are absent.
    print(
        json.dumps(
            {
                "scope": "trusted_local_systemd_fixtures_no_candidates_no_runsc",
                "checks": checks,
                "cleanup": "owned_units_mounts_processes_and_root_absent",
            }
        )
    )


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--service":
        service(sys.argv[2], sys.argv[3])
    elif len(sys.argv) > 1 and sys.argv[1] == "--child":
        child_supervisor(sys.argv[2], sys.argv[3])
    else:
        main()
