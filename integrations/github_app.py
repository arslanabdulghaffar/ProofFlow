"""Fixed private GitHub App transport. Every external write is authorized by the outbox."""

import asyncio
import base64
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import wraps
from urllib.parse import quote

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

ORIGIN = "https://api.github.com"
PERMISSIONS = {"contents": "write", "pull_requests": "write", "metadata": "read"}
SHA = re.compile(r"^[a-f0-9]{40}$")


class GitHubFailure(Exception):
    """Stable code only; native errors, response bodies and credentials stay private."""


class GitHubUncertain(GitHubFailure):
    """A mutation might have been accepted. Reconcile; do not resend it."""


def require(value, code="GITHUB_RESPONSE_INVALID"):
    if not value:
        raise GitHubFailure(code)


def json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def b64url(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=")


def app_jwt(pem: bytes, issuer: str, now: int) -> str:
    require(type(pem) is bytes and 512 <= len(pem) <= 32768, "GITHUB_KEY_INVALID")
    require(
        type(issuer) is str and re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", issuer),
        "GITHUB_APP_ID_INVALID",
    )
    require(type(now) is int and now > 0, "GITHUB_CLOCK_INVALID")
    try:
        key = serialization.load_pem_private_key(pem, password=None)
        require(
            isinstance(key, rsa.RSAPrivateKey) and 2048 <= key.key_size <= 8192,
            "GITHUB_KEY_INVALID",
        )
        message = (
            b64url(json_bytes({"alg": "RS256", "typ": "JWT"}))
            + b"."
            + b64url(json_bytes({"iat": now - 60, "exp": now + 300, "iss": issuer}))
        )
        signature = key.sign(message, padding.PKCS1v15(), hashes.SHA256())
        return (message + b"." + b64url(signature)).decode("ascii")
    except (ValueError, TypeError):
        raise GitHubFailure("GITHUB_KEY_INVALID") from None


def blob_sha(raw: bytes) -> str:
    # Git object identity is SHA1; approval integrity separately uses SHA256.
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode() + b"\0" + raw, usedforsecurity=False
    ).hexdigest()


def _pairs(items):
    value = {}
    for key, item in items:
        if key in value:
            raise ValueError("duplicate")
        value[key] = item
    return value


def checked_shape(method):
    """Malformed upstream shapes have a fixed diagnostic, never native detail."""

    @wraps(method)
    async def wrapped(*args, **kwargs):
        try:
            return await method(*args, **kwargs)
        except (AttributeError, KeyError, IndexError, TypeError, ValueError):
            raise GitHubFailure("GITHUB_RESPONSE_INVALID") from None

    return wrapped


@dataclass(frozen=True)
class GitHubConfig:
    client_id: str
    installation_id: int
    repository_id: int
    owner: str = "arslanabdulghaffar"
    repository: str = "ProofFlow-Demo"
    base: str = "main"
    path: str = "pipeline.py"

    def __post_init__(self):
        require(
            type(self.installation_id) is int and 0 < self.installation_id < 2**63,
            "GITHUB_CONFIGURATION_INVALID",
        )
        require(
            type(self.repository_id) is int and 0 < self.repository_id < 2**63,
            "GITHUB_CONFIGURATION_INVALID",
        )
        require(
            re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", self.client_id), "GITHUB_CONFIGURATION_INVALID"
        )
        require(
            (self.owner, self.repository, self.base, self.path)
            == ("arslanabdulghaffar", "ProofFlow-Demo", "main", "pipeline.py"),
            "GITHUB_CONFIGURATION_INVALID",
        )

    @property
    def prefix(self):
        return "/repos/" + self.owner + "/" + self.repository


@dataclass
class GitHubApp:
    config: GitHubConfig
    pem: bytes = field(repr=False)

    async def request(self, method, path, token, payload=None, *, missing=False, array=False):
        require(
            method in ("GET", "POST", "PUT")
            and path.startswith("/")
            and not path.startswith("//")
            and "://" not in path
            and "\n" not in path,
            "GITHUB_OPERATION_INVALID",
        )
        require(
            type(token) is str
            and 1 <= len(token) <= 4096
            and all(33 <= ord(c) <= 126 for c in token),
            "GITHUB_TOKEN_INVALID",
        )
        try:
            async with asyncio.timeout(20):
                async with httpx.AsyncClient(
                    verify=True,
                    trust_env=False,
                    follow_redirects=False,
                    timeout=httpx.Timeout(15, connect=5),
                    limits=httpx.Limits(max_connections=1, max_keepalive_connections=0),
                ) as client:
                    async with client.stream(
                        method,
                        ORIGIN + path,
                        content=(json_bytes(payload) if payload is not None else None),
                        headers={
                            "Authorization": "Bearer " + token,
                            "Accept": "application/vnd.github+json",
                            "X-GitHub-Api-Version": "2026-03-10",
                            "Content-Type": "application/json",
                            "Accept-Encoding": "identity",
                            "User-Agent": "ProofFlow-private-app",
                        },
                    ) as response:
                        if missing and method == "GET" and response.status_code == 404:
                            return None
                        if response.status_code not in (200, 201):
                            if method != "GET":
                                raise GitHubUncertain("GITHUB_WRITE_UNCONFIRMED")
                            raise GitHubFailure("GITHUB_READ_REJECTED")
                        require(
                            response.headers.get("content-type", "").split(";")[0]
                            == "application/json",
                            "GITHUB_ENCODING_INVALID",
                        )
                        require(
                            response.headers.get("content-encoding", "identity") == "identity",
                            "GITHUB_ENCODING_INVALID",
                        )
                        raw = bytearray()
                        async for block in response.aiter_raw(chunk_size=4096):
                            raw.extend(block)
                            require(len(raw) <= 262144, "GITHUB_RESPONSE_LIMIT")
            value = json.loads(
                raw,
                object_pairs_hook=_pairs,
                parse_constant=lambda _: (_ for _ in ()).throw(ValueError("constant")),
            )
            require(type(value) is (list if array else dict))
            return value
        except (
            httpx.HTTPError,
            httpx.StreamError,
            OSError,
            TimeoutError,
            ValueError,
            RecursionError,
        ):
            if method != "GET":
                raise GitHubUncertain("GITHUB_WRITE_UNCONFIRMED") from None
            raise GitHubFailure("GITHUB_READ_UNAVAILABLE") from None
        except GitHubFailure:
            if method != "GET":
                raise GitHubUncertain("GITHUB_WRITE_UNCONFIRMED") from None
            raise

    @checked_shape
    async def token(self):
        jwt = app_jwt(self.pem, self.config.client_id, int(datetime.now(UTC).timestamp()))
        installation = await self.request(
            "GET", "/app/installations/" + str(self.config.installation_id), jwt
        )
        require(
            installation.get("repository_selection") == "selected"
            and installation.get("permissions") == PERMISSIONS
            and installation.get("account", {}).get("login") == self.config.owner
            and installation.get("suspended_at") is None,
            "GITHUB_INSTALLATION_SCOPE_INVALID",
        )
        issued = await self.request(
            "POST",
            "/app/installations/" + str(self.config.installation_id) + "/access_tokens",
            jwt,
            {
                "repository_ids": [self.config.repository_id],
                "permissions": {"contents": "write", "pull_requests": "write"},
            },
        )
        require(issued.get("permissions") == PERMISSIONS, "GITHUB_TOKEN_SCOPE_INVALID")
        try:
            expiry = datetime.fromisoformat(issued["expires_at"].replace("Z", "+00:00"))
            seconds = (expiry - datetime.now(UTC)).total_seconds()
            require(30 < seconds <= 3660, "GITHUB_TOKEN_EXPIRY_INVALID")
            token = issued["token"]
        except (KeyError, TypeError, ValueError):
            raise GitHubFailure("GITHUB_TOKEN_INVALID") from None
        allowed = await self.request("GET", "/installation/repositories?per_page=100", token)
        require(
            allowed.get("total_count") == 1 and len(allowed.get("repositories", [])) == 1,
            "GITHUB_TOKEN_SCOPE_INVALID",
        )
        repo = allowed["repositories"][0]
        require(
            repo.get("id") == self.config.repository_id
            and repo.get("private") is True
            and repo.get("full_name") == self.config.owner + "/" + self.config.repository,
            "GITHUB_REPOSITORY_IDENTITY_CHANGED",
        )
        return token

    @checked_shape
    async def inspect_base(self, token):
        root = self.config.prefix
        repo = await self.request("GET", root, token)
        require(
            repo.get("id") == self.config.repository_id
            and repo.get("private") is True
            and repo.get("full_name") == self.config.owner + "/" + self.config.repository
            and repo.get("default_branch") == self.config.base
            and repo.get("archived") is False
            and repo.get("fork") is False,
            "GITHUB_REPOSITORY_IDENTITY_CHANGED",
        )
        ref = await self.request("GET", root + "/git/ref/heads/" + self.config.base, token)
        sha = ref.get("object", {}).get("sha")
        require(
            type(sha) is str
            and SHA.fullmatch(sha)
            and ref.get("ref") == "refs/heads/" + self.config.base
            and ref.get("object", {}).get("type") == "commit",
            "GITHUB_BASE_INVALID",
        )
        commit = await self.request("GET", root + "/git/commits/" + sha, token)
        tree_sha = commit.get("tree", {}).get("sha")
        require(type(tree_sha) is str and SHA.fullmatch(tree_sha), "GITHUB_TREE_INVALID")
        tree = await self.request("GET", root + "/git/trees/" + tree_sha + "?recursive=1", token)
        entries = tree.get("tree")
        require(
            tree.get("truncated") is False and type(entries) is list and 1 <= len(entries) <= 2,
            "GITHUB_DEDICATED_REPO_REQUIRED",
        )
        require(
            len({e.get("path") for e in entries}) == len(entries)
            and all(
                e.get("path") in ("README.md", self.config.path)
                and e.get("type") == "blob"
                and e.get("mode") == "100644"
                and type(e.get("sha")) is str
                and SHA.fullmatch(e["sha"])
                for e in entries
            ),
            "GITHUB_DEDICATED_REPO_REQUIRED",
        )
        prior = next((e["sha"] for e in entries if e["path"] == self.config.path), None)
        original = b""
        if prior:
            value = await self.request("GET", root + "/git/blobs/" + prior, token)
            require(
                value.get("encoding") == "base64" and type(value.get("content")) is str,
                "GITHUB_BLOB_INVALID",
            )
            try:
                original = base64.b64decode(value["content"].replace("\n", ""), validate=True)
            except ValueError:
                raise GitHubFailure("GITHUB_BLOB_INVALID") from None
            require(len(original) <= 16384 and blob_sha(original) == prior, "GITHUB_BLOB_INVALID")
        return {
            "repository_id": self.config.repository_id,
            "base_sha": sha,
            "base_tree_sha": tree_sha,
            "prior_blob": prior,
            "original": original,
        }

    @staticmethod
    def branch(intent):
        from uuid import UUID

        return "proofflow/intent-" + UUID(str(intent)).hex

    @checked_shape
    async def read_branch(self, token, intent):
        value = await self.request(
            "GET", self.config.prefix + "/git/ref/heads/" + self.branch(intent), token, missing=True
        )
        if value is None:
            return None
        require(
            value.get("ref") == "refs/heads/" + self.branch(intent)
            and value.get("object", {}).get("type") == "commit"
            and type(value.get("object", {}).get("sha")) is str
            and SHA.fullmatch(value["object"]["sha"]),
            "GITHUB_BRANCH_CHANGED",
        )
        return value["object"]["sha"]

    async def create_branch(self, token, intent, base_sha):
        require(SHA.fullmatch(base_sha), "GITHUB_BASE_INVALID")
        return await self.request(
            "POST",
            self.config.prefix + "/git/refs",
            token,
            {"ref": "refs/heads/" + self.branch(intent), "sha": base_sha},
        )

    async def put_candidate(self, token, intent, source, prior_blob):
        require(type(source) is bytes and 0 < len(source) <= 16384, "GITHUB_CANDIDATE_INVALID")
        payload = {
            "message": "ProofFlow verified candidate " + self.branch(intent).split("-")[-1],
            "branch": self.branch(intent),
            "content": base64.b64encode(source).decode(),
        }
        if prior_blob is not None:
            require(SHA.fullmatch(prior_blob), "GITHUB_BLOB_INVALID")
            payload["sha"] = prior_blob
        return await self.request(
            "PUT", self.config.prefix + "/contents/" + self.config.path, token, payload
        )

    @checked_shape
    async def verify_commit(self, token, intent, head, base_sha, source):
        require(SHA.fullmatch(head) and SHA.fullmatch(base_sha), "GITHUB_COMMIT_INVALID")
        commit = await self.request("GET", self.config.prefix + "/git/commits/" + head, token)
        require(
            commit.get("sha") == head
            and len(commit.get("parents", [])) == 1
            and commit["parents"][0].get("sha") == base_sha
            and commit.get("message")
            == "ProofFlow verified candidate " + self.branch(intent).split("-")[-1],
            "GITHUB_COMMIT_CHANGED",
        )
        # Compare API confirms no other path changed, not just the candidate hash.
        diff = await self.request(
            "GET", self.config.prefix + "/compare/" + base_sha + "..." + head, token
        )
        files = diff.get("files", [])
        require(
            diff.get("total_commits") == 1
            and len(files) == 1
            and files[0].get("filename") == self.config.path
            and files[0].get("status") in ("added", "modified")
            and files[0].get("sha") == blob_sha(source),
            "GITHUB_DIFF_CHANGED",
        )
        value = await self.request(
            "GET", self.config.prefix + "/contents/" + self.config.path + "?ref=" + head, token
        )
        require(
            value.get("type") == "file" and value.get("encoding") == "base64", "GITHUB_BLOB_INVALID"
        )
        try:
            captured = base64.b64decode(value["content"].replace("\n", ""), validate=True)
        except (ValueError, KeyError, TypeError):
            raise GitHubFailure("GITHUB_BLOB_INVALID") from None
        require(
            captured == source and value.get("sha") == blob_sha(source), "GITHUB_CANDIDATE_CHANGED"
        )
        return head

    async def find_pr(self, token, intent):
        values = await self.request(
            "GET",
            self.config.prefix
            + "/pulls?state=all&head="
            + quote(self.config.owner + ":" + self.branch(intent), safe="")
            + "&base="
            + self.config.base
            + "&per_page=100",
            token,
            array=True,
        )
        require(type(values) is list and len(values) <= 1, "GITHUB_PR_IDENTITY_AMBIGUOUS")
        return values[0] if values else None

    async def create_pr(self, token, intent, title, body):
        require(
            type(title) is str and len(title) <= 120 and type(body) is str and len(body) <= 4096,
            "GITHUB_PR_TEXT_INVALID",
        )
        return await self.request(
            "POST",
            self.config.prefix + "/pulls",
            token,
            {
                "title": title,
                "body": body,
                "head": self.branch(intent),
                "base": self.config.base,
                "draft": True,
                "maintainer_can_modify": False,
            },
        )

    def verify_pr(self, value, intent, head, base_sha, title, body):
        require(
            type(value.get("head")) is dict
            and type(value.get("base")) is dict
            and type(value["head"].get("repo")) is dict
            and type(value["base"].get("repo")) is dict,
            "GITHUB_PR_INVALID",
        )
        require(
            type(value) is dict and type(value.get("number")) is int and value["number"] > 0,
            "GITHUB_PR_INVALID",
        )
        require(
            value.get("draft") is True
            and value.get("state") == "open"
            and value.get("title") == title
            and value.get("body") == body
            and value.get("head", {}).get("sha") == head
            and value["head"].get("ref") == self.branch(intent)
            and value["head"].get("repo", {}).get("id") == self.config.repository_id
            and value.get("base", {}).get("sha") == base_sha
            and value["base"].get("ref") == self.config.base
            and value["base"].get("repo", {}).get("id") == self.config.repository_id
            and value.get("html_url")
            == "https://github.com/"
            + self.config.owner
            + "/"
            + self.config.repository
            + "/pull/"
            + str(value["number"]),
            "GITHUB_PR_CHANGED",
        )
        return {
            "number": value["number"],
            "url": value["html_url"],
            "head_sha": head,
            "base_sha": base_sha,
            "draft": True,
            "repository_id": self.config.repository_id,
        }
