"""Fixed private dispatcher startup. No configurable model/provider/tool dispatcher."""

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from uuid import UUID

from api.app.product_store import ProductConnection, ProductStore
from api.app.workspace_assets import WorkspaceAssets
from integrations.github_setup import load_github_app
from orchestrator.budget_store import BudgetConnection
from orchestrator.github_dispatcher import GitHubDispatcher
from orchestrator.probe_plan import RateQuote
from orchestrator.product_dispatcher import ProductDispatcher
from orchestrator.product_setup import database_password
from orchestrator.provider_setup import load_provider_secrets
from orchestrator.repair_dispatcher import RepairDispatcher
from orchestrator.repair_provider import RepairBudget, RepairProvider
from orchestrator.worker_client import WorkerClient
from worker.wire import tls_context


async def main():
    os.umask(0o077)
    private = Path("/etc/proofflow-product/worker")
    raw = (private / "worker.json").read_bytes()
    if len(raw) > 16384:
        raise RuntimeError("PRODUCT_CONFIGURATION_LIMIT")
    config = json.loads(raw)
    context = tls_context(
        private / "ca.pem", private / "controller.pem", private / "controller.key", server=False
    )
    worker = WorkerClient(
        config["worker_address"],
        context,
        config["worker_certificate_sha256"],
        config["runtime_sha256"],
    )
    root = os.open(
        "/var/lib/proofflow-product/assets", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    )
    try:
        store = ProductStore(ProductConnection(database_password(), "dispatcher"))
        dispatcher = ProductDispatcher(
            store,
            WorkspaceAssets(root),
            worker,
            verifier_sha256=config["verifier_sha256"],
            journal=Path("/var/lib/proofflow-product/jobs"),
        )
        repair_config = json.loads(Path("/etc/proofflow-repair/config.json").read_bytes())
        quote = dict(repair_config["quote"])
        for field in ("observed_at", "valid_until"):
            quote[field] = datetime.fromisoformat(quote[field])
        secrets = load_provider_secrets("/etc/proofflow-repair/credentials")
        provider = RepairProvider(
            store=store,
            budget=RepairBudget(
                BudgetConnection(secrets.database_password), UUID(repair_config["account_id"])
            ),
            quote=RateQuote(**quote),
            api_key=secrets.vultr_api_key,
        )
        repair = RepairDispatcher(
            store,
            WorkspaceAssets(root),
            worker,
            provider,
            verifier_sha256=config["verifier_sha256"],
            journal=Path("/var/lib/proofflow-product/jobs"),
        )
        github_app = load_github_app()
        github = GitHubDispatcher(store, github_app) if github_app is not None else None
        while True:
            # Root publishes a validated, same-model/rate quote atomically.
            # Refresh between jobs, never while a bounded repair is in progress.
            current = json.loads(Path("/etc/proofflow-repair/config.json").read_bytes())
            fresh = dict(current["quote"])
            if current["account_id"] != repair_config["account_id"] or any(
                fresh[key] != repair_config["quote"][key] for key in
                ("model", "input_micro_usd_per_million", "output_micro_usd_per_million")
            ):
                raise RuntimeError("PROVIDER_QUOTE_IDENTITY_CHANGED")
            for key in ("observed_at", "valid_until"):
                fresh[key] = datetime.fromisoformat(fresh[key])
            provider.quote = RateQuote(**fresh)
            if not await dispatcher.once():
                await repair.once()
            if github is not None:
                await github.once()
            await asyncio.sleep(1)
    finally:
        os.close(root)


if __name__ == "__main__":
    asyncio.run(main())
