"""Real filesystem unit replacement; systemctl is a recording double, never invoked."""

import hashlib
import os
import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "linux" or getattr(os, "geteuid", lambda: -1)() != 0,
    reason="Linux root-owned installer fixture")


def unit(revision):
    return ("ExecStart=/usr/bin/python3 -I -B /opt/proofflow-retention/" + revision * 64
            + "/product_retention_host.py\nMemoryMax=512M\n").encode()


def test_exact_revision_update_preserves_predecessor_and_retry(tmp_path, monkeypatch):
    from scripts import install_product_retention as installer

    calls = []
    monkeypatch.setattr(installer, "command", lambda args: calls.append(args))
    path = tmp_path / "retention.service"
    path.write_bytes(unit("a"))
    path.chmod(0o644)
    installer.service_update(path, unit("b"))
    assert path.read_bytes() == unit("b")
    backup = tmp_path / (path.name + ".previous-" + hashlib.sha256(unit("a")).hexdigest())
    assert backup.read_bytes() == unit("a")
    assert len(calls) == 2 and all(c[1] == "stop" for c in calls)
    installer.service_update(path, unit("b"))
    assert len(calls) == 2


def test_nonrevision_policy_change_is_refused_before_stopping(tmp_path, monkeypatch):
    from scripts import install_product_retention as installer

    calls = []
    monkeypatch.setattr(installer, "command", lambda args: calls.append(args))
    path = tmp_path / "retention.service"
    path.write_bytes(unit("a"))
    path.chmod(0o644)
    with pytest.raises(RuntimeError, match="POLICY_CHANGED"):
        installer.service_update(path, unit("b").replace(b"512M", b"1024M"))
    assert not calls and path.read_bytes() == unit("a")


def test_linked_service_is_refused(tmp_path):
    from scripts import install_product_retention as installer

    target = tmp_path / "foreign"
    target.write_bytes(unit("a"))
    target.chmod(0o644)
    path = tmp_path / "retention.service"
    path.symlink_to(target)
    with pytest.raises(RuntimeError, match="UNIT_UNSAFE"):
        installer.service_update(path, unit("b"))
    assert target.read_bytes() == unit("a")
