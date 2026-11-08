"""Real ASGI routes with inert store doubles; no public socket or candidate run."""

import asyncio
import json
import os
import sys

import httpx
import pytest

from api.app.auth import AuthError
from api.app.ingress import PRIVATE_ORIGIN, authority, load_origin
from api.app.product import create_product_app

ORIGIN = "https://demo.proofflow.example"


class Unused:
    async def call(self, *args):
        raise AssertionError("Ingress must reject before touching data")


@pytest.mark.parametrize("origin", [
    "http://demo.example", "https://DEMO.example", "https://demo.example:443",
    "https://demo.example/", "https://user@demo.example", "https://*.example",
    "https://demo.example.", "https://-demo.example", "https://demo_example",
    "https://demo.example:0443", "https://[::1]:443", "https://demo.example?x",
])
def test_noncanonical_origin_rejected(origin):
    with pytest.raises(AuthError):
        create_product_app(Unused(), Unused(), origin=origin)


@pytest.mark.parametrize("origin", [ORIGIN, PRIVATE_ORIGIN, "https://[::1]:18443"])
def test_canonical_origin(origin):
    assert authority(origin) == origin.removeprefix("https://").encode()


@pytest.mark.parametrize("headers,base", [
    ([("Host", "attacker.example")], ORIGIN),
    ([("Host", "demo.proofflow.example"), ("Host", "demo.proofflow.example")], ORIGIN),
    ([("Host", "demo.proofflow.example:443")], ORIGIN),
    ([("Forwarded", "host=demo.proofflow.example;proto=https")], ORIGIN),
    ([("X-Forwarded-Host", "demo.proofflow.example")], ORIGIN),
    ([("X-Forwarded-Proto", "https")], ORIGIN),
    ([("X-Forwarded-For", "127.0.0.1")], ORIGIN),
    ([], ORIGIN.replace("https:", "http:")),
])
def test_bad_authority_or_proxy_cannot_reach_even_public_routes(headers, base):
    async def check():
        app = create_product_app(Unused(), Unused(), origin=ORIGIN)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url=base) as client:
            for route in ("/", "/health/live", "/v1/session"):
                response = await client.get(route, headers=headers)
                assert response.status_code == 400
                assert response.json()["error"]["code"] == "INGRESS_NOT_ALLOWED"
                assert response.headers["cache-control"] == "no-store"
                assert "attacker.example" not in response.text
    asyncio.run(check())


def test_expected_origin_serves_shell_but_never_bootstraps_anonymous_authority():
    async def check():
        app = create_product_app(Unused(), Unused(), origin=ORIGIN)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url=ORIGIN) as client:
            assert (await client.get("/")).status_code == 200
            assert (await client.get("/health/live")).status_code == 200
            assert (await client.get("/v1/session")).status_code == 403
            assert (await client.post("/v1/session/import", json={})).status_code == 400
            assert (await client.get("/openapi.json")).status_code == 404
    asyncio.run(check())


@pytest.mark.skipif(sys.platform != "linux", reason="Actual Linux ownership/no-follow semantics")
def test_origin_file_modes_links_format_and_private_default(tmp_path):
    path = tmp_path / "origin.json"
    assert load_origin(path) == PRIVATE_ORIGIN
    path.write_text(json.dumps({"origin": ORIGIN}))
    path.chmod(0o400)
    assert load_origin(path) == ORIGIN
    link = tmp_path / "linked.json"
    link.symlink_to(path)
    with pytest.raises(OSError):
        load_origin(link)
    hard = tmp_path / "hard.json"
    os.link(path, hard)
    with pytest.raises(AuthError, match="ORIGIN_FILE_INVALID"):
        load_origin(path)
    hard.unlink()
    path.chmod(0o600)
    with pytest.raises(AuthError):
        load_origin(path)
    path.write_text('{"origin":"https://demo.example","extra":true}')
    path.chmod(0o400)
    with pytest.raises(AuthError):
        load_origin(path)
