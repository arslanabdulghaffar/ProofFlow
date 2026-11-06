"""Trusted admin file fixtures; no systemd, network or image execution."""

import base64
import os

import pytest

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Linux owner/mode semantics")


def setup(tmp_path, monkeypatch):
    from scripts import install_verifier_update as module

    paths = {str(tmp_path / name): (os.geteuid(), 0o400) for name in ("unit", "config")}
    payload = {}
    for path in paths:
        with open(path, "wb") as output:
            output.write(b"previous")
        os.chmod(path, 0o400)
        payload[path] = {
            k: base64.b64encode(v).decode()
            for k, v in {"old": b"previous", "new": b"replacement"}.items()
        }
    monkeypatch.setattr(module, "PATHS", paths)
    return module, payload


def test_all_predecessors_checked_before_replacement_and_backup_preserved(tmp_path, monkeypatch):
    module, payload = setup(tmp_path, monkeypatch)
    module.install(payload, check_only=True)
    assert (tmp_path / "unit").read_bytes() == b"previous"
    module.install(payload)
    assert (tmp_path / "unit").read_bytes() == b"replacement"
    assert [p.read_bytes() for p in tmp_path.glob("*.previous-*")] == [b"previous", b"previous"]
    with pytest.raises(RuntimeError, match="PREDECESSOR_CHANGED"):
        module.install(payload)


@pytest.mark.parametrize("fault", ["content", "symlink", "extra_path"])
def test_unsafe_update_leaves_every_target_unchanged(tmp_path, monkeypatch, fault):
    module, payload = setup(tmp_path, monkeypatch)
    if fault == "content":
        os.chmod(tmp_path / "config", 0o600)
        (tmp_path / "config").write_bytes(b"foreign")
        os.chmod(tmp_path / "config", 0o400)
    elif fault == "symlink":
        (tmp_path / "config").unlink()
        (tmp_path / "config").symlink_to(tmp_path / "unit")
    else:
        payload[str(tmp_path / "extra")] = payload[str(tmp_path / "unit")]
    with pytest.raises(RuntimeError):
        module.install(payload)
    assert (tmp_path / "unit").read_bytes() == b"previous"
    assert not list(tmp_path.glob("*.previous-*"))
