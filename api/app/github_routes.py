"""Queue a read-only preview; a separate exact operator approval authorizes writes."""

from fastapi import Request
from pydantic import ValidationError

from api.app.wire import PrApprovalRequest, PrIntentResponse, VersionPreviewRequest
from contracts.codec import parse_object


def install_github_routes(app, store, authorize):
    from api.app.product import HttpFailure, body, identifier

    async def parsed(request, model):
        raw = parse_object(await body(request, 2048))
        if model is PrApprovalRequest and raw.get("confirm") is not True:
            raise HttpFailure(400, "INVALID_PR_REQUEST")
        try:
            return model.model_validate(raw)
        except ValidationError:
            raise HttpFailure(400, "INVALID_PR_REQUEST") from None

    @app.post(
        "/v1/versions/{version_id}/pr-preview", status_code=202, response_model=PrIntentResponse
    )
    async def preview(version_id: str, request: Request):
        workspace, token, csrf = await authorize(request, True)
        value = await parsed(request, VersionPreviewRequest)
        identity = (
            await store.call(
                "pr_request",
                workspace,
                token,
                csrf,
                identifier(version_id),
                identifier(value.intent_id),
            )
        )[0]
        return {"intent_id": str(identity), "status_url": "/v1/pr-intents/" + str(identity)}

    @app.get("/v1/pr-intents/{intent_id}")
    async def get_intent(intent_id: str, request: Request):
        workspace, token, _ = await authorize(request)
        row = await store.call("pr_get", workspace, token, identifier(intent_id))
        if row is None or row[0] is None:
            raise HttpFailure(404, "PR_NOT_FOUND")
        return row[0]

    @app.post("/v1/pr-intents/{intent_id}/approve")
    async def approve(intent_id: str, request: Request):
        workspace, token, csrf = await authorize(request, True)
        value = await parsed(request, PrApprovalRequest)
        applied = (
            await store.call(
                "pr_approve", workspace, token, csrf, identifier(intent_id), value.preview_sha256
            )
        )[0]
        return {
            "approved": True,
            "already_applied": not applied,
            "intent_id": str(identifier(intent_id)),
        }
