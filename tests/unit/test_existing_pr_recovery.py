"""Recovery drill boundaries only; no credentials, subprocesses or network calls."""

import asyncio
from pathlib import Path

import pytest

from integrations.github_app import GitHubApp, GitHubConfig


@pytest.mark.parametrize("method,path,payload", [
    ("POST", "/repos/arslanabdulghaffar/ProofFlow-Demo/pulls", {}),
    ("PUT", "/repos/arslanabdulghaffar/ProofFlow-Demo/contents/pipeline.py", {}),
    ("POST", "/repos/arslanabdulghaffar/ProofFlow-Demo/git/refs", {}),
    ("DELETE", "/repos/arslanabdulghaffar/ProofFlow-Demo/pulls/1", None),
    ("POST", "/app/installations/12/access_tokens",
     {"repository_ids": [34], "permissions": {"contents": "write", "pull_requests": "write"}}),
    ("POST", "/app/installations/12/access_tokens",
     {"repository_ids": [35], "permissions": {"contents": "read", "pull_requests": "read"}}),
])
def test_drill_rejects_writes_before_network(monkeypatch, method, path, payload):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    from scripts.check_existing_pr_recovery import ReadOnlyApp

    async def unexpected(*args, **kwargs):
        pytest.fail("Mutation reached HTTP transport")

    monkeypatch.setattr(GitHubApp, "request", unexpected)
    app = ReadOnlyApp(GitHubConfig("Iv1.fixture", 12, 34), b"unused")
    with pytest.raises(RuntimeError, match="RECOVERY_GITHUB_WRITE_FORBIDDEN"):
        asyncio.run(app.request(method, path, "fixture", payload))
    assert app.calls == [] and app.denied_writes == 1


def test_recovery_store_cannot_dispatch_or_change_fixture_state(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    from scripts.check_existing_pr_recovery import FixtureStore

    store = FixtureStore(None)
    for operation in ("pr_begin", "pr_approve", "pr_request", "UPDATE", "seed"):
        with pytest.raises(RuntimeError, match="RECOVERY_STORE_WRITE_DISPATCH_FORBIDDEN"):
            asyncio.run(store.call(operation))
    assert store.operations == []
