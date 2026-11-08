"""Fail-closed demo deadlines and reboot/clock rollback boundaries; no paid calls."""

import json
import sys
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from scripts import guest_demo_guard as guard
from scripts.guest_demo_guard import valid_window

NOW = datetime(2026, 11, 8, 2, 0, tzinfo=UTC)
BOOT = str(uuid4())


def window():
    return {
        "window_id": str(uuid4()),
        "workspace_id": str(uuid4()),
        "state": "ACTIVE",
        "boot_id": BOOT,
        "started_at": NOW.isoformat(),
        "expires_at": (NOW + timedelta(minutes=30)).isoformat(),
        "quote_until": (NOW + timedelta(minutes=45)).isoformat(),
        "funded_until": (NOW + timedelta(hours=2)).isoformat(),
    }


def test_live_window_and_exact_deadline():
    value = window()
    assert valid_window(value, NOW, BOOT)
    assert valid_window(value, NOW + timedelta(minutes=29), BOOT)
    assert not valid_window(value, NOW + timedelta(minutes=30), BOOT)
    assert not valid_window(value, NOW - timedelta(microseconds=1), BOOT)
    assert not valid_window(value, NOW, str(uuid4()))


@pytest.mark.parametrize(
    "field,value",
    [
        ("state", "OPENING"),
        ("state", "CLOSED"),
        ("workspace_id", "' OR true;--"),
        ("expires_at", (NOW + timedelta(minutes=31)).isoformat()),
        ("funded_until", (NOW + timedelta(minutes=29)).isoformat()),
        ("quote_until", (NOW + timedelta(minutes=29)).isoformat()),
        ("started_at", NOW.replace(tzinfo=None).isoformat()),
        ("expires_at", "invalid"),
    ],
)
def test_fail_closed(field, value):
    assert not valid_window(window() | {field: value}, NOW, BOOT)


@pytest.mark.skipif(sys.platform != "linux", reason="Actual Linux root file/lock semantics")
@pytest.mark.parametrize("fault", ["partial_open", "bad_json", "database_failure"])
def test_guard_failure_closes_or_stops_dispatcher(tmp_path, monkeypatch, fault):
    tmp_path.chmod(0o700)
    state = tmp_path / "window.json"
    state.write_text(
        "{" if fault != "partial_open" else json.dumps(window() | {"state": "OPENING"})
    )
    state.chmod(0o600)
    boot = tmp_path / "boot"
    boot.write_text(BOOT)
    monkeypatch.setattr(guard, "ROOT", tmp_path)
    monkeypatch.setattr(guard, "STATE", state)
    monkeypatch.setattr(guard, "BOOT", boot)
    monkeypatch.setattr(sys, "argv", ["guard", "check"])
    calls, commands = [], []

    def sql(database, statement):
        calls.append(database)
        if fault == "database_failure":
            raise RuntimeError("injected unavailable database")
        return b""

    monkeypatch.setattr(guard, "sql", sql)
    monkeypatch.setattr(guard, "command", lambda args: commands.append(args))
    if fault == "partial_open":
        guard.main()
        assert json.loads(state.read_text())["state"] == "CLOSED"
    else:
        with pytest.raises(RuntimeError, match="DEMO_GUARD_FAILED_ADMISSION_STOPPED"):
            guard.main()
    if fault == "database_failure":
        assert commands == [["/usr/bin/systemctl", "stop", "proofflow-product-dispatcher.service"]]
    else:
        assert calls == ["proofflow_budget", "proofflow_product"]
        assert not commands
