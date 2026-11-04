"""Private authenticated Phase2 HTTP surface. No inference or candidate execution here."""

import asyncio
import difflib
import hashlib
import re
import time
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException

from api.app.auth import AuthError, SessionSecrets, request_digests
from api.app.evidence_bundle import build_bundle
from api.app.product_store import ProductFailure
from api.app.wire import (
    ApprovalResponse,
    AssetResponse,
    BrowserSessionRequest,
    CancellationResponse,
    DeleteRequest,
    DeleteResponse,
    EnqueueResponse,
    JobEvent,
    JobSummary,
    RepairExport,
    RepairResponse,
    RepairSummary,
    RevocationResponse,
    SessionResponse,
)
from contracts.codec import InputError, canonical_bytes, parse_object
from contracts.policy import parse_contract

LIMITS = {"pipeline": 16384, "contract": 32768, "transactions": 5242880, "customers": 5242880}
STATIC = Path(__file__).parent / "static"


def failure(scope, code, status):
    if re.fullmatch(r"[A-Z_]{1,80}", code) is None:
        code = "REQUEST_FAILED"
    return JSONResponse({"error": {"code": code,
        "message": "Request could not be completed. Check the recorded status before retrying.",
        "retryable": status in (429, 503), "request_id": scope["request_id"]}}, status_code=status)


class HttpFailure(Exception):
    def __init__(self, status, code):
        self.status, self.code = status, code


def identifier(value):
    try:
        parsed = UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise HttpFailure(400, "INVALID_IDENTIFIER") from None
    if str(parsed) != value:
        raise HttpFailure(400, "INVALID_IDENTIFIER")
    return parsed


async def body(request, limit):
    lengths = [v for k, v in request.scope["headers"] if k.lower() == b"content-length"]
    if len(lengths) > 1:
        raise HttpFailure(400, "INVALID_FRAMING")
    if lengths:
        if not lengths[0].isdigit() or len(lengths[0]) > 10:
            raise HttpFailure(400, "INVALID_FRAMING")
        if int(lengths[0]) > limit:
            raise HttpFailure(413, "BODY_LIMIT")
    raw = bytearray()
    async with asyncio.timeout(10):
        async for chunk in request.stream():
            if len(raw) + len(chunk) > limit:
                raise HttpFailure(413, "BODY_LIMIT")
            raw.extend(chunk)
    if not raw or lengths and int(lengths[0]) != len(raw):
        raise HttpFailure(400, "INVALID_FRAMING")
    return bytes(raw)


class CapacityBoundary:
    """Hold capacity through the final response byte, including slow downloads."""

    def __init__(self, app):
        self.app = app
        self.slots = asyncio.Semaphore(4)
        self.event_slots = asyncio.Semaphore(2)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        scope["request_id"] = str(uuid4())  # Never trust a caller-supplied request ID.

        async def protected_send(message):
            if message["type"] == "http.response.start":
                message = {**message, "headers": [*message.get("headers", []),
                    (b"cache-control", b"no-store"), (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"x-request-id", scope["request_id"].encode()),
                    (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'; "
                     b"base-uri 'none'; form-action 'self'; script-src 'self'; "
                     b"style-src 'self'; connect-src 'self'")]}
            await send(message)

        async def dispatch():
            started = False

            async def tracked_send(message):
                nonlocal started
                started |= message["type"] == "http.response.start"
                await protected_send(message)

            try:
                return await self.app(scope, receive, tracked_send)
            except Exception:
                if started:
                    raise
                return await failure(scope, "INTERNAL_ERROR", 500)(scope, receive, protected_send)
        if self.slots.locked():
            return await failure(scope, "BUSY", 429)(
                scope, receive, protected_send)
        async with self.slots:
            if scope.get("path", "").endswith("/events"):
                if self.event_slots.locked():
                    return await failure(scope, "STREAM_BUSY", 429)(
                        scope, receive, protected_send)
                async with self.event_slots:
                    try:
                        async with asyncio.timeout(65):
                            return await dispatch()
                    except TimeoutError:
                        # End this connection, not an invented event or resumed cursor.
                        return None
            return await dispatch()


def create_product_app(store, assets, *, origin: str, journals=None):
    bundle_slot = asyncio.Semaphore(1)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(CapacityBoundary)

    @app.exception_handler(HTTPException)
    async def route_failure(request, error):
        return failure(request.scope, "ROUTE_NOT_AVAILABLE", error.status_code)

    @app.exception_handler(TimeoutError)
    async def timeout_failure(request, __):
        return failure(request.scope, "REQUEST_TIMEOUT", 408)

    @app.exception_handler(HttpFailure)
    async def http_failure(request, error):
        return failure(request.scope, error.code, error.status)

    @app.exception_handler(AuthError)
    async def auth_failure(request, error):
        return failure(request.scope, str(error), 403)

    @app.exception_handler(InputError)
    async def input_failure(request, error):
        return failure(request.scope, str(error), 422)

    @app.exception_handler(ProductFailure)
    async def store_failure(request, error):
        code = str(error)
        status = (400 if code == "INVALID_EVENT_CURSOR" else 403 if code == "ACCESS_DENIED"
                  else 429 if code in ("ASSET_QUOTA", "JOB_CAPACITY", "VERSION_CAPACITY",
                                       "PR_CAPACITY",
                                       "BATCH_CONNECTION_CAPACITY", "BATCH_DELIVERY_CAPACITY")
                  else 404 if code in ("JOB_NOT_FOUND", "VERSION_NOT_FOUND")
                  else 409 if code.endswith("CONFLICT") or code in (
                      "CONTRACT_REVOKED", "EXACT_CONTRACT_REQUIRED", "VERSION_NOT_ELIGIBLE",
                      "GITHUB_NOT_CONFIGURED", "EXACT_PR_APPROVAL_REQUIRED", "PR_AUTHORITY_REVOKED",
                      "BATCH_CONNECTION_UNAVAILABLE", "BATCH_DELIVERY_INVALID",
                      "EXACT_VERSION_APPROVAL_REQUIRED", "VERSION_ASSET_MISMATCH") else 503)
        return failure(request.scope, code, status)

    @app.get("/", response_class=Response)
    async def intake():
        return Response((STATIC / "index.html").read_bytes(), media_type="text/html")

    @app.get("/static/{name}")
    async def static(name: str):
        types = {"github.js": "application/javascript", "versions.js": "application/javascript",
                 "intake.js": "application/javascript",
                 "recovery.js": "application/javascript",
                 "intake.css": "text/css"}
        if name not in types:
            raise HttpFailure(404, "ASSET_NOT_FOUND")
        return Response((STATIC / name).read_bytes(), media_type=types[name])

    @app.post("/v1/session/import")
    async def import_session(request: Request):
        try:
            value = BrowserSessionRequest.model_validate(parse_object(await body(request, 1024)))
        except ValidationError:
            raise HttpFailure(400, "INVALID_SESSION_FIELDS") from None
        headers = [(k, v) for k, v in request.scope["headers"]
                   if k.lower() not in (b"cookie", b"x-proofflow-csrf")]
        headers += [(b"cookie", ("__Host-proofflow=" + value.session_token).encode()),
                    (b"x-proofflow-csrf", value.csrf_token.encode())]
        token, csrf = request_digests(headers, expected_origin=origin, writing=True)
        workspace, kind, expiry = await store.call("browser_session", token, csrf)
        await asyncio.to_thread(assets.assert_live, workspace)
        age = max(1, min(43200, int((expiry - datetime.now(UTC)).total_seconds())))
        response = JSONResponse(SessionResponse(workspace_id=str(workspace), kind=kind,
                                                expires_at=expiry.isoformat()).model_dump())
        response.headers.append("Set-Cookie", SessionSecrets(value.session_token,
            value.csrf_token).cookie(max_age=age))
        response.headers.append("Set-Cookie", "__Host-proofflow-csrf=" + value.csrf_token
            + "; Path=/; Max-Age=" + str(age) + "; Secure; SameSite=Strict")
        return response

    async def authorize(request, writing=False):
        session, csrf = request_digests(request.scope["headers"], expected_origin=origin,
                                        writing=writing)
        row = await store.call("session", session)
        if row is None or len(row) != 3 or type(row[0]) is not UUID:
            raise ProductFailure("PRODUCT_RESULT_INVALID")
        await asyncio.to_thread(assets.assert_live, row[0])
        return row[0], session, csrf

    async def json_body(request, fields):
        value = parse_object(await body(request, 32768))
        if set(value) != set(fields):
            raise HttpFailure(400, "INVALID_FIELDS")
        return value

    @app.get("/health/live")
    async def live():
        return {"status": "alive"}

    @app.get("/health/ready", status_code=503)
    async def ready():
        return {"status": "not_ready", "reason": "product_acceptance_incomplete"}

    @app.get("/v1/session", response_model=SessionResponse)
    async def session(request: Request):
        workspace, token, _ = await authorize(request)
        _, kind, expiry = await store.call("session", token)
        return {"workspace_id": str(workspace), "kind": kind, "expires_at": expiry.isoformat()}

    @app.post("/v1/assets/{kind}/{asset_id}", status_code=201, response_model=AssetResponse)
    async def upload(kind: str, asset_id: str, request: Request):
        workspace, token, csrf = await authorize(request, True)
        asset = identifier(asset_id)
        if kind not in LIMITS:
            raise HttpFailure(400, "INVALID_ASSET_KIND")
        raw = await body(request, LIMITS[kind])
        if kind == "pipeline":
            try:
                source = raw.decode("utf-8", errors="strict")
            except UnicodeError:
                raise HttpFailure(422, "PIPELINE_ENCODING_INVALID") from None
            if "\x00" in source:
                raise HttpFailure(422, "PIPELINE_ENCODING_INVALID")
        digest = hashlib.sha256(raw).hexdigest()
        # A COMMIT failure cannot authorize filesystem writes. A publication or
        # finalization failure preserves the reservation, never silently frees it.
        await store.call("reserve", workspace, token, csrf, asset, kind, digest, len(raw))
        actual_digest = await asyncio.to_thread(assets.put, workspace, raw)
        if actual_digest != digest:
            raise ProductFailure("ASSET_BYTES_CHANGED")
        await store.call("publish", workspace, token, csrf, asset, kind, digest, len(raw))
        return {"asset_id": str(asset), "kind": kind, "sha256": digest, "bytes": len(raw),
                "validation": "unvalidated"}

    async def get_asset(request, asset_id, writing=False):
        workspace, token, csrf = await authorize(request, writing)
        asset = identifier(asset_id)
        row = await store.call("asset", workspace, token, asset)
        if row is None:
            raise HttpFailure(404, "ASSET_NOT_FOUND")
        kind, digest, size = row
        raw = await asyncio.to_thread(assets.read, workspace, digest)
        if len(raw) != size or hashlib.sha256(raw).hexdigest() != digest:
            raise ProductFailure("ASSET_BYTES_CHANGED")
        # Fresh authorization after the potentially slow read and before disclosure.
        again = await store.call("asset", workspace, token, asset)
        if again != row:
            raise ProductFailure("ASSET_AUTHORITY_CHANGED")
        return workspace, token, csrf, asset, kind, digest, raw

    @app.get("/v1/assets/{asset_id}/download")
    async def download(asset_id: str, request: Request):
        _, _, _, _, kind, _, raw = await get_asset(request, asset_id)
        return Response(raw, media_type="application/octet-stream", headers={
            "Content-Disposition": 'attachment; filename="' + kind + '.txt"'})

    @app.post("/v1/contracts/{asset_id}/approve", response_model=ApprovalResponse)
    async def approve(asset_id: str, request: Request):
        workspace, token, csrf, asset, kind, digest, raw = await get_asset(request, asset_id, True)
        value = await json_body(request, ("expected_sha256", "confirm"))
        if kind != "contract" or value["expected_sha256"] != digest or value["confirm"] is not True:
            raise HttpFailure(409, "EXACT_CONTRACT_REQUIRED")
        policy = parse_contract(raw)
        await store.call("approve", workspace, token, csrf, asset, digest)
        return {"asset_id": str(asset), "raw_sha256": digest, "canonical_sha256": policy.sha256,
                "approved": True}

    @app.post("/v1/contracts/{asset_id}/revoke", response_model=RevocationResponse)
    async def revoke(asset_id: str, request: Request):
        workspace, token, csrf = await authorize(request, True)
        await store.call("revoke_contract", workspace, token, csrf, identifier(asset_id))
        return {"revoked": True}

    @app.post("/v1/jobs", status_code=202, response_model=EnqueueResponse)
    async def enqueue(request: Request):
        workspace, token, csrf = await authorize(request, True)
        value = await json_body(request, ("idempotency_key", "pipeline_id", "transactions_id",
                                          "customers_id", "contract_id"))
        names = ("idempotency_key", "pipeline_id", "transactions_id", "customers_id", "contract_id")
        ids = [identifier(value[key]) for key in names]
        result = await store.call("enqueue", workspace, token, csrf, uuid4(), *ids)
        return {"job_id": str(result[0]), "status_url": "/v1/jobs/" + str(result[0])}

    @app.get("/v1/jobs/{job_id}")
    async def job(job_id: str, request: Request):
        workspace, token, _ = await authorize(request)
        result = await store.call("job", workspace, token, identifier(job_id))
        if result is None or result[0] is None:
            raise HttpFailure(404, "JOB_NOT_FOUND")
        return result[0]

    @app.get("/v1/jobs/{job_id}/summary", response_model=JobSummary)
    async def summary(job_id: str, request: Request):
        value = await job(job_id, request)
        semantic = (value.get("report") or {}).get("semantic") or {}
        report = semantic.get("report", {}).get("result", {})
        return {"wire_version": "proofflow-browser-v1", "job_id": job_id,
            "state": value["state"], "outcome": value["outcome"], "created_at": value["created_at"],
            "sequence": str(value["sequence"]),
            "blocking_occurrences": report.get("blocking_occurrences"),
            "finding_count": report.get("finding_count"), "findings": report.get("findings", []),
            "ownership_witnesses": report.get("ownership_witnesses", [])}

    @app.post("/v1/jobs/{job_id}/cancel", response_model=CancellationResponse)
    async def cancel(job_id: str, request: Request):
        workspace, token, csrf = await authorize(request, True)
        await store.call("cancel", workspace, token, csrf, identifier(job_id))
        return {"cancellation_requested": True}

    @app.post("/v1/repairs", status_code=202, response_model=RepairResponse)
    async def enqueue_repair(request: Request):
        workspace, token, csrf = await authorize(request, True)
        value = await json_body(request, ("parent_id", "idempotency_key"))
        result = await store.call("repair_enqueue", workspace, token, csrf, uuid4(),
            identifier(value["idempotency_key"]), identifier(value["parent_id"]))
        return {"repair_id": str(result[0]), "status_url": "/v1/repairs/" + str(result[0])}

    @app.get("/v1/repairs/{repair_id}", response_model=RepairSummary)
    async def repair_status(repair_id: str, request: Request):
        workspace, token, _ = await authorize(request)
        value = await store.call("repair_get", workspace, token, identifier(repair_id))
        if value is None or value[0] is None:
            raise HttpFailure(404, "JOB_NOT_FOUND")
        return value[0]

    @app.post("/v1/repairs/{repair_id}/cancel", response_model=CancellationResponse)
    async def repair_cancel(repair_id: str, request: Request):
        workspace, token, csrf = await authorize(request, True)
        await store.call("repair_cancel", workspace, token, csrf, identifier(repair_id))
        return {"cancellation_requested": True}

    @app.get("/v1/repairs/{repair_id}/export", response_model=RepairExport)
    async def repair_export(repair_id: str, request: Request):
        workspace, token, _ = await authorize(request)
        identity = identifier(repair_id)
        row = await store.call("repair_export", workspace, token, identity)
        if row is None or row[0] is None:
            raise HttpFailure(409, "REPAIR_PROOF_INCOMPLETE")
        value = row[0]
        raw = value["candidate_source"].encode("utf-8")
        if not 1 <= len(raw) <= 16384:
            raise ProductFailure("REPAIR_EXPORT_INVALID")
        original = await asyncio.to_thread(assets.read, workspace, value["original_sha256"])
        if await store.call("repair_export", workspace, token, identity) != row:
            raise ProductFailure("REPAIR_AUTHORITY_CHANGED")
        diff = "".join(difflib.unified_diff(original.decode("utf-8").splitlines(keepends=True),
            raw.decode("utf-8").splitlines(keepends=True), fromfile="original/pipeline.py",
            tofile="candidate/pipeline.py"))
        return JSONResponse({"repair_id": repair_id,
            "candidate_sha256": hashlib.sha256(raw).hexdigest(),
            "candidate_source": raw.decode("utf-8"), "diff": diff,
            "activation_approved": False}, headers={
                "Content-Disposition": 'attachment; filename="proofflow-candidate.json"'})

    @app.get("/v1/repairs/{repair_id}/bundle")
    async def repair_bundle(repair_id: str, request: Request):
        workspace, token, _ = await authorize(request)
        identity = identifier(repair_id)
        if journals is None:
            raise HttpFailure(503, "REPAIR_ARTIFACT_UNAVAILABLE")
        try:
            await asyncio.wait_for(bundle_slot.acquire(), 0.01)
        except TimeoutError:
            raise HttpFailure(429, "EXPORT_CAPACITY") from None
        try:
            row = await store.call("repair_bundle", workspace, token, identity)
            if row is None or row[0] is None:
                raise HttpFailure(404, "JOB_NOT_FOUND")
            raw = await asyncio.to_thread(build_bundle, row[0], workspace, assets, journals)
            if await store.call("repair_bundle", workspace, token, identity) != row:
                raise ProductFailure("REPAIR_AUTHORITY_CHANGED")
            return Response(raw, media_type="application/zip", headers={
                "Content-Disposition": 'attachment; filename="proofflow-evidence.zip"',
                "X-ProofFlow-SHA256": hashlib.sha256(raw).hexdigest()})
        finally:
            bundle_slot.release()

    @app.get("/v1/jobs/{job_id}/events")
    async def events(job_id: str, request: Request):
        workspace, token, _ = await authorize(request)
        job = identifier(job_id)
        cursors = [v for k, v in request.scope["headers"] if k.lower() == b"last-event-id"]
        if len(cursors) > 1:
            raise HttpFailure(400, "INVALID_EVENT_CURSOR")
        after = 0
        if cursors:
            try:
                value = cursors[0].decode("ascii")
            except UnicodeError:
                raise HttpFailure(400, "INVALID_EVENT_CURSOR") from None
            prefix, separator, number = value.partition(":")
            if (prefix != job_id or separator != ":"
                    or re.fullmatch(r"0|[1-9][0-9]{0,18}", number) is None
                    or int(number) > 9223372036854775807):
                raise HttpFailure(400, "INVALID_EVENT_CURSOR")
            after = int(number)
        # Fail auth/cursor checks before emitting HTTP200. Discard this read so
        # generator reauthorizes immediately before its first disclosure too.
        initial = (await store.call("events", workspace, token, job, after))[0]
        if not initial:
            current = (await store.call("job", workspace, token, job))[0]
            if current["state"] in ("NEEDS_REVIEW", "FAILED_INFRA", "CANCELLED"):
                return Response(status_code=204)

        async def replay():
            cursor = after
            started = heartbeat_at = time.monotonic()
            try:
                while time.monotonic() - started < 60:
                    rows = (await store.call("events", workspace, token, job, cursor))[0]
                    for event in rows:
                        await store.call("session", token)  # Recheck after each possibly slow send.
                        await asyncio.to_thread(assets.assert_live, workspace)
                        event = JobEvent.model_validate(event).model_dump()
                        sequence = int(event["sequence"])
                        if sequence != cursor + 1:
                            raise ProductFailure("PRODUCT_EVENT_SEQUENCE_INVALID")
                        yield ("id: " + job_id + ":" + str(sequence) + "\nevent: job_state\ndata: "
                               ).encode() + canonical_bytes(event) + b"\n\n"
                        cursor = sequence
                        if event["state"] in ("NEEDS_REVIEW", "FAILED_INFRA", "CANCELLED"):
                            return
                    if time.monotonic() - heartbeat_at >= 15:
                        yield b": heartbeat\n\n"
                        heartbeat_at = time.monotonic()
                    if await request.is_disconnected():
                        return
                    await asyncio.sleep(1)
            except (ProductFailure, ValidationError):
                # No event ID: reconnect can only resume from the last real event.
                yield (b'event: stream_closed\ndata: '
                       b'{"code":"STREAM_AUTHORITY_OR_STORE_UNAVAILABLE"}\n\n')
        return StreamingResponse(replay(), media_type="text/event-stream", headers={
            "X-Accel-Buffering": "no"})

    @app.get("/jobs/{job_id}")
    async def original_evidence(job_id: str, request: Request):
        workspace, token, _ = await authorize(request)
        stored = await store.call("job", workspace, token, identifier(job_id))
        if stored is None or stored[0] is None:
            raise HttpFailure(404, "JOB_NOT_FOUND")
        value = stored[0]
        report = (value.get("report") or {}).get("semantic", {}).get("report", {}).get("result", {})
        meanings = {"match": "The original output matched this input. Activation is not approved.",
                    "mismatch": "The original output violates the approved contract.",
                    "held": "Source data has unresolved problems. This batch is held.",
                    "input_rejected": "The source data could not be prepared under this contract.",
                    "infrastructure_failed": "The run failed. No verified result was published.",
                    "cancelled": "This job was cancelled."}
        rows = "".join("<tr>" + "".join("<td>" + escape(str(witness[key])) + "</td>" for key in
            ("merchant_id", "customer_id", "expected_owner", "actual_owner")) + "</tr>"
            for witness in report.get("ownership_witnesses", []))
        findings = "".join("<li>" + escape(finding["check"] + ": " + finding["code"])
                           + "</li>" for finding in report.get("findings", []))
        document = ("<!doctype html><html lang=en><meta charset=utf-8>"
            "<meta name=viewport content='width=device-width,initial-scale=1'>"
            "<title>ProofFlow — Original run evidence</title><main><h1>Original run evidence</h1>"
            "<p>Private development view · recorded results</p><p>Job <code>" + escape(job_id)
            + "</code></p><h2>" + escape(value["state"].replace("_", " ").title()) + "</h2><p>"
            + meanings.get(value.get("outcome"), "Waiting for execution and verification evidence.")
            + "</p><p>Blocking source occurrences: "
            + escape(str(report.get("blocking_occurrences", "—")))
            + "</p><h2>Ownership comparison</h2>"
            + ("<table><caption>Source-derived owner versus actual output</caption><thead><tr>"
               "<th scope=col>Merchant</th><th scope=col>Customer</th>"
               "<th scope=col>Expected owner</th><th scope=col>Actual owner</th>"
               "</tr></thead><tbody>" + rows + "</tbody></table>" if rows
               else "<p>No ownership mismatch witness recorded.</p>")
            + "<h2>Checks</h2><ul>" + findings + "</ul><p><a href='/v1/jobs/" + escape(job_id)
            + "'>Recorded JSON evidence</a></p><p>Refresh to read the latest committed state.</p>"
            "</main></html>")
        return Response(document, media_type="text/html")

    @app.post("/v1/logout")
    async def logout(request: Request):
        workspace, token, csrf = await authorize(request, True)
        await store.call("logout", workspace, token, csrf)
        response = Response(status_code=204)
        for name, suffix in (("__Host-proofflow", "; HttpOnly"), ("__Host-proofflow-csrf", "")):
            response.headers.append("Set-Cookie", name + "=; Path=/; Max-Age=0; Secure; "
                                    "SameSite=Strict" + suffix)
        return response

    @app.post("/v1/workspace/delete", response_model=DeleteResponse)
    async def delete_workspace(request: Request):
        workspace, token, csrf = await authorize(request, True)
        raw = parse_object(await body(request, 1024))
        try:
            value = DeleteRequest.model_validate(raw)
        except ValidationError:
            raise HttpFailure(400, "INVALID_DELETE_CONFIRMATION") from None
        if value.workspace_id != str(workspace) or raw.get("confirm") is not True:
            raise HttpFailure(409, "EXACT_WORKSPACE_REQUIRED")
        await store.call("delete", workspace, token, csrf)
        return {"access_revoked": True, "deletion": "queued"}

    from api.app.batch_events import install_batch_event_routes
    from api.app.github_routes import install_github_routes
    from api.app.version_routes import install_version_routes
    install_version_routes(app, store, assets, authorize)
    install_github_routes(app, store, authorize)
    install_batch_event_routes(app, store, authorize)
    return app
