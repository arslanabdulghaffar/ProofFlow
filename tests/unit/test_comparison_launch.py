"""Launcher fault tests with fake administration/HTTP only. No cloud or candidate I/O."""

import importlib
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest


def setup(tmp_path, monkeypatch, fault=None):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    module = importlib.import_module("scripts.run_comparison")
    (tmp_path / "evidence").mkdir()
    monkeypatch.setattr(module, "PRIVATE", tmp_path)
    monkeypatch.setattr(module.sys, "argv", ["synthetic-launch-test"])
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=b""))
    config = {
        "account_id": str(uuid4()),
        "quote": {
            k: module.QUOTE_POLICY[k]
            for k in ("model", "input_micro_usd_per_million", "output_micro_usd_per_million")
        },
    }
    config["quote"]["valid_until"] = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    monkeypatch.setattr(module, "refresh", lambda: config)
    original_manifest = module.manifest

    def reduced(**kwargs):
        # Explicit orchestration double: four jobs, not an evaluation result.
        plan = original_manifest(**kwargs)
        plan["jobs"] = [
            {"case": kwargs["cases"][0]["id"], "arm": arm, "repeat": 1} for arm in "ABCD"
        ]
        return plan

    monkeypatch.setattr(module, "manifest", reduced)
    events = []
    root = tmp_path / "evidence/final-comparison-v1"

    class Live:
        def __init__(self):
            self.policy = {"runtime_sha256": module.RUNTIME, "verifier_sha256": module.VERIFIER}
            self.credit = {"review_due_at": (datetime.now(UTC) + timedelta(hours=6)).isoformat()}
            self.admin = SimpleNamespace(host=self.admin_host)
            self.opened = False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            if self.opened:
                self.admission(False)

        def sql(self, statement, database=None):
            events.append(statement)
            if "bool_and(blocked)" in statement:
                return b"t"
            if "SELECT" in statement:
                return b"0"
            return b""

        def admission(self, enabled):
            events.append(("admission", enabled))
            self.opened = enabled

        def host(self, command, raw=None):
            events.append(command)
            if command.startswith("systemctl is-active"):
                return b"active\nactive\nactive"
            if "docker inspect" in command:
                return ("sha256:" + module.IMAGE).encode()
            if "echo present" in command:
                return b"absent"
            if "df --output" in command:
                return str(5 * 1024**3).encode()
            if command.startswith("sha256sum "):
                freeze = json.loads((root / "freeze.json").read_bytes())
                name = command.split("/" + freeze["revision"] + "/", 1)[1]
                return (freeze["shipped"][name] + " file").encode()
            if "comparison_setup.py" in command:
                return b"COMPARISON_BOOK_INITIALIZED"
            if command.startswith("cat /etc/proofflow-repair/config.json"):
                return json.dumps(config).encode()
            return b""

        def admin_host(self, role, command, timeout):
            events.append(("controller", command))
            if fault == "unknown_controller":
                raise TimeoutError("synthetic lost transport")
            freeze = json.loads((root / "freeze.json").read_bytes())
            job = next(j for j in freeze["jobs"] if j["run_id"] == command.split()[-1])
            result = {
                **job,
                "decision": "failed",
                "grade": "unknown",
                "calls": [],
                "critical": fault == "critical_controller",
            }
            return SimpleNamespace(returncode=0, stdout=json.dumps(result).encode())

    def api(live, job, case, path):
        events.append(("api", job["run_id"]))
        if fault == "api_exception":
            raise RuntimeError("synthetic unknown API response")
        return {
            **job,
            "decision": "held",
            "grade": "correct",
            "calls": [],
            "critical": fault == "critical_api",
        }

    monkeypatch.setattr(module, "LiveSession", Live)
    monkeypatch.setattr(module, "run", api)
    monkeypatch.setattr(module, "retire", lambda *a: events.append("retire"))
    return module, events, root


def test_success_closes_every_job_and_keeps_fixed_finite_artifacts(tmp_path, monkeypatch):
    module, events, root = setup(tmp_path, monkeypatch)
    module.main()
    freeze = json.loads((root / "freeze.json").read_bytes())
    assert freeze["forecast_micro"] == 7200000
    assert freeze["A_cap_micro"] + freeze["BC_cap_micro"] == freeze["forecast_micro"]
    assert len(list(root.glob("dispatch-*.json"))) == 4
    assert len(list(root.glob("closed-*.json"))) == 4
    assert (root / "completed.json").exists()
    assert events.count("UPDATE pf_budget.accounts SET blocked=false;") == 3
    assert events.count("UPDATE pf_budget.accounts SET blocked=true;") == 4
    assert events.count(("admission", True)) == 1 and events.count(("admission", False)) == 1
    before = len(events)
    with pytest.raises(RuntimeError, match="ALREADY_STARTED"):
        module.main()
    assert len(events) == before


@pytest.mark.parametrize(
    "fault", ["api_exception", "critical_api", "unknown_controller", "critical_controller"]
)
def test_fault_closes_admission_and_halts_remaining_jobs(tmp_path, monkeypatch, fault):
    module, events, root = setup(tmp_path, monkeypatch, fault)
    with pytest.raises((RuntimeError, TimeoutError)):
        module.main()
    assert not (root / "completed.json").exists()
    dispatched = len(list(root.glob("dispatch-*.json")))
    assert dispatched == (1 if "api" in fault else 2)
    assert len(list(root.glob("closed-*.json"))) == dispatched
    assert events.count("UPDATE pf_budget.accounts SET blocked=true;") == dispatched
    assert events.count(("admission", False)) == 1
    if "api" in fault:
        assert "retire" not in events


def test_deterministic_container_has_no_provider_or_database_credentials(tmp_path, monkeypatch):
    module, _, _ = setup(tmp_path, monkeypatch)
    job = {"run_id": str(uuid4()), "arm": "D"}
    argv = module.container("/trusted", "/private", job=job)
    assert not any("repair/credentials" in arg or "proofflow-budget" in arg for arg in argv)
    assert "--read-only" in argv and "--cap-drop=ALL" in argv
    assert "--memory=512m" in argv and "--pids-limit=64" in argv
    assert not any("docker.sock" in arg or "github" in arg for arg in argv)


def test_actual_script_entrypoint_rejects_arguments_before_account_access(tmp_path):
    script = Path(__file__).resolve().parents[2] / "scripts/run_comparison.py"
    reply = subprocess.run(  # noqa: S603 - actual fixed entrypoint, rejected before account access
        [sys.executable, str(script), "--not-authorized"],
        cwd=tmp_path,
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert reply.returncode != 0
    assert b"COMPARISON_ARGUMENTS_FORBIDDEN" in reply.stderr
    assert b"ModuleNotFoundError" not in reply.stderr
