"""A bounded wait accommodates observed skew without accepting future snapshots."""

from datetime import UTC, datetime, timedelta

import pytest

from scripts.recovery_clock import wait_for_observation


def clock(monkeypatch, advance=True):
    now = datetime(2026, 11, 7, tzinfo=UTC)
    state = {"wall": now, "elapsed": 0}

    class Clock:
        fromisoformat = staticmethod(datetime.fromisoformat)

        @staticmethod
        def now(zone):
            return state["wall"]

    def sleep(seconds):
        state["elapsed"] += seconds
        if advance:
            state["wall"] += timedelta(seconds=seconds)

    monkeypatch.setattr("scripts.recovery_clock.datetime", Clock)
    monkeypatch.setattr("scripts.recovery_clock.time.monotonic", lambda: state["elapsed"])
    monkeypatch.setattr("scripts.recovery_clock.time.sleep", sleep)
    return now, state


def test_small_skew_waits_without_changing_observed_time(monkeypatch):
    now, state = clock(monkeypatch)
    observed = now + timedelta(seconds=1.5)
    assert wait_for_observation(observed.isoformat()) >= observed
    assert 1.4 <= state["elapsed"] <= 1.6


def test_past_observation_does_not_wait(monkeypatch):
    now, state = clock(monkeypatch)
    assert wait_for_observation((now - timedelta(seconds=1)).isoformat()) == now
    assert state["elapsed"] == 0


def test_large_skew_rejected(monkeypatch):
    now, _ = clock(monkeypatch)
    with pytest.raises(RuntimeError, match="CLOCK_NOT_CAUGHT_UP"):
        wait_for_observation((now + timedelta(seconds=6)).isoformat())


def test_stalled_clock_is_bounded(monkeypatch):
    now, state = clock(monkeypatch, advance=False)
    with pytest.raises(RuntimeError, match="CLOCK_NOT_CAUGHT_UP"):
        wait_for_observation((now + timedelta(seconds=1)).isoformat())
    assert state["elapsed"] < 6.2
