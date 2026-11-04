"""Exact approval and fresh-batch HTTP composition; no candidate execution."""

import asyncio
import hashlib
from uuid import uuid4

from fastapi import Request
from pydantic import ValidationError

from api.app.product_store import ProductFailure
from api.app.wire import (
    BatchRequest,
    BatchResponse,
    VersionApprovalRequest,
    VersionApprovalResponse,
    VersionPrepared,
    VersionPrepareRequest,
    VersionPreview,
    VersionPreviewRequest,
    VersionRevokeRequest,
)
from contracts.codec import parse_object


def install_version_routes(app, store, assets, authorize):
    from api.app.product import HttpFailure, body, identifier

    async def parsed(request, model):
        raw = parse_object(await body(request, 2048))
        for key in ("confirm", "prepare_verified_source"):
            if key in raw and raw[key] is not True:
                raise HttpFailure(400, "INVALID_VERSION_REQUEST")
        try:
            return model.model_validate(raw)
        except ValidationError:
            raise HttpFailure(400, "INVALID_VERSION_REQUEST") from None

    @app.post("/v1/repairs/{repair_id}/version", response_model=VersionPrepared)
    async def prepare(repair_id: str, request: Request):
        workspace, token, csrf = await authorize(request, True)
        await parsed(request, VersionPrepareRequest)
        version = identifier(repair_id)
        row = await store.call("repair_export", workspace, token, version)
        if row is None or row[0] is None:
            raise HttpFailure(409, "VERSION_NOT_ELIGIBLE")
        raw = row[0]["candidate_source"].encode("utf-8")
        if not 0 < len(raw) <= 16384:
            raise ProductFailure("VERSION_ASSET_MISMATCH")
        digest = hashlib.sha256(raw).hexdigest()
        # Same deterministic asset ID on uncertain retries. No source upload or
        # filename supplied by the caller can substitute the verified candidate.
        await store.call("reserve", workspace, token, csrf, version, "pipeline", digest, len(raw))
        if await asyncio.to_thread(assets.put, workspace, raw) != digest:
            raise ProductFailure("VERSION_ASSET_MISMATCH")
        await store.call("publish", workspace, token, csrf, version, "pipeline", digest, len(raw))
        return (await store.call("version_prepare", workspace, token, csrf, version, version))[0]

    @app.get("/v1/versions/{version_id}")
    async def get_version(version_id: str, request: Request):
        workspace, token, _ = await authorize(request)
        row = await store.call("version_get", workspace, token, identifier(version_id))
        if row is None or row[0] is None:
            raise HttpFailure(404, "VERSION_NOT_FOUND")
        return row[0]

    @app.post("/v1/versions/{version_id}/preview", response_model=VersionPreview)
    async def preview(version_id: str, request: Request):
        workspace, token, csrf = await authorize(request, True)
        value = await parsed(request, VersionPreviewRequest)
        return (
            await store.call(
                "version_preview",
                workspace,
                token,
                csrf,
                identifier(version_id),
                identifier(value.intent_id),
            )
        )[0]

    @app.post("/v1/versions/{version_id}/approve", response_model=VersionApprovalResponse)
    async def approve(version_id: str, request: Request):
        workspace, token, csrf = await authorize(request, True)
        value = await parsed(request, VersionApprovalRequest)
        return (
            await store.call(
                "version_approve",
                workspace,
                token,
                csrf,
                identifier(version_id),
                identifier(value.intent_id),
                value.bundle_sha256,
            )
        )[0]

    @app.post("/v1/versions/{version_id}/revoke")
    async def revoke(version_id: str, request: Request):
        workspace, token, csrf = await authorize(request, True)
        value = await parsed(request, VersionRevokeRequest)
        revision = int(value.expected_revision)
        if revision > 9223372036854775807:
            raise HttpFailure(400, "INVALID_VERSION_REQUEST")
        changed = (
            await store.call(
                "version_revoke", workspace, token, csrf, identifier(version_id), revision
            )
        )[0]
        return {"revoked": True, "changed": changed}

    @app.post("/v1/pipelines/{pipeline_id}/batches", status_code=202, response_model=BatchResponse)
    async def enqueue_batch(pipeline_id: str, request: Request):
        workspace, token, csrf = await authorize(request, True)
        value = await parsed(request, BatchRequest)
        identity = (
            await store.call(
                "batch_enqueue",
                workspace,
                token,
                csrf,
                identifier(pipeline_id),
                identifier(value.version_id),
                uuid4(),
                identifier(value.idempotency_key),
                identifier(value.transactions_id),
                identifier(value.customers_id),
            )
        )[0]
        return {"batch_id": str(identity), "status_url": "/v1/batches/" + str(identity)}

    @app.get("/v1/batches/{batch_id}")
    async def get_batch(batch_id: str, request: Request):
        workspace, token, _ = await authorize(request)
        row = await store.call("batch_get", workspace, token, identifier(batch_id))
        if row is None or row[0] is None:
            raise HttpFailure(404, "BATCH_NOT_FOUND")
        return row[0]
