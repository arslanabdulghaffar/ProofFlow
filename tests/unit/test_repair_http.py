"""Labeled HTTP/store doubles. No code execution, provider or cloud calls."""

import asyncio
import hashlib
from uuid import uuid4

from api.app.product_store import ProductFailure
from tests.unit.test_product_http import fixture


def test_repair_enqueue_csrf_fixed_fields_and_owned_store_boundary():
    async def check():
        store, _, client = fixture()
        original = store.call
        identity = str(uuid4())
        seen = []

        async def call(operation, *values):
            if operation == "repair_enqueue":
                seen.append(values)
                return (identity,)
            return await original(operation, *values)

        store.call = call
        async with client:
            request = {"parent_id": str(uuid4()), "idempotency_key": str(uuid4())}
            assert (
                await client.post("/v1/repairs", json=request, headers={"X-Proofflow-CSRF": ""})
            ).status_code == 403
            assert not seen
            assert (
                await client.post("/v1/repairs", json={**request, "model": "external"})
            ).status_code == 400
            response = await client.post("/v1/repairs", json=request)
            assert response.status_code == 202 and response.json()["repair_id"] == identity
            assert seen[0][0] == store.workspace

    asyncio.run(check())


def test_export_inert_source_exact_hash_and_revocation_readback():
    async def check():
        store, assets, client = fixture()
        original_call = store.call
        identity = str(uuid4())
        original = b"# inert original\n"
        source = "# <script>untrusted data</script>\n"
        digest = hashlib.sha256(original).hexdigest()
        assets.values[(store.workspace, digest)] = original
        count = 0
        revoke = False

        async def call(operation, *values):
            nonlocal count
            if operation == "repair_export":
                count += 1
                if revoke and count % 2 == 0:
                    raise ProductFailure("ACCESS_DENIED")
                return ({"candidate_source": source, "original_sha256": digest},)
            return await original_call(operation, *values)

        store.call = call
        async with client:
            response = await client.get("/v1/repairs/" + identity + "/export")
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("application/json")
            assert response.headers["content-disposition"].startswith("attachment;")
            assert (
                response.json()["candidate_sha256"] == hashlib.sha256(source.encode()).hexdigest()
            )
            assert response.json()["activation_approved"] is False
            assert "original/pipeline.py" in response.json()["diff"]
            revoke = True
            assert (await client.get("/v1/repairs/" + identity + "/export")).status_code == 403

    asyncio.run(check())
