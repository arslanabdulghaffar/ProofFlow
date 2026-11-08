"""Operations alerts must fail closed without granting product/release authority."""

import importlib
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest


def fixture(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    m = importlib.import_module("check_operations")
    now = datetime(2026, 11, 8, tzinfo=UTC)
    future = (now+timedelta(days=1)).isoformat()
    o = {"public": {"certificate_expires_at": (now+timedelta(days=3)).isoformat(),
                    "live": {"status": 200, "body": {"status": "alive"}},
                    "ready": {"status": 503, "body": {"status": "not_ready",
                                                      "reason": "product_acceptance_incomplete"}}},
         "backup": {"authenticated": True, "snapshot_at": now.isoformat(), "expires_at": future},
         "tasks": [{"name": name, "enabled": True, "result": 0, "last_run": now.isoformat()}
                   for name in ("ProofFlow-CreditGuard", "ProofFlow-ProductBackup")],
         "remote": {"remaining_credit_usd": "188.96", "credit_stop_reason": None,
                    "budget": {"project_limit": 150000000, "inference_limit": 25000000,
                               "probe_limit": 2000000, "expires_at": future},
                    "funded_until": future, "hosts": {
                        role: {"services": dict.fromkeys(names, True),
                               "storage_path": m.STORAGE[role],
                               "free_bytes": 4*1024**3,
                               "total_bytes": 20*1024**3, "free_inodes": 50, "total_inodes": 100}
                        for role, names in m.SERVICES.items()}}}
    o["remote"]["hosts"]["control"].update(renewal_success=True, tls_rotation_pending=False)
    return m, now, o


@pytest.mark.parametrize("fault", [None, "tls", "live", "fake_ready", "wrong_app", "backup_expiry",
                                  "unauthenticated_backup", "stale_task", "disabled_task",
                                  "task_failure", "credit", "nan", "cutoff", "cap", "service",
                                  "disk", "inodes", "missing_probe", "malformed",
                                  "renewal", "rotation"])
def test_real_issues_are_actionable_and_liveness_is_not_release_readiness(monkeypatch, fault):
    m, now, o = fixture(monkeypatch)
    if fault == "tls":
        o["public"]["certificate_expires_at"] = now.isoformat()
    elif fault == "live":
        o["public"]["live"]["status"] = 500
    elif fault == "fake_ready":
        o["public"]["ready"] = {"status": 200, "body": {"status": "ready"}}
    elif fault == "wrong_app":
        o["public"]["ready"]["body"]["reason"] = "infrastructure_not_verified"
    elif fault == "backup_expiry":
        o["backup"]["expires_at"] = (now+timedelta(minutes=20)).isoformat()
    elif fault == "unauthenticated_backup":
        o["backup"]["authenticated"] = False
    elif fault == "stale_task":
        o["tasks"][0]["last_run"] = (now-timedelta(hours=1)).isoformat()
    elif fault == "disabled_task":
        o["tasks"][1]["enabled"] = False
    elif fault == "task_failure":
        o["tasks"][1]["result"] = 1
    elif fault in ("credit", "nan"):
        o["remote"]["remaining_credit_usd"] = "149" if fault == "credit" else "NaN"
    elif fault == "cutoff":
        o["remote"]["funded_until"] = now.isoformat()
    elif fault == "cap":
        o["remote"]["budget"]["inference_limit"] = 26000000
    elif fault == "service":
        o["remote"]["hosts"]["worker"]["services"]["proofflow-worker.service"] = False
    elif fault == "renewal":
        o["remote"]["hosts"]["control"]["renewal_success"] = False
    elif fault == "rotation":
        o["remote"]["hosts"]["control"]["tls_rotation_pending"] = True
    elif fault == "disk":
        o["remote"]["hosts"]["control"]["free_bytes"] = 1
    elif fault == "inodes":
        o["remote"]["hosts"]["worker"]["free_inodes"] = 1
    elif fault == "missing_probe":
        o.pop("public")
    elif fault == "malformed":
        o["backup"] = None
    before = deepcopy(o)
    result = m.assess(o, now)
    assert result["status"] == ("ACTION_REQUIRED" if fault else "SCOPED_OK")
    assert bool(result["blockers"]) == bool(fault)
    assert result["phase6_complete"] is False and o == before
    if fault in ("fake_ready", "wrong_app"):
        assert "PUBLIC_READINESS_REMAINS_503_NOT_VERIFIED" not in result["notes"]


def test_failed_probe_does_not_leak_exception_or_skip_other_checks(monkeypatch, capsys):
    m, now, o = fixture(monkeypatch)
    reached = []

    def fail():
        raise RuntimeError("synthetic-sensitive-error-never-print")

    def good(key):
        reached.append(key)
        return o[key]

    monkeypatch.setattr(m, "public_probe", fail)
    for key in ("backup", "tasks", "remote"):
        monkeypatch.setattr(m, key+"_probe", lambda key=key: good(key))
    assert m.main() == 1
    output = capsys.readouterr().out
    assert "synthetic-sensitive" not in output
    assert "PUBLIC_UNAVAILABLE" in json.loads(output)["blockers"]
    assert reached == ["backup", "tasks", "remote"]
