"""Bootstrap HTTP doubles and guard policy fixtures; no real approvals or inference."""

import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import httpx
import pytest

from api.app.product import create_product_app
from api.app.product_store import ProductFailure
from orchestrator.judge_quote import catalogue_quote

sys.path.insert(0, str(Path("scripts").resolve()))
from judging_guard import allowed  # noqa: E402


@pytest.mark.parametrize(
    "origin,public,consent,fail,status",
    [
        ("https://example.org", True, True, False, 200),
        ("https://evil.example", True, True, False, 403),
        (None, True, True, False, 403),
        ("https://example.org", False, True, False, 404),
        ("https://example.org", True, False, False, 400),
        ("https://example.org", True, 1, False, 400),
        ("https://example.org", True, True, True, 503),
    ],
)
def test_claim_boundary(origin, public, consent, fail, status):
    class Store:
        calls = []

        async def call(self, operation, *args):
            self.calls.append(operation)
            assert operation == "judge_claim" and isinstance(args[0], UUID)
            assert args[0].version == 7 and len(args[1]) == len(args[2]) == 64
            assert args[1] != args[2]
            if fail:
                raise ProductFailure("ADMISSION_CLOSED")
            return (datetime.now(UTC) + timedelta(minutes=30),)

    async def run():
        store = Store()
        app = create_product_app(store, None, origin="https://example.org", guest_only=public)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="https://example.org"
        ) as c:
            reply = await c.post(
                "/v1/judge/start",
                json={"synthetic_only": consent},
                headers={} if origin is None else {"Origin": origin},
            )
            assert reply.status_code == status
            if status == 200:
                assert reply.json()["kind"] == "guest"
                assert "pf_s_" not in reply.text and "pf_c_" not in reply.text
                cookies = reply.headers.get_list("set-cookie")
                assert len(cookies) == 2 and "HttpOnly" in cookies[0]
                assert all("Secure" in v and "SameSite=Strict" in v for v in cookies)
            else:
                assert not reply.headers.get_list("set-cookie")

    asyncio.run(run())


def test_guard_window():
    now = datetime(2026, 11, 9, tzinfo=UTC)
    good = {
        "enabled": True,
        "reviewed_at": now.isoformat(),
        "funded_until": (now + timedelta(hours=48)).isoformat(),
        "boot_id": "fixture",
    }
    assert allowed(good, now, "fixture")
    for patch in (
        {"enabled": False},
        {"boot_id": "other"},
        {"funded_until": now.isoformat()},
        {"funded_until": (now + timedelta(hours=49)).isoformat()},
    ):
        assert not allowed(good | patch, now, "fixture")
    assert not allowed(good, now - timedelta(seconds=1), "fixture")


def test_backup_observation_cannot_login_or_change_admission():
    from product_live_session import LiveSession
    live = LiveSession(observation_only=True)
    with pytest.raises(RuntimeError, match='OBSERVATION_CANNOT_LOGIN'):
        live.login(UUID(int=1))
    with pytest.raises(RuntimeError, match='OBSERVATION_CANNOT_CHANGE_ADMISSION'):
        live.admission(True)


def test_credit_guard_retries_only_bounded_administration_contention():
    from vultr_credit_guard import acquire_guard_admin
    waited = []
    calls = []
    def busy_then_ready():
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError('ADMINISTRATOR_OPERATION_IN_PROGRESS')
        return 'fixture-admin'
    assert acquire_guard_admin(busy_then_ready, pause=waited.append) == 'fixture-admin'
    assert waited == [1, 1]
    def always_busy():
        raise RuntimeError('ADMINISTRATOR_OPERATION_IN_PROGRESS')
    waited.clear()
    with pytest.raises(RuntimeError, match='ADMINISTRATOR_OPERATION_IN_PROGRESS'):
        acquire_guard_admin(always_busy, pause=waited.append)
    assert len(waited) == 45
    def unrelated_failure():
        raise RuntimeError('FIXTURE_ACCOUNT_ERROR')
    waited.clear()
    with pytest.raises(RuntimeError, match='FIXTURE_ACCOUNT_ERROR'):
        acquire_guard_admin(unrelated_failure, pause=waited.append)
    assert not waited


@pytest.mark.parametrize('changed,blocked', [(False, True), (True, True), (False, False)])
def test_deployment_preserves_only_same_provider_quote(monkeypatch, changed, blocked):
    from types import SimpleNamespace

    import deploy_product_services as deploy
    prior = {'account_id':'fixture-account','quote':{'model':'fixture-model',
             'input_micro_usd_per_million':100000,'output_micro_usd_per_million':200000}}
    current = json.loads(json.dumps(prior))
    current['quote']['observed_at'] = 'fixture-new-observation'
    if changed:
        current['quote']['model'] = 'other'
    closed = []
    class Admin:
        state = {'control_machine_id':'fixture-control'}
        def host(self, role, command):
            if command == 'cat /etc/machine-id':
                raw = b'fixture-control'
            elif command == 'cat /etc/proofflow-repair/config.json':
                raw = json.dumps(current).encode()
            else:
                raw = b't' if blocked else b'f'
            return SimpleNamespace(returncode=0, stdout=raw)
        def close(self):
            closed.append(True)
    monkeypatch.setattr(deploy, 'Admin', Admin)
    if changed or not blocked:
        with pytest.raises(RuntimeError):
            deploy.retained_provider(prior)
    else:
        assert deploy.retained_provider(prior) == current
    assert closed == [True]


def test_quote_rejects_changed_rate_model_or_reasoning():
    model = {
        "id": "qwen3.8-flash-next",
        "reasoning": {"mandatory": False},
        "input_modalities": [
            {"type": "text", "pricing": [{"unit": "token", "cost_usd": "0.0000001"}]}
        ],
        "output_modalities": [
            {"type": "text", "pricing": [{"unit": "token", "cost_usd": "0.0000002"}]}
        ],
    }
    now = datetime.now(UTC)
    assert (
        catalogue_quote(json.dumps({"data": [model]}).encode(), now)["input_micro_usd_per_million"]
        == 100000
    )
    for patch in (
        {"id": "other"},
        {"reasoning": {"mandatory": True}},
        {"output_modalities": model["input_modalities"]},
    ):
        with pytest.raises(RuntimeError):
            catalogue_quote(json.dumps({"data": [model | patch]}).encode(), now)
