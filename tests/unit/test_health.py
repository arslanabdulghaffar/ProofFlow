"""Trusted HTTP boundary checks, not sandbox/provider acceptance tests."""

import asyncio

import httpx
import pytest

from api.app.main import app


def request(method, path, **kwargs):
    async def send():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(send())


def test_liveness_is_not_readiness():
    alive = request("GET", "/health/live")
    assert alive.status_code == 200
    assert alive.json() == {"status": "alive"}
    response = request("GET", "/health/ready")
    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "reason": "infrastructure_not_verified",
    }


def test_environment_and_request_cannot_assert_readiness(monkeypatch):
    monkeypatch.setenv("PROOFFLOW_READY", "true")
    monkeypatch.setenv("SANDBOX_VERIFIED", "true")
    response = request("GET", "/health/ready?ready=true", headers={"X-Ready": "true"})
    assert response.status_code == 503


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json", "/v1/jobs"])
def test_unimplemented_surfaces_are_not_exposed(path):
    assert request("GET", path).status_code == 404
    assert request("POST", path, json={"code": "not executed"}).status_code == 404


def test_health_has_no_mutating_route():
    assert request("POST", "/health/ready", json={"status": "ready"}).status_code == 405
