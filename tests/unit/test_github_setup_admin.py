"""Read-only administrator preflight doubles, never real credential manager or GitHub."""

import asyncio
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest

from integrations.github_app import GitHubConfig, GitHubFailure


@pytest.mark.parametrize("failure", [None, "actions", "hooks"])
def test_admin_preflight_uses_development_credential_only_for_get(monkeypatch, failure):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    from scripts import prepare_github_app as setup

    calls = []
    config = asdict(GitHubConfig("Iv1.fixture", 12, 34))
    config.pop("repository_id")
    config["installation_id"] = "12"
    monkeypatch.setattr(
        setup.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout="password=synthetic-credential\n"),
    )
    monkeypatch.setattr(setup, "app_jwt", lambda *a: "synthetic-jwt")

    class App:
        def __init__(self, cfg, pem):
            self.config = cfg

        async def request(self, method, path, token, **kwargs):
            calls.append((method, path, token))
            if path.endswith("/actions/permissions"):
                return {"enabled": failure == "actions"}
            if "/hooks?" in path:
                return [{"inert": "hook"}] if failure == "hooks" else []
            return {"private": True, "default_branch": "main", "id": 34}

        async def token(self):
            return "scoped-synthetic-token"

        async def inspect_base(self, token):
            assert token == "scoped-synthetic-token"  # noqa: S105 - labeled credential double
            return {"base_sha": "a" * 40}

    monkeypatch.setattr(setup, "GitHubApp", App)
    if failure:
        with pytest.raises(GitHubFailure, match="GITHUB_ACTIONS_AND_HOOKS_MUST_BE_DISABLED"):
            asyncio.run(setup.preflight(config, b"fixture"))
    else:
        app, base = asyncio.run(setup.preflight(config, b"fixture"))
        assert app.config.repository_id == 34 and base["base_sha"] == "a" * 40
    assert len(calls) == 3 and all(c[0] == "GET" and c[2] == "synthetic-credential" for c in calls)
