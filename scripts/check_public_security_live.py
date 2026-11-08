"""Actual public guest boundaries and service restart recovery; inert bytes only."""

import json
import time
from datetime import UTC, datetime
from uuid import uuid4

import httpx
from product_live_session import PRIVATE, LiveSession, require

from api.app.auth import SessionSecrets, csrf_digest, session_digest
from worker.protocol import authority_id


def main():
    path = PRIVATE / "evidence" / ("phase6-public-security-" + uuid4().hex + ".json")
    result = {
        "started_at": datetime.now(UTC).isoformat(),
        "completed": False,
        "workspaces": [],
        "checks": [],
        "provider_calls": 0,
        "new_resources": 0,
    }

    def save():
        path.write_text(json.dumps(result, indent=2))

    with LiveSession() as live:
        require(
            live.sql("SELECT count(*) FROM pf_product.workspaces;") == b"0",
            "CLEAN_WORKSPACES_REQUIRED",
        )
        origin = "https://" + live.admin.state["hosts"]["control"]["address"] + ":8443"
        clients = []
        try:
            for kind in ("operator", "guest", "guest"):
                workspace = str(authority_id())
                result["workspaces"].append(workspace)
                save()
                live.sql(
                    "SET ROLE pf_product_provisioner; SELECT pf_product.create_workspace('"
                    + workspace
                    + "','"
                    + kind
                    + "',clock_timestamp()+interval '1 hour');"
                )
                private = live.login(workspace, minutes=10)
                headers = dict(private.headers)
                headers["origin"] = origin
                client = httpx.Client(
                    base_url=origin,
                    headers=headers,
                    trust_env=False,
                    timeout=15,
                    limits=httpx.Limits(max_keepalive_connections=0),
                )
                clients.append(client)
                response = client.post(
                    "/v1/session/import",
                    json={"session_token": live.secret.token, "csrf_token": live.secret.csrf},
                )
                require(
                    response.status_code == (403 if kind == "operator" else 200),
                    "PUBLIC_KIND_ADMISSION_FAILED",
                )
                require(
                    client.get("/v1/session").status_code == (403 if kind == "operator" else 200),
                    "PUBLIC_KIND_AUTHORIZATION_FAILED",
                )
            result["checks"].append("operator_import_and_cookie_denied_guests_admitted")
            _, first, second = clients
            asset = str(authority_id())
            require(
                first.post(
                    "/v1/assets/pipeline/" + asset,
                    content=b"# Inert boundary test; never executed\n",
                ).status_code
                == 201,
                "FIXTURE_UPLOAD_FAILED",
            )
            require(
                first.get("/v1/assets/" + asset + "/download").status_code == 200,
                "OWNER_DOWNLOAD_FAILED",
            )
            require(
                second.get("/v1/assets/" + asset + "/download").status_code == 404,
                "CROSS_WORKSPACE_DISCLOSURE",
            )
            require(
                first.post(
                    "/v1/assets/pipeline/" + str(authority_id()),
                    content=b"# inert",
                    headers={"Origin": "https://unrelated.invalid"},
                ).status_code
                == 403,
                "CSRF_ORIGIN_ACCEPTED",
            )
            response = first.post(
                "/v1/versions/" + str(authority_id()) + "/pr-preview",
                json={"intent_id": str(authority_id())}
            )
            require(response.status_code == 403, "GUEST_PR_REQUEST_ACCEPTED")
            result["checks"] += [
                "cross_workspace_download_denied",
                "wrong_origin_write_denied",
                "guest_pr_preview_denied",
            ]
            live.host("systemctl restart proofflow-public-api.service")
            time.sleep(2)
            require(
                first.get("/v1/assets/" + asset + "/download").status_code == 200,
                "RESTART_LOST_VALID_AUTHORITY",
            )
            require(first.post("/v1/logout").status_code == 204, "LOGOUT_FAILED")
            live.host("systemctl restart proofflow-public-api.service")
            time.sleep(2)
            require(
                first.get("/v1/assets/" + asset + "/download").status_code == 403,
                "RESTART_RESTORED_REVOKED_SESSION",
            )
            # Short-lived session uses normal provisioning, never direct session-state edits.
            secret = SessionSecrets.create()
            live.sql(
                "SET ROLE pf_product_provisioner; SELECT pf_product.create_session('"
                + result["workspaces"][2]
                + "','"
                + session_digest(secret.token)
                + "','"
                + csrf_digest(secret.csrf)
                + "',clock_timestamp()+interval '3 seconds');"
            )
            with httpx.Client(
                base_url=origin,
                trust_env=False,
                timeout=15,
                headers={"Cookie": "__Host-proofflow=" + secret.token},
            ) as expiry:
                require(expiry.get("/v1/session").status_code == 200, "FRESH_EXPIRY_SESSION_FAILED")
                time.sleep(4)
                require(expiry.get("/v1/session").status_code == 403, "EXPIRED_SESSION_ACCEPTED")
            result["checks"] += [
                "restart_preserves_valid_session_and_asset",
                "restart_does_not_resurrect_revoked_session",
                "expired_public_session_denied",
            ]
            result["completed"] = True
        finally:
            for client in clients:
                client.close()
            for workspace in result["workspaces"]:
                if live.sql("SELECT count(*) FROM pf_product.workspaces WHERE id='"  # noqa: S608 - generated authority UUID
                            + workspace + "';") == b"0":
                    continue
                client = live.login(workspace, minutes=10)
                require(
                    client.post(
                        "/v1/workspace/delete", json={"workspace_id": workspace, "confirm": True}
                    ).status_code
                    == 200,
                    "BOUNDARY_CLEANUP_FAILED",
                )
            live.host("systemctl start proofflow-product-retention.service")
            result["cleanup_confirmed"] = (
                live.sql("SELECT count(*) FROM pf_product.workspaces;") == b"0"
            )
            if not result["completed"]:
                live.host("systemctl stop proofflow-public.socket proofflow-public.service")
            save()
        require(result["cleanup_confirmed"], "BOUNDARY_CLEANUP_UNCERTAIN")
    print(
        json.dumps(
            {"completed": result["completed"], "checks": result["checks"], "receipt": path.name}
        )
    )


if __name__ == "__main__":
    main()
