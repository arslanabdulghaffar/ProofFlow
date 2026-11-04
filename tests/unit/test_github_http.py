"""API boundary doubles only; operator/current-authority checks also have real SQL tests."""

import asyncio
from uuid import uuid4

from api.app.product_store import ProductFailure
from tests.unit.test_product_http import fixture


def test_pr_approval_is_separate_strict_and_requires_csrf():
    async def check():
        store, _, client = fixture()
        prior = store.call
        seen = []
        intent = str(uuid4())

        async def call(op, *args):
            if op == "pr_approve":
                seen.append(args)
                return (True,)
            return await prior(op, *args)

        store.call = call
        value = {"preview_sha256": "a" * 64, "confirm": True}
        path = "/v1/pr-intents/" + intent + "/approve"
        async with client:
            for changed in (
                {**value, "confirm": 1},
                {**value, "confirm": False},
                {**value, "body": "override"},
            ):
                assert (await client.post(path, json=changed)).status_code == 400
            assert (
                await client.post(path, json=value, headers={"X-Proofflow-CSRF": ""})
            ).status_code == 403
            assert not seen
            assert (await client.post(path, json=value)).status_code == 200
            assert str(seen[0][3]) == intent and seen[0][4] == value["preview_sha256"]

    asyncio.run(check())


def test_preview_cannot_supply_repo_destination_and_missing_setup_is_honest():
    async def check():
        store, _, client = fixture()
        prior = store.call
        seen = []

        async def call(op, *args):
            if op == "pr_request":
                seen.append(args)
                raise ProductFailure("GITHUB_NOT_CONFIGURED")
            return await prior(op, *args)

        store.call = call
        path = "/v1/versions/" + str(uuid4()) + "/pr-preview"
        async with client:
            value = {"intent_id": str(uuid4())}
            assert (
                await client.post(path, json={**value, "repository": "attacker"})
            ).status_code == 400
            assert not seen
            result = await client.post(path, json=value)
            assert (
                result.status_code == 409
                and result.json()["error"]["code"] == "GITHUB_NOT_CONFIGURED"
            )

    asyncio.run(check())
