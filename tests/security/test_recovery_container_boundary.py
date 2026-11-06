"""Recovery driver failure/launch boundary doubles; actual tmpfs timeout is separate."""

import importlib
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def driver(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    return importlib.import_module("asset_recovery_container")


def test_recovery_launch_keeps_source_readonly_and_plaintext_ephemeral(driver, monkeypatch):
    monkeypatch.setattr(driver, "source_tree", lambda: ("/trusted-fixture-source", "a" * 64))
    args, name, digest = driver.command()
    assert digest == "a" * 64 and name.startswith("proofflow-inert-recovery-")
    for option in ("--network=none", "--read-only", "--cap-drop=ALL",
                   "--security-opt=no-new-privileges", "--memory=512m", "--memory-swap=512m",
                   "--user=10003:10003", "--pids-limit=16", "--ulimit=core=0:0"):
        assert option in args
    assert [a for a in args if a.startswith("--mount=")] == [
        "--mount=type=bind,source=/trusted-fixture-source,destination=/trusted,readonly"]
    assert any(a.startswith("--tmpfs=/run/proofflow-recovery:")
               and "noexec,nosuid,nodev,size=67108864,mode=0700,uid=10003,gid=10003" in a
               for a in args)
    assert "--signal=KILL" in args and "20s" in args
    assert not any(a.startswith("--env=") for a in args)


def test_delivery_timeout_cleans_only_own_container_and_never_retries(driver, monkeypatch):
    monkeypatch.setattr(driver, "command", lambda: (["fixed-launch"], "owned-name", "b" * 64))
    states = iter([False, True])
    monkeypatch.setattr(driver, "absent", lambda name: next(states))
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        if args == ["fixed-launch"]:
            assert kwargs["input"] == b"private fixture input"
            raise subprocess.TimeoutExpired(args, 35)
        assert args == [*driver.WSL, "docker", "rm", "-f", "owned-name"]
        assert "input" not in kwargs
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(driver.subprocess, "run", run)
    with pytest.raises(subprocess.TimeoutExpired):
        driver.run(b"private fixture input")
    assert len(calls) == 2


def test_uncertain_cleanup_is_failure_even_after_successful_child(driver, monkeypatch):
    monkeypatch.setattr(driver, "command", lambda: (["fixed-launch"], "owned-name", "b" * 64))
    monkeypatch.setattr(driver, "absent", lambda name: False)
    monkeypatch.setattr(driver.subprocess, "run", lambda *a, **k:
                        SimpleNamespace(returncode=0, stdout=b"{}"))
    with pytest.raises(RuntimeError, match="CLEANUP_UNCONFIRMED"):
        driver.run(b"private fixture input")


def test_unexpected_importable_module_in_source_cache_is_denied(driver, tmp_path):
    (tmp_path / "api.py").write_bytes(b"inert unexpected module")
    with pytest.raises(RuntimeError, match="INVENTORY_CHANGED"):
        driver.validate_tree(tmp_path)


@pytest.mark.skipif(sys.platform != "linux", reason="Linux symlink fixture")
def test_source_cache_symlink_is_rejected_before_copying(driver, tmp_path):
    target = tmp_path / "cache"
    target.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (target / "orchestrator").symlink_to(outside, target_is_directory=True)
    with pytest.raises(RuntimeError, match="INVENTORY_CHANGED"):
        driver.validate_tree(target)
    assert not list(outside.iterdir())
