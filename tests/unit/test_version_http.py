"""HTTP doubles only. Real approval races are tested with disposable PostgreSQL."""

import asyncio
from uuid import uuid4

from api.app.product_store import ProductFailure
from tests.unit.test_product_http import fixture


def test_exact_approval_rejects_unknown_fields_confirmation_and_csrf_before_store():
    async def check():
        store, _, client = fixture()
        prior = store.call
        seen = []
        version, intent = str(uuid4()), str(uuid4())

        async def call(op, *args):
            if op == "version_approve":
                seen.append(args)
                return ({"version_id": version, "approved": True, "already_applied": False},)
            return await prior(op, *args)

        store.call = call
        async with client:
            value = {"intent_id": intent, "bundle_sha256": "a" * 64, "confirm": True}
            path = "/v1/versions/" + version + "/approve"
            for changed in (
                {**value, "confirm": False},
                {**value, "confirm": 1},
                {**value, "candidate_source": "forged"},
            ):
                assert (await client.post(path, json=changed)).status_code == 400
            assert (
                await client.post(path, json=value, headers={"X-Proofflow-CSRF": ""})
            ).status_code == 403
            assert not seen
            assert (await client.post(path, json=value)).status_code == 200
            assert seen[0][0] == store.workspace and str(seen[0][3]) == version
            assert str(seen[0][4]) == intent and seen[0][5] == value["bundle_sha256"]

    asyncio.run(check())


def test_batch_forbids_caller_runtime_source_and_handles_stale_authority():
    async def check():
        store, _, client = fixture()
        prior = store.call
        seen = []

        async def call(op, *args):
            if op == "batch_enqueue":
                seen.append(args)
                raise ProductFailure("VERSION_NOT_ELIGIBLE")
            return await prior(op, *args)

        store.call = call
        value = {
            k: str(uuid4())
            for k in ("version_id", "transactions_id", "customers_id", "idempotency_key")
        }
        async with client:
            path = "/v1/pipelines/" + str(uuid4()) + "/batches"
            assert (await client.post(path, json={**value, "runtime": "custom"})).status_code == 400
            assert not seen
            assert (await client.post(path, json=value)).status_code == 409
            assert len(seen) == 1

    asyncio.run(check())
