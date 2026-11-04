"""Networkless private TLS-over-Unix-socket API; operator reaches it through pinned SSH."""

import os
import ssl

import uvicorn

from api.app.product import create_product_app
from api.app.product_store import ProductConnection, ProductStore
from api.app.workspace_assets import WorkspaceAssets
from orchestrator.product_setup import database_password


def main():
    os.umask(0o077)
    root = os.open("/var/lib/proofflow-product/assets",
                   os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        app = create_product_app(ProductStore(ProductConnection(database_password())),
                                 WorkspaceAssets(root), origin="https://127.0.0.1:18443")

        def tls(_, factory):
            context = factory()
            context.minimum_version = ssl.TLSVersion.TLSv1_3
            return context

        config = uvicorn.Config(app, uds="/run/proofflow-product-api/api.sock", workers=1,
            access_log=False, server_header=False, proxy_headers=False, ws="none", backlog=8,
            limit_concurrency=8, timeout_keep_alive=2, timeout_graceful_shutdown=15,
            h11_max_incomplete_event_size=16384,
            ssl_keyfile="/etc/proofflow-product/tls/health.key",
            ssl_certfile="/etc/proofflow-product/tls/health.pem", ssl_context_factory=tls)
        uvicorn.Server(config).run()
    finally:
        os.close(root)


if __name__ == "__main__":
    main()
