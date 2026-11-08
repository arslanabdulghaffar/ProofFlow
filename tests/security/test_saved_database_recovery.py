"""Trusted restore helper boundaries; inert synthetic bytes, no live credentials."""

import base64
import hashlib
from copy import deepcopy
from datetime import UTC, datetime

import pytest

from orchestrator.restore_guard import RestoreError
from scripts import rehearse_saved_database as recovery


def test_saved_restore_has_no_disk_or_network_and_owns_its_deadline():
    args = recovery.create_args("synthetic-name", "synthetic-label")
    for flag, value in (("--network", "none"), ("--user", "70:70"), ("--cap-drop", "ALL"),
                        ("--memory", "512m"), ("--memory-swap", "512m"),
                        ("--security-opt", "no-new-privileges"), ("--ulimit", "core=0:0"),
                        ("--entrypoint", "/usr/bin/timeout")):
        assert args[args.index(flag)+1] == value
    assert "--mount" not in args and "--volume" not in args and "--publish" not in args
    mounts = [args[i+1] for i, value in enumerate(args) if value == "--tmpfs"]
    assert len(mounts) == 3 and all("noexec,nosuid,nodev" in m for m in mounts)
    assert any(m.startswith("/var/lib/postgresql:") and "size=256m" in m for m in mounts)
    assert "90" in args and "KILL" in args and "--read-only" in args and "--rm" in args
    assert "--init" in args


@pytest.mark.parametrize("fault", ["hash", "missing_authority", "extra_field"])
def test_invalid_saved_backup_stops_before_container_creation(monkeypatch, fault):
    now = datetime.now(UTC).isoformat()
    snapshot = {"observed_at": now, "workspaces": []}
    raw = b"inert fixture; never SQL"
    value = {"database": base64.b64encode(raw).decode(),
             "database_sha256": hashlib.sha256(raw).hexdigest(),
             "snapshot": snapshot, "current": snapshot}
    if fault == "hash":
        value["database_sha256"] = "0"*64
    elif fault == "missing_authority":
        value["current"] = None
    else:
        value["host"] = "untrusted target"
    monkeypatch.setattr(recovery, "docker", lambda *a, **kw: pytest.fail("Docker reached"))
    with pytest.raises((RestoreError, RuntimeError)):
        recovery.rehearse(value)


@pytest.mark.parametrize("fault", [None, "bind", "missing_ram", "network", "unbounded", "no_init"])
def test_inspected_tmpfs_is_in_hostconfig_not_mount_inventory(fault):
    config = {"Image": recovery.IMAGE, "Mounts": [], "Config": {"User": "70:70"},
              "HostConfig": {"NetworkMode": "none", "PortBindings": {}, "ReadonlyRootfs": True,
                             "Memory": 536870912, "MemorySwap": 536870912,
                             "Tmpfs": deepcopy(recovery.TMPFS), "AutoRemove": True, "Init": True,
                             "PidsLimit": 128, "NanoCpus": 1000000000, "CapDrop": ["ALL"],
                             "CapAdd": None, "Privileged": False,
                             "SecurityOpt": ["no-new-privileges"]}}
    if fault == "bind":
        config["Mounts"] = [{"Type": "bind"}]
    elif fault == "missing_ram":
        config["HostConfig"]["Tmpfs"].pop("/var/lib/postgresql")
    elif fault == "network":
        config["HostConfig"]["NetworkMode"] = "host"
    elif fault == "unbounded":
        config["HostConfig"]["Memory"] = 0
    elif fault == "no_init":
        config["HostConfig"]["Init"] = False
    if fault:
        with pytest.raises(RuntimeError, match="BOUNDARY_CHANGED"):
            recovery.validate_container(config)
    else:
        recovery.validate_container(config)
