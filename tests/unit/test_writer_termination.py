"""Mock kernel observations only; never starts a runtime or candidate."""

from unittest.mock import Mock
from uuid import uuid4

import pytest

from worker.protocol import SupervisorError
from worker.runtime import SystemdRunsc


@pytest.mark.parametrize("failure", ["EXECUTION_WRITERS_REMAIN", "EXECUTION_WRITERS_UNCERTAIN"])
def test_collection_waits_for_kernel_empty_after_systemd_stop(monkeypatch, failure):
    runtime = SystemdRunsc(None)
    runtime.show = Mock(return_value={"LoadState": "not-found"})
    runtime.confirm_stopped = Mock(side_effect=[SupervisorError(failure), {"empty": True}])
    monkeypatch.setattr("worker.runtime.time.monotonic", Mock(side_effect=[0, 0.1]))
    sleeper = Mock()
    monkeypatch.setattr("worker.runtime.time.sleep", sleeper)
    assert runtime.stop_and_confirm(uuid4()) == {"empty": True}
    assert runtime.confirm_stopped.call_count == 2
    sleeper.assert_called_once_with(0.02)


def test_persistent_writers_still_fail_closed_after_bounded_wait(monkeypatch):
    runtime = SystemdRunsc(None)
    runtime.show = Mock(return_value={"LoadState": "not-found"})
    runtime.confirm_stopped = Mock(side_effect=SupervisorError("EXECUTION_WRITERS_REMAIN"))
    monkeypatch.setattr("worker.runtime.time.monotonic", Mock(side_effect=[0, 3]))
    with pytest.raises(SupervisorError, match="EXECUTION_WRITERS_REMAIN"):
        runtime.stop_and_confirm(uuid4())


def test_unexpected_cgroup_never_retried(monkeypatch):
    runtime = SystemdRunsc(None)
    runtime.show = Mock(return_value={"LoadState": "not-found"})
    runtime.confirm_stopped = Mock(side_effect=SupervisorError("UNEXPECTED_EXECUTION_CGROUP"))
    sleeper = Mock()
    monkeypatch.setattr("worker.runtime.time.sleep", sleeper)
    with pytest.raises(SupervisorError, match="UNEXPECTED_EXECUTION_CGROUP"):
        runtime.stop_and_confirm(uuid4())
    sleeper.assert_not_called()
