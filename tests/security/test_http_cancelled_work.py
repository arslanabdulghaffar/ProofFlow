"""Real executor threads, inert bytes and labeled HTTP/store doubles; no cloud/code runs."""

import asyncio
import threading
from uuid import uuid4

import httpx
import pytest

from api.app import product
from api.app.product_store import ProductFailure
from tests.unit.test_product_http import ORIGIN, FixtureAssets, FixtureStore


def client_for(store, assets):
    app = product.create_product_app(store, assets, origin=ORIGIN, journals=object())
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN,
                            headers={"Cookie": "__Host-proofflow=" + store.secrets.token})


async def until(predicate):
    async with asyncio.timeout(2):
        while not predicate():
            await asyncio.sleep(0.001)


@pytest.mark.parametrize("failure", [False, True])
@pytest.mark.parametrize("termination", ["cancel", "deadline"])
def test_cancelled_bundle_keeps_capacity_until_real_thread_finishes(monkeypatch, failure,
                                                                  termination):
    if termination == "deadline":
        monkeypatch.setattr(product, "RESPONSE_DEADLINE_SECONDS", 0.15)

    async def exercise():
        store = FixtureStore()
        assets = FixtureAssets(store)
        prior = store.call
        started, release, finished = threading.Event(), threading.Event(), threading.Event()
        calls = []
        errors = []
        asyncio.get_running_loop().set_exception_handler(lambda loop, ctx: errors.append(ctx))

        async def call(operation, *values):
            if operation == "repair_bundle":
                return ({"inert_fixture": True},)
            return await prior(operation, *values)

        def build(*args):
            calls.append(True)
            if len(calls) == 1:
                started.set()
                try:
                    assert release.wait(3)
                    if failure:
                        raise ProductFailure("FIXTURE_IO_FAILURE")
                finally:
                    finished.set()
            return b"inert fixture bundle"

        store.call = call
        monkeypatch.setattr(product, "build_bundle", build)
        async with client_for(store, assets) as client:
            path = "/v1/repairs/" + str(uuid4()) + "/bundle"
            pending = asyncio.create_task(client.get(path))
            try:
                await until(started.is_set)
                if termination == "cancel":
                    pending.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await pending
                else:
                    # A pre-response timeout closes the connection. ASGITransport
                    # asserts because no response completed (no real socket here).
                    with pytest.raises(AssertionError):
                        await pending
                response = await client.get(path)
                assert response.status_code == 429
                assert len(calls) == 1
            finally:
                release.set()
                await until(finished.is_set)
            await asyncio.sleep(0.02)  # Executor completion callback releases capacity.
            assert (await client.get(path)).status_code == 200
            assert len(calls) == 2 and not errors

    asyncio.run(exercise())


def test_cancelled_upload_never_publishes_registry_after_background_write_finishes():
    async def exercise():
        store = FixtureStore()
        assets = FixtureAssets(store)
        original = assets.put
        started, release, finished = threading.Event(), threading.Event(), threading.Event()

        def put(workspace, raw):
            started.set()
            try:
                assert release.wait(3)
                return original(workspace, raw)
            finally:
                finished.set()

        assets.put = put
        async with client_for(store, assets) as client:
            task = asyncio.create_task(client.post("/v1/assets/pipeline/" + str(uuid4()),
                content=b"# inert fixture", headers={"Origin": ORIGIN,
                "X-Proofflow-CSRF": store.secrets.csrf}))
            try:
                await until(started.is_set)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            finally:
                release.set()
                await until(finished.is_set)
            assert "reserve" in store.events and "bytes_published" in store.events
            assert "publish" not in store.events and not store.registry

    asyncio.run(exercise())


def test_cancelled_asset_checks_cannot_accumulate_background_threads():
    async def exercise():
        store = FixtureStore()
        assets = FixtureAssets(store)
        release = threading.Event()
        lock = threading.Lock()
        started = []

        def check(workspace):
            with lock:
                started.append(workspace)
            assert release.wait(3)

        assets.assert_live = check
        async with client_for(store, assets) as client:
            requests = [asyncio.create_task(client.get("/v1/session")) for _ in range(4)]
            try:
                await until(lambda: len(started) == 4)
                for task in requests:
                    task.cancel()
                await asyncio.gather(*requests, return_exceptions=True)
                response = await client.get("/v1/session")
                assert response.status_code == 429
                assert len(started) == 4
            finally:
                release.set()
            await asyncio.sleep(0.02)
            assert (await client.get("/v1/session")).status_code == 200

    asyncio.run(exercise())


def test_revocation_during_bundle_build_still_denies_disclosure(monkeypatch):
    async def exercise():
        store = FixtureStore()
        assets = FixtureAssets(store)
        prior = store.call
        revoked = threading.Event()

        async def call(operation, *values):
            if operation == "repair_bundle":
                if revoked.is_set():
                    raise ProductFailure("ACCESS_DENIED")
                return ({"inert_fixture": True},)
            return await prior(operation, *values)

        def build(*args):
            revoked.set()
            return b"DO_NOT_DISCLOSE_FIXTURE"

        store.call = call
        monkeypatch.setattr(product, "build_bundle", build)
        async with client_for(store, assets) as client:
            response = await client.get("/v1/repairs/" + str(uuid4()) + "/bundle")
            assert response.status_code == 403
            assert b"DO_NOT_DISCLOSE_FIXTURE" not in response.content

    asyncio.run(exercise())
