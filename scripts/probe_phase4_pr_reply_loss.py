"""Trusted one-shot fault driver: normal outbox writes, discard final PR response once."""

import asyncio
import json
import sys
from uuid import UUID

from api.app.product_store import ProductConnection, ProductFailure, ProductStore
from integrations.github_setup import load_github_app
from orchestrator.github_dispatcher import GitHubDispatcher
from orchestrator.product_setup import database_password


async def run(store, app, intent, digest):
    original_call, original_request = store.call, app.request
    dropped = False

    async def scoped_call(operation, *args):
        result = await original_call(operation, *args)
        if operation == "pr_claim" and result and result[0]:
            job = result[0]
            if job["id"] != intent or job["preview_sha256"] != digest:
                raise RuntimeError("FAULT_PROBE_INTENT_CHANGED")
        return result

    async def lose_reply(method, path, *args, **kwargs):
        nonlocal dropped
        value = await original_request(method, path, *args, **kwargs)
        if method == "POST" and path == app.config.prefix + "/pulls":
            dropped = True
            # The real HTTP reply is deliberately discarded before any readback/DB confirmation.
            raise ProductFailure("PRODUCT_OPERATION_UNCERTAIN")
        return value

    # ProductStore is frozen. Wrap its interface; never monkey-patch the real
    # store or App. Mutable test doubles previously hid this startup failure.
    class ScopedStore:
        call = staticmethod(scoped_call)

    class ReplyLossApp:
        request = staticmethod(lose_reply)

        def __getattr__(self, name):
            return getattr(app, name)

    dispatcher = GitHubDispatcher(ScopedStore(), ReplyLossApp())
    async with asyncio.timeout(80):
        for _ in range(60):
            await dispatcher.once()
            if dropped:
                return {"intent": intent, "final_pr_reply_discarded": True}
            await asyncio.sleep(1)
    raise RuntimeError("FAULT_PROBE_REPLY_NOT_DISCARDED")


if __name__ == "__main__":
    try:
        intent = str(UUID(sys.argv[1]))
        digest = sys.argv[2]
        store = ProductStore(ProductConnection(database_password(), "dispatcher"))
        print(json.dumps(asyncio.run(run(store, load_github_app(), intent, digest))))
    except Exception:
        raise SystemExit("PR_REPLY_LOSS_PROBE_FAILED_RECONCILE_OUTBOX") from None
