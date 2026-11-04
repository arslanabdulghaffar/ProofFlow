"""Fixed private dispatcher startup. No configurable model/provider/tool dispatcher."""

import asyncio
import json
import os
from pathlib import Path

from api.app.product_store import ProductConnection, ProductStore
from api.app.workspace_assets import WorkspaceAssets
from orchestrator.product_dispatcher import ProductDispatcher
from orchestrator.product_setup import database_password
from orchestrator.worker_client import WorkerClient
from worker.wire import tls_context


async def main():
    os.umask(0o077)
    private = Path("/etc/proofflow-product/worker")
    raw = (private / "worker.json").read_bytes()
    if len(raw) > 16384:
        raise RuntimeError("PRODUCT_CONFIGURATION_LIMIT")
    config = json.loads(raw)
    context = tls_context(private / "ca.pem", private / "controller.pem",
                          private / "controller.key", server=False)
    worker = WorkerClient(config["worker_address"], context, config["worker_certificate_sha256"],
                          config["runtime_sha256"])
    root = os.open("/var/lib/proofflow-product/assets",
                   os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        store = ProductStore(ProductConnection(database_password(), "dispatcher"))
        dispatcher = ProductDispatcher(store,
            WorkspaceAssets(root), worker, verifier_sha256=config["verifier_sha256"],
            journal=Path("/var/lib/proofflow-product/jobs"))
        while True:
            await dispatcher.once()
            await asyncio.sleep(1)
    finally:
        os.close(root)


if __name__ == "__main__":
    asyncio.run(main())
