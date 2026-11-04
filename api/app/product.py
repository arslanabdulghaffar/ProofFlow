"""Private authenticated Phase2 HTTP surface. No inference or candidate execution here."""

import asyncio
import hashlib
from html import escape
from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from api.app.auth import AuthError, request_digests
from api.app.product_store import ProductFailure
from contracts.codec import InputError, parse_object
from contracts.policy import parse_contract

LIMITS = {"pipeline": 16384, "contract": 32768, "transactions": 5242880, "customers": 5242880}


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

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def protected_send(message):
            if message["type"] == "http.response.start":
                message = {**message, "headers": [*message.get("headers", []),
                    (b"cache-control", b"no-store"), (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'; "
                     b"base-uri 'none'; form-action 'self'")]}
            await send(message)
        if self.slots.locked():
            return await JSONResponse({"error": {"code": "BUSY"}}, status_code=429)(
                scope, receive, protected_send)
        async with self.slots:
            return await self.app(scope, receive, protected_send)


def create_product_app(store, assets, *, origin: str):
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(CapacityBoundary)

    @app.exception_handler(TimeoutError)
    async def timeout_failure(_, __):
        return JSONResponse({"error": {"code": "REQUEST_TIMEOUT"}}, status_code=408)

    @app.exception_handler(HttpFailure)
    async def http_failure(_, error):
        return JSONResponse({"error": {"code": error.code}}, status_code=error.status)

    @app.exception_handler(AuthError)
    async def auth_failure(_, error):
        return JSONResponse({"error": {"code": str(error)}}, status_code=403)

    @app.exception_handler(InputError)
    async def input_failure(_, error):
        return JSONResponse({"error": {"code": str(error)}}, status_code=422)

    @app.exception_handler(ProductFailure)
    async def store_failure(_, error):
        code = str(error)
        status = (403 if code == "ACCESS_DENIED" else 429 if code in ("ASSET_QUOTA", "JOB_CAPACITY")
                  else 404 if code == "JOB_NOT_FOUND" else 409 if code.endswith("CONFLICT")
                  or code in ("CONTRACT_REVOKED", "EXACT_CONTRACT_REQUIRED") else 503)
        return JSONResponse({"error": {"code": code}}, status_code=status)

    async def authorize(request, writing=False):
        session, csrf = request_digests(request.scope["headers"], expected_origin=origin,
                                        writing=writing)
        row = await store.call("session", session)
        if row is None or len(row) != 3 or type(row[0]) is not UUID:
            raise ProductFailure("PRODUCT_RESULT_INVALID")
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

    @app.get("/v1/session")
    async def session(request: Request):
        workspace, _, _ = await authorize(request)
        return {"workspace_id": str(workspace)}

    @app.post("/v1/assets/{kind}/{asset_id}", status_code=201)
    async def upload(kind: str, asset_id: str, request: Request):
        workspace, token, csrf = await authorize(request, True)
        asset = identifier(asset_id)
        if kind not in LIMITS:
            raise HttpFailure(400, "INVALID_ASSET_KIND")
        raw = await body(request, LIMITS[kind])
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

    @app.post("/v1/contracts/{asset_id}/approve")
    async def approve(asset_id: str, request: Request):
        workspace, token, csrf, asset, kind, digest, raw = await get_asset(request, asset_id, True)
        value = await json_body(request, ("expected_sha256", "confirm"))
        if kind != "contract" or value["expected_sha256"] != digest or value["confirm"] is not True:
            raise HttpFailure(409, "EXACT_CONTRACT_REQUIRED")
        policy = parse_contract(raw)
        await store.call("approve", workspace, token, csrf, asset, digest)
        return {"asset_id": str(asset), "raw_sha256": digest, "canonical_sha256": policy.sha256,
                "approved": True}

    @app.post("/v1/contracts/{asset_id}/revoke")
    async def revoke(asset_id: str, request: Request):
        workspace, token, csrf = await authorize(request, True)
        await store.call("revoke_contract", workspace, token, csrf, identifier(asset_id))
        return {"revoked": True}

    @app.post("/v1/jobs", status_code=202)
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

    @app.post("/v1/jobs/{job_id}/cancel")
    async def cancel(job_id: str, request: Request):
        workspace, token, csrf = await authorize(request, True)
        await store.call("cancel", workspace, token, csrf, identifier(job_id))
        return {"cancellation_requested": True}

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
        return Response(status_code=204, headers={"Set-Cookie": "__Host-proofflow=; Path=/; "
                        "Max-Age=0; Secure; HttpOnly; SameSite=Strict"})

    return app
