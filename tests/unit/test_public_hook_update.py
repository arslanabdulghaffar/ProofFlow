"""Fixed deployment boundary tests. No cloud calls or real service changes."""

import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def module(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    return importlib.import_module("update_public_certificate_hook")


@pytest.mark.parametrize("digest", ["../changed", "g"*64, "a"*63])
def test_invalid_revision_cannot_form_a_remote_path(module, digest):
    with pytest.raises(RuntimeError, match="DIGEST_INVALID"):
        module.replacement_unit(b"inert fixture", digest)


def test_changed_unit_cannot_be_overwritten(module):
    with pytest.raises(RuntimeError, match="UNIT_CHANGED"):
        module.replacement_unit(b"unexpected unit with owner changes", "a"*64)


def test_funding_stop_prevents_remote_mutation(module, monkeypatch):
    closed = []
    monkeypatch.setattr(module, "Admin", lambda: SimpleNamespace(
        state={"project": module.LABEL}, request=lambda *args: {"account": {}},
        host=lambda *a, **kw: pytest.fail("remote operation reached"),
        close=lambda: closed.append(True)))
    monkeypatch.setattr(module, "stop_reason", lambda *args: "LATCHED_STOP")
    with pytest.raises(RuntimeError, match="FUNDING_STOPPED"):
        module.main()
    assert closed == [True]
