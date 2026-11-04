"""HTTP framing/ordering tests with labeled in-memory DB/storage doubles.

Real SQL concurrency and filesystem attack tests live in separate Linux checks.
No candidate source is executed; upload bytes are inert.
"""

import asyncio
import hashlib
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from api.app.auth import SessionSecrets, csrf_digest, session_digest
from api.app.product import CapacityBoundary, create_product_app
from api.app.product_store import ProductConnection, ProductFailure, ProductStore

ORIGIN = "https://proofflow.internal:8443"


class FixtureStore:
    def __init__(self):
        self.secrets = SessionSecrets.create()
        self.workspace = uuid4()
        self.events = []
        self.registry = {}
        self.failure = None
        self.asset_reads = 0
        self.revoke_on_readback = False
        self.job_result = None

    async def call(self, operation, *values):
        self.events.append(operation)
        if self.failure == operation:
            raise ProductFailure("ASSET_QUOTA" if operation == "reserve"
                                 else "PRODUCT_OPERATION_UNCERTAIN")
        if operation == "session":
            if values[0] != session_digest(self.secrets.token):
                raise ProductFailure("ACCESS_DENIED")
            return self.workspace, "operator", datetime.now(UTC)
        if values[0] != self.workspace:
            raise ProductFailure("ACCESS_DENIED")
        if operation in ("reserve", "publish", "approve", "enqueue", "cancel", "logout"):
            if values[2] != csrf_digest(self.secrets.csrf):
                raise ProductFailure("ACCESS_DENIED")
        if operation == "reserve":
            return (True,)
        if operation == "publish":
            self.registry[values[3]] = values[4:]
            return (True,)
        if operation == "asset":
            self.asset_reads += 1
            if self.revoke_on_readback and self.asset_reads == 2:
                raise ProductFailure("ACCESS_DENIED")
            return self.registry.get(values[2])
        if operation in ("approve", "cancel", "logout"):
            return (True,)
        if operation == "enqueue":
            return (values[3],)
        if operation == "job":
            return (self.job_result,)
        raise AssertionError("Unexpected fixture operation")


class FixtureAssets:
    def __init__(self, store):
        self.store = store
        self.values = {}
        self.failure = False

    def put(self, workspace, raw):
        self.store.events.append("bytes_published")
        if self.failure:
            raise ProductFailure("ASSET_PUBLICATION_UNCERTAIN")
        digest = hashlib.sha256(raw).hexdigest()
        self.values[(workspace, digest)] = raw
        return digest

    def read(self, workspace, digest):
        self.store.events.append("bytes_read")
        return self.values[(workspace, digest)]


def fixture():
    db = FixtureStore()
    assets = FixtureAssets(db)
    app = create_product_app(db, assets, origin=ORIGIN)
    headers = {"Cookie": "__Host-proofflow=" + db.secrets.token, "Origin": ORIGIN,
               "X-Proofflow-CSRF": db.secrets.csrf}
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN,
                              headers=headers)
    return db, assets, client


def test_upload_reservation_commit_precedes_bytes_and_registry():
    async def check():
        db, _, client = fixture()
        async with client:
            response = await client.post("/v1/assets/pipeline/" + str(uuid4()), content=b"# inert")
            assert response.status_code == 201
            assert db.events == ["session", "reserve", "bytes_published", "publish"]
            assert response.headers["cache-control"] == "no-store"
            assert response.json()["validation"] == "unvalidated"
    asyncio.run(check())


@pytest.mark.parametrize("failure,expected", [("reserve", ["session", "reserve"]),
    ("disk", ["session", "reserve", "bytes_published"]),
    ("publish", ["session", "reserve", "bytes_published", "publish"])])
def test_uncertain_failure_never_releases_reservation_or_claims_success(failure, expected):
    async def check():
        db, assets, client = fixture()
        db.failure = failure
        assets.failure = failure == "disk"
        async with client:
            response = await client.post("/v1/assets/pipeline/" + str(uuid4()), content=b"inert")
            assert response.status_code in (429, 503)
            assert db.events == expected
    asyncio.run(check())


@pytest.mark.parametrize("change", [{"Origin": "https://attacker.invalid"},
                                     {"X-Proofflow-CSRF": "bad"}, {"Sec-Fetch-Site": "cross-site"}])
def test_auth_framing_denies_before_database_or_storage(change):
    async def check():
        db, _, client = fixture()
        async with client:
            response = await client.post("/v1/assets/pipeline/" + str(uuid4()),
                                         content=b"inert", headers=change)
            assert response.status_code == 403 and db.events == []
    asyncio.run(check())


def test_chunked_size_limit_and_duplicate_headers():
    async def check():
        db, _, client = fixture()
        async with client:
            async def chunks():
                yield b"x" * 8192
                yield b"x" * 8193
            response = await client.post("/v1/assets/pipeline/" + str(uuid4()), content=chunks())
            assert response.status_code == 413 and "reserve" not in db.events
            response = await client.post("/v1/assets/pipeline/" + str(uuid4()), content=b"x",
                                         headers=[("Origin", ORIGIN), ("Origin", ORIGIN)])
            assert response.status_code == 403
    asyncio.run(check())


def test_download_checks_registry_before_bytes_and_again_before_disclosure():
    async def check():
        db, _, client = fixture()
        asset = uuid4()
        async with client:
            await client.post("/v1/assets/pipeline/" + str(asset), content=b"private inert source")
            db.events.clear()
            response = await client.get("/v1/assets/" + str(uuid4()) + "/download")
            assert response.status_code == 404 and "bytes_read" not in db.events
            db.asset_reads = 0
            db.revoke_on_readback = True
            response = await client.get("/v1/assets/" + str(asset) + "/download")
            assert response.status_code == 403 and b"private inert source" not in response.content
    asyncio.run(check())


def test_exact_contract_confirmation_and_invalid_json_have_no_approval():
    async def check():
        db, _, client = fixture()
        asset = uuid4()
        raw = Path("contracts/examples/synthetic-v1.1.json").read_bytes()
        async with client:
            uploaded = await client.post("/v1/assets/contract/" + str(asset), content=raw)
            digest = uploaded.json()["sha256"]
            url = "/v1/contracts/" + str(asset) + "/approve"
            for confirm in ("true", 1, False):
                response = await client.post(url,
                                             json={"expected_sha256": digest, "confirm": confirm})
                assert response.status_code == 409 and "approve" not in db.events
            response = await client.post(url, content=b'{"confirm":true,"confirm":true}')
            assert response.status_code == 422 and "approve" not in db.events
            response = await client.post(url, json={"expected_sha256": digest, "confirm": True})
            assert response.status_code == 200 and response.json()["approved"] is True
    asyncio.run(check())


def test_queue_accepts_only_asset_ids_and_returns_committed_job():
    async def check():
        db, _, client = fixture()
        value = {key: str(uuid4()) for key in ("idempotency_key", "pipeline_id", "transactions_id",
                                              "customers_id", "contract_id")}
        async with client:
            for extra in ("status", "runtime", "command", "verifier"):
                response = await client.post("/v1/jobs", json={**value, extra: "bypass"})
                assert response.status_code == 400 and "enqueue" not in db.events
            response = await client.post("/v1/jobs", json=value)
            assert response.status_code == 202
            assert response.json()["status_url"].endswith(response.json()["job_id"])
            assert (await client.get("/health/ready")).status_code == 503
    asyncio.run(check())


def test_capacity_is_held_until_body_finishes():
    async def check():
        gate = asyncio.Event()
        started = []
        messages = []
        async def application(scope, receive, send):
            started.append(scope["path"])
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await gate.wait()
            await send({"type": "http.response.body", "body": b"done"})
        async def send(message):
            messages.append(message)
        async def receive():
            return {"type": "http.request", "body": b""}
        app = CapacityBoundary(application)
        tasks = [asyncio.create_task(app({"type": "http", "path": str(i)}, receive, send))
                 for i in range(4)]
        while len(started) < 4:
            await asyncio.sleep(0)
        await app({"type": "http", "path": "fifth"}, receive, send)
        assert any(m.get("status") == 429 for m in messages) and len(started) == 4
        gate.set()
        await asyncio.gather(*tasks)
    asyncio.run(check())


def test_failure_view_escapes_recorded_witnesses_and_shows_durable_state():
    async def check():
        db, _, client = fixture()
        db.job_result = {"state": "NEEDS_REVIEW", "outcome": "mismatch", "report": {
            "semantic": {"report": {"result": {"blocking_occurrences": 0, "findings": [
                {"check": "V04", "code": "OWNER_MISMATCH"}], "ownership_witnesses": [
                    {"merchant_id": "M", "customer_id": "C", "expected_owner": "Correct owner",
                     "actual_owner": "<script>alert('inert')</script>"}]}}}}}
        async with client:
            response = await client.get("/jobs/" + str(uuid4()))
            assert response.status_code == 200
            assert "Needs Review" in response.text and "Correct owner" in response.text
            assert "<script>" not in response.text and "&lt;script&gt;" in response.text
            assert response.headers["content-security-policy"].startswith("default-src 'none'")
    asyncio.run(check())


def test_product_connection_fixed_identity_environment_and_operation_boundary(monkeypatch):
    secret = "synthetic-fixture-password-" + "a" * 40
    config = ProductConnection(secret)
    assert secret not in repr(config)
    params = config.parameters()
    assert params["dbname"] == "proofflow_product" and params["user"] == "pf_product_api_login"
    assert params["require_auth"] == "scram-sha-256"
    with pytest.raises(ProductFailure, match="PRODUCT_OPERATION_INVALID"):
        asyncio.run(ProductStore(config).call("claim", uuid4()))
    monkeypatch.setenv("PGSERVICE", "hostile")
    with pytest.raises(ProductFailure, match="PRODUCT_CONFIGURATION_INVALID"):
        config.parameters()
