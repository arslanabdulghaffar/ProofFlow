"""Public API admission with labeled inert stores; no provider or worker calls."""

import asyncio

import httpx
import pytest

from api.app.product import create_product_app
from tests.unit.test_product_http import FixtureAssets, FixtureStore

ORIGIN = "https://192.0.2.1:8443"


@pytest.mark.parametrize("kind", ["guest", "operator"])
def test_public_only_imports_and_authorizes_guest_sessions(kind):
    class Store(FixtureStore):
        async def call(self, operation, *values):
            result = await super().call(operation, *values)
            if operation in ("session", "browser_session"):
                return result[0], kind, result[2]
            return result

    async def check():
        db = Store()
        app = create_product_app(db, FixtureAssets(db), origin=ORIGIN, guest_only=True)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url=ORIGIN) as c:
            imported = await c.post("/v1/session/import", headers={"Origin": ORIGIN}, json={
                "session_token": db.secrets.token, "csrf_token": db.secrets.csrf})
            response = await c.get("/v1/session", headers={
                "Cookie": "__Host-proofflow=" + db.secrets.token})
            if kind == "guest":
                assert imported.status_code == response.status_code == 200
                assert response.json()["kind"] == "guest"
            else:
                assert imported.status_code == response.status_code == 403
                assert not imported.headers.get_list("set-cookie")
                assert response.json()["error"]["code"] == "GUEST_SESSION_REQUIRED"
    asyncio.run(check())
