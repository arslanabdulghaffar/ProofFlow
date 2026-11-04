"""Trusted administrator harness doubles; no credentials, provider or GitHub access."""

from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize("change", ["digest", "content", "expiry", "revoked", "approved", None])
def test_exact_admin_gate_does_not_rebind_or_repeat_approval(monkeypatch, change):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    from scripts.complete_phase4_pr_approval import approve_exact

    expected = {
        "preview_sha256": "a" * 64, "preview": {"body": "exact fixture"},
        "expires_at": "2026-11-05T00:10:00+00:00", "state": "PREVIEW",
        "currently_authorized": True, "approved_at": None,
    }
    record = {"pr_intent": "709af4a1-4367-44f8-884a-8b4ec4f86fe5", "pr": expected}
    current = deepcopy(expected)
    digest = "a" * 64
    if change == "digest":
        digest = "b" * 64
    elif change == "content":
        current["preview"]["body"] = "changed"
    elif change == "expiry":
        current["expires_at"] = "2026-11-04T00:00:00+00:00"
    elif change == "revoked":
        current["currently_authorized"] = False
    elif change == "approved":
        current["approved_at"] = "2026-11-05T00:00:00+00:00"
    posts = []

    def post(path, **kw):
        posts.append((path, kw))
        return SimpleNamespace(status_code=200)

    client = SimpleNamespace(
        get=lambda _: SimpleNamespace(status_code=200, json=lambda: current), post=post
    )
    now = datetime(2026, 11, 5, tzinfo=UTC)
    if change not in (None, "approved"):
        with pytest.raises(RuntimeError):
            approve_exact(client, record, digest, now)
    else:
        approve_exact(client, record, digest, now)
    assert len(posts) == (1 if change is None else 0)
    if posts:
        assert posts[0][1] == {"json": {"confirm": True, "preview_sha256": "a" * 64}}


@pytest.mark.parametrize("name", ["../escape.dpapi", "C:/escape.dpapi", "phase4-pr-X.dpapi"])
def test_private_session_names_fail_before_secret_access(monkeypatch, name):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    from scripts.check_phase4_expired_approval import existing_session
    from scripts.prepare_phase4_pr_preview import save_session

    for operation in (lambda: existing_session(name), lambda: save_session(None, name)):
        with pytest.raises(RuntimeError, match="PRIVATE_SESSION_NAME_INVALID"):
            operation()


@pytest.mark.parametrize("initial_session_status", [200, 403])
def test_refresh_reconciliation_never_posts_approval(monkeypatch, tmp_path, initial_session_status):
    import json

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    from scripts import check_phase4_expired_approval as probe

    evidence = tmp_path / "evidence"
    evidence.mkdir()
    identity = "709af4a1-4367-44f8-884a-8b4ec4f86fe5"
    (evidence / "phase4-pr-refresh-20261105.json").write_text(json.dumps({
        "pr_intent": identity, "session_file": "phase4-pr-" + identity.replace("-", "") + ".dpapi",
        "pr": {"expires_at": "2000-01-01T00:00:00+00:00", "preview_sha256": "a" * 64},
    }))
    posts = []

    class Client:
        status = initial_session_status

        def get(self, path):
            assert path == "/v1/session"
            return SimpleNamespace(status_code=self.status)

        def post(self, path):
            posts.append(path)
            assert path == "/v1/logout"
            self.status = 403
            return SimpleNamespace(status_code=204)

    class Live:
        credit = {"credit_guard": "fixture_only"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def sql(self, statement):
            if statement.startswith("SELECT count(*)"):
                return b"0"
            assert statement.startswith("SELECT jsonb_build_object(")
            return b'{"approved_at":null,"currently_authorized":false}'

    async def external_readback(intent):
        assert intent == identity
        return {"branch_exists": False, "pr_exists": False}

    monkeypatch.setattr(probe, "PRIVATE", tmp_path)
    monkeypatch.setattr(probe, "LiveSession", Live)
    monkeypatch.setattr(
        probe, "existing_session", lambda _: {"token": "fixture", "csrf": "fixture"}
    )
    monkeypatch.setattr(probe.ssl, "create_default_context", lambda **kw: None)
    monkeypatch.setattr(probe.httpx, "Client", lambda **kw: Client())
    monkeypatch.setattr(probe, "external_readback", external_readback)
    probe.main(refresh=True)
    assert posts == (["/v1/logout"] if initial_session_status == 200 else [])
    receipt = json.loads((evidence / "phase4-refresh-expired-result.json").read_bytes())
    assert receipt["approval_http_status"] is None
    assert receipt["durable_external_writes"] == 0
