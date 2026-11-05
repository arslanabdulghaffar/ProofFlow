"""Fault-driver tests with explicit controller doubles; no GitHub or product database calls."""

import asyncio
from pathlib import Path

import pytest

from tests.unit.test_github_dispatcher import fixture


@pytest.mark.parametrize("change", [None, "intent", "digest"])
def test_driver_is_exactly_scoped_and_drops_only_the_final_reply(monkeypatch, change):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    from scripts.probe_phase4_pr_reply_loss import run

    _, store, app = fixture()
    identity, digest = store.job["id"], "a" * 64
    store.job["preview_sha256"] = digest
    if change == "intent":
        store.job["id"] = "different"
    elif change == "digest":
        store.job["preview_sha256"] = "b" * 64
    if change:
        with pytest.raises(RuntimeError, match="FAULT_PROBE_INTENT_CHANGED"):
            asyncio.run(run(store, app, identity, digest))
        assert not app.writes
    else:
        assert asyncio.run(run(store, app, identity, digest))["final_pr_reply_discarded"] is True
        assert len(app.writes) == 3 and store.job["state"] == "PR_PENDING"
        assert sum(op == "pr_readback" for op, _ in store.calls) == 2
        assert app.pr is not None


def test_driver_supports_real_frozen_store_without_mutating_dependencies(monkeypatch):
    from api.app.product_store import ProductConnection, ProductStore

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    from scripts.probe_phase4_pr_reply_loss import run

    _, fake, app = fixture()
    digest = "a" * 64
    fake.job["preview_sha256"] = digest

    async def call(self, operation, *args):
        return await fake.call(operation, *args)

    # No database/network: exercise the production immutable type with a fake
    # class-level I/O boundary, not the mutable Store used by the old tests.
    monkeypatch.setattr(ProductStore, "call", call)
    store = ProductStore(ProductConnection("fixture-unused", "dispatcher"))
    before_store, before_app = dict(vars(store)), dict(vars(app))
    result = asyncio.run(run(store, app, fake.job["id"], digest))
    assert result["final_pr_reply_discarded"] is True
    assert vars(store) == before_store
    assert "request" not in vars(app) and "request" not in before_app
    assert len(app.writes) == 3 and fake.job["state"] == "PR_PENDING"
