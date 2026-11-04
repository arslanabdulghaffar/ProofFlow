"""HTTP framing/ordering tests with labeled in-memory DB/storage doubles.

Real SQL concurrency and filesystem attack tests live in separate Linux checks.
No candidate source is executed; upload bytes are inert.
"""

import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
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
        self.job_events = []
        self.event_reads = 0
        self.revoke_events = False

    async def call(self, operation, *values):
        self.events.append(operation)
        if self.failure == operation:
            raise ProductFailure("ASSET_QUOTA" if operation == "reserve"
                                 else "PRODUCT_OPERATION_UNCERTAIN")
        if operation in ("session", "browser_session"):
            if values[0] != session_digest(self.secrets.token):
                raise ProductFailure("ACCESS_DENIED")
            if operation == "browser_session" and values[1] != csrf_digest(self.secrets.csrf):
                raise ProductFailure("ACCESS_DENIED")
            return self.workspace, "operator", datetime.now(UTC) + timedelta(hours=1)
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
        if operation in ("approve", "cancel", "logout", "delete"):
            return (True,)
        if operation == "enqueue":
            return (values[3],)
        if operation == "job":
            return (self.job_result,)
        if operation == "events":
            self.event_reads += 1
            if self.revoke_events and self.event_reads > 1:
                raise ProductFailure("ACCESS_DENIED")
            return ([e for e in self.job_events if int(e["sequence"]) > values[3]],)
        raise AssertionError("Unexpected fixture operation")


class FixtureAssets:
    def __init__(self, store):
        self.store = store
        self.values = {}
        self.failure = False

    def assert_live(self, workspace):
        assert workspace == self.store.workspace

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


def test_event_replay_resume_terminal_and_bound_cursor():
    async def check():
        db, _, client = fixture()
        job = str(uuid4())
        db.job_events = [{"sequence": str(n), "state": state, "event": "recorded",
                          "occurred_at": "2026-11-04T00:00:00+00:00"}
                         for n, state in ((1, "QUEUED"), (2, "NEEDS_REVIEW"))]
        db.job_result = {"state": "NEEDS_REVIEW"}
        async with client:
            response = await client.get("/v1/jobs/" + job + "/events")
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            assert response.text.count("event: job_state") == 2
            assert '"sequence":"1"' in response.text
            resumed = await client.get("/v1/jobs/" + job + "/events",
                headers={"Last-Event-ID": job + ":1"})
            assert "id: " + job + ":1" not in resumed.text
            assert "id: " + job + ":2" in resumed.text
            ended = await client.get("/v1/jobs/" + job + "/events",
                headers={"Last-Event-ID": job + ":2"})
            assert ended.status_code == 204
            for value in (str(uuid4()) + ":1", job + ":-1", job + ":01",
                          job + ":9223372036854775808", job + ":1\n"):
                assert (await client.get("/v1/jobs/" + job + "/events",
                    headers={"Last-Event-ID": value})).status_code == 400
            assert (await client.get("/v1/jobs/" + job + "/events", headers=[
                ("Last-Event-ID", job + ":1"), ("Last-Event-ID", job + ":1")])).status_code == 400
    asyncio.run(check())


def test_event_revalidation_before_first_disclosure():
    async def check():
        db, _, client = fixture()
        db.job_events = [{"sequence": "1", "state": "NEEDS_REVIEW", "event": "secret"}]
        db.revoke_events = True
        async with client:
            response = await client.get("/v1/jobs/" + str(uuid4()) + "/events")
            assert response.status_code == 200
            assert "STREAM_AUTHORITY_OR_STORE_UNAVAILABLE" in response.text
            assert "secret" not in response.text and "id:" not in response.text
    asyncio.run(check())


def test_stream_capacity_reserves_other_request_slots():
    async def check():
        release, entered = asyncio.Event(), asyncio.Event()
        active = 0
        async def inner(scope, receive, send):
            nonlocal active
            if scope["path"].endswith("/events"):
                active += 1
                if active == 2:
                    entered.set()
                await release.wait()
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"", "more_body": False})
        boundary = CapacityBoundary(inner)
        async def receive():
            return {"type": "http.request", "body": b""}
        messages = []
        async def send(message):
            messages.append(message)
        streams = [asyncio.create_task(boundary({"type": "http", "path": "/events"},
                                               receive, send)) for _ in range(2)]
        await entered.wait()
        await boundary({"type": "http", "path": "/events"}, receive, send)
        assert messages[0]["status"] == 429
        messages.clear()
        await boundary({"type": "http", "path": "/health/live"}, receive, send)
        assert messages[0]["status"] == 200
        release.set()
        await asyncio.gather(*streams)
        assert boundary.slots._value == 4 and boundary.event_slots._value == 2
    asyncio.run(check())


def test_event_rechecks_session_between_frames():
    async def check():
        db = FixtureStore()
        db.job_events = [{"sequence": str(n), "state": state, "event": "recorded",
                          "occurred_at": "2026-11-04T00:00:00Z"}
                         for n, state in ((1, "QUEUED"), (2, "NEEDS_REVIEW"))]
        app = create_product_app(db, FixtureAssets(db), origin=ORIGIN)
        messages = []
        async def send(message):
            messages.append(message)
            if b"id: " in message.get("body", b""):
                db.secrets = SessionSecrets.create()  # Labeled revocation double after disclosure1.
        async def receive():
            await asyncio.Event().wait()
        scope = {"type": "http", "asgi": {"spec_version": "2.4"}, "method": "GET",
                 "scheme": "https", "path": "/v1/jobs/" + str(uuid4()) + "/events",
                 "query_string": b"", "headers": [(b"cookie", ("__Host-proofflow="
                                                   + db.secrets.token).encode())]}
        await app(scope, receive, send)
        raw = b"".join(m.get("body", b"") for m in messages)
        assert raw.count(b"id: ") == 1
        assert b"STREAM_AUTHORITY_OR_STORE_UNAVAILABLE" in raw
        assert b"NEEDS_REVIEW" not in raw
    asyncio.run(check())


def test_browser_bridge_exact_pair_cookie_flags_origin_and_no_authority_mint():
    async def check():
        db, _, client = fixture()
        data = {"session_token": db.secrets.token, "csrf_token": db.secrets.csrf}
        async with client:
            denied = await client.post("/v1/session/import", json=data,
                                       headers={"Origin": "https://foreign.invalid"})
            assert denied.status_code == 403 and "browser_session" not in db.events
            wrong = await client.post("/v1/session/import", json={**data,
                "csrf_token": SessionSecrets.create().csrf})
            assert wrong.status_code == 403
            good = await client.post("/v1/session/import", json=data)
            assert good.status_code == 200 and good.json()["workspace_id"] == str(db.workspace)
            cookies = good.headers.get_list("set-cookie")
            assert len(cookies) == 2
            assert "HttpOnly" in cookies[0] and "HttpOnly" not in cookies[1]
            assert all("Secure" in c and "SameSite=Strict" in c and "Domain=" not in c
                       for c in cookies)
            assert db.secrets.token not in good.text and db.secrets.csrf not in good.text
            assert "create_session" not in db.events
    asyncio.run(check())


@pytest.mark.parametrize("confirm", [False, 1, "true", None])
def test_delete_requires_literal_confirmation(confirm):
    async def check():
        db, _, client = fixture()
        async with client:
            result = await client.post("/v1/workspace/delete", json={
                "workspace_id": str(db.workspace), "confirm": confirm})
            assert result.status_code in (400, 409) and "delete" not in db.events
    asyncio.run(check())


def test_delete_is_exact_workspace_and_reports_only_queued():
    async def check():
        db, _, client = fixture()
        async with client:
            result = await client.post("/v1/workspace/delete", json={
                "workspace_id": str(uuid4()), "confirm": True})
            assert result.status_code == 409 and "delete" not in db.events
            result = await client.post("/v1/workspace/delete", json={
                "workspace_id": str(db.workspace), "confirm": True})
            assert result.json() == {"access_revoked": True, "deletion": "queued"}
    asyncio.run(check())


def test_static_allowlist_uniform_errors_and_private_exception_redaction():
    async def check():
        db, _, client = fixture()
        async with client:
            page = await client.get("/")
            assert page.status_code == 200 and "script-src 'self'" in page.headers[
                "content-security-policy"]
            for path in ("/static/auth.py", "/missing"):
                denied = await client.get(path)
                assert denied.status_code == 404
                assert denied.json()["error"]["request_id"] == denied.headers["x-request-id"]
            async def broken(*args):
                raise RuntimeError("private native error")
            db.call = broken
            failed = await client.get("/v1/session")
            assert failed.status_code == 500 and "private native" not in failed.text
            assert failed.json()["error"]["code"] == "INTERNAL_ERROR"
    asyncio.run(check())


def test_pipeline_rejects_non_utf8_before_reservation():
    async def check():
        db, _, client = fixture()
        async with client:
            for raw in (b"\xff", b"a\x00b"):
                result = await client.post("/v1/assets/pipeline/" + str(uuid4()), content=raw)
                assert result.status_code == 422 and "reserve" not in db.events
    asyncio.run(check())


def test_browser_summary_keeps_large_sequence_exact_and_strips_internal_receipts():
    async def check():
        db, _, client = fixture()
        db.job_result = {"state": "NEEDS_REVIEW", "outcome": "mismatch",
            "created_at": "2026-11-04T00:00:00Z", "sequence": 9007199254740993,
            "report": {"worker": {"private_internal": "not browser data"},
                "semantic": {"report": {"result": {"blocking_occurrences": 0,
                    "finding_count": 1, "findings": [{"check": "V04",
                        "code": "CANONICAL_CUSTOMER_MISMATCH", "source": "source:1"}],
                    "ownership_witnesses": []}}}}}
        async with client:
            response = await client.get("/v1/jobs/" + str(uuid4()) + "/summary")
            assert response.status_code == 200
            assert response.json()["sequence"] == "9007199254740993"
            assert "private_internal" not in response.text
            assert response.json()["finding_count"] == 1
    asyncio.run(check())
