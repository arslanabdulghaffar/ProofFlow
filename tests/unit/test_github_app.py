"""No GitHub network calls: fixed transport and readback contract doubles."""

import asyncio
import base64
import json
from uuid import uuid4

import httpx
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from integrations.github_app import (
    GitHubApp,
    GitHubConfig,
    GitHubFailure,
    GitHubUncertain,
    app_jwt,
    blob_sha,
)


def test_app_jwt_is_rsa_fixed_algorithm_short_lived_and_verifiable():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    value = app_jwt(pem, "Iv1.test", 1800000000)
    header, body, signature = value.split(".")

    def decoded(text):
        return base64.urlsafe_b64decode(text + "=" * ((-len(text)) % 4))

    assert json.loads(decoded(header)) == {"alg": "RS256", "typ": "JWT"}
    assert json.loads(decoded(body)) == {"iss": "Iv1.test", "iat": 1799999940, "exp": 1800000300}
    key.public_key().verify(
        decoded(signature), (header + "." + body).encode(), padding.PKCS1v15(), hashes.SHA256()
    )
    with pytest.raises(GitHubFailure):
        app_jwt(b"bad", "Iv1.test", 1800000000)
    with pytest.raises(GitHubFailure):
        GitHubConfig("id", 1, 2, repository="ProofFlow")


@pytest.mark.parametrize("mode", ["timeout", "redirect", "bad_json", "oversize"])
def test_mutation_uncertainty_is_not_retried_and_fixed_tls_destination(monkeypatch, mode):
    original = httpx.AsyncClient
    requests, settings = [], []

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"x" * 262145 if mode == "oversize" else b'{"x":1,"x":2}'

    def handler(request):
        requests.append(request)
        if mode == "timeout":
            raise httpx.ReadTimeout("fixture")
        if mode == "redirect":
            return httpx.Response(302, headers={"location": "https://attacker.invalid"})
        if mode == "oversize":
            return httpx.Response(
                200, headers={"content-type": "application/json"}, stream=Stream()
            )
        return httpx.Response(201, headers={"content-type": "application/json"}, stream=Stream())

    def client(**kwargs):
        settings.append(kwargs)
        return original(**kwargs, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(httpx, "AsyncClient", client)
    app = GitHubApp(GitHubConfig("id", 1, 2), b"not used")
    with pytest.raises(GitHubUncertain):
        asyncio.run(app.create_branch("fixture-token", uuid4(), "a" * 40))
    assert len(requests) == 1
    assert requests[0].url.host == "api.github.com"
    assert requests[0].method == "POST"
    assert settings[0]["verify"] is True and settings[0]["trust_env"] is False
    assert settings[0]["follow_redirects"] is False


def test_commit_requires_single_allowed_path_exact_candidate_and_parent():
    app = GitHubApp(GitHubConfig("id", 1, 2), b"unused")
    identity = uuid4()
    source = b"# inert candidate\n"
    extra = False

    async def request(method, path, token, payload=None, **kwargs):
        if "/git/commits/" in path:
            return {
                "sha": "b" * 40,
                "parents": [{"sha": "a" * 40}],
                "message": "ProofFlow verified candidate " + identity.hex,
            }
        if "/compare/" in path:
            files = [{"filename": "pipeline.py", "status": "added", "sha": blob_sha(source)}]
            if extra:
                files.append({"filename": ".github/workflows/run.yml"})
            return {"total_commits": 1, "files": files}
        return {
            "type": "file",
            "encoding": "base64",
            "content": base64.b64encode(source).decode(),
            "sha": blob_sha(source),
        }

    app.request = request
    assert (
        asyncio.run(app.verify_commit("fixture", identity, "b" * 40, "a" * 40, source)) == "b" * 40
    )
    extra = True
    with pytest.raises(GitHubFailure, match="GITHUB_DIFF_CHANGED"):
        asyncio.run(app.verify_commit("fixture", identity, "b" * 40, "a" * 40, source))


@pytest.mark.parametrize("changed", ["draft", "head", "base", "repo", "body", "url"])
def test_pr_readback_never_accepts_altered_identity_or_nondraft(changed):
    app = GitHubApp(GitHubConfig("id", 1, 2), b"unused")
    identity = uuid4()
    value = {
        "number": 7,
        "draft": True,
        "state": "open",
        "title": "review",
        "body": "bounded",
        "head": {"sha": "b" * 40, "ref": app.branch(identity), "repo": {"id": 2}},
        "base": {"sha": "a" * 40, "ref": "main", "repo": {"id": 2}},
        "html_url": "https://github.com/arslanabdulghaffar/ProofFlow-Demo/pull/7",
    }
    assert app.verify_pr(value, identity, "b" * 40, "a" * 40, "review", "bounded")["number"] == 7
    if changed == "draft":
        value["draft"] = False
    elif changed in ("head", "base"):
        value[changed]["sha"] = "c" * 40
    elif changed == "repo":
        value["head"]["repo"]["id"] = 3
    elif changed == "body":
        value["body"] = "altered"
    else:
        value["html_url"] = "https://attacker.invalid"
    with pytest.raises(GitHubFailure, match="GITHUB_PR_CHANGED"):
        app.verify_pr(value, identity, "b" * 40, "a" * 40, "review", "bounded")


def test_broad_installation_scope_rejected_before_minting_token():
    app = GitHubApp(GitHubConfig("id", 1, 2), b"unused")
    calls = []

    async def request(*args, **kwargs):
        calls.append(args)
        return {"repository_selection": "all", "permissions": {}}

    app.request = request
    # Key signing is tested separately; no real secret or network is involved.
    from unittest.mock import patch

    import integrations.github_app as module

    with patch.object(module, "app_jwt", return_value="fixture"):
        with pytest.raises(GitHubFailure, match="GITHUB_INSTALLATION_SCOPE_INVALID"):
            asyncio.run(app.token())
    assert len(calls) == 1 and calls[0][0] == "GET"
