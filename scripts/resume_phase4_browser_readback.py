"""Complete the preserved live browser probe after a collapsed-details harness timeout."""

import base64
import hashlib
import json
import traceback
from datetime import UTC, datetime
from uuid import UUID

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from playwright.sync_api import expect, sync_playwright
from product_live_session import ORIGIN, PRIVATE, LiveSession, require


def main():
    path = PRIVATE / "evidence/phase4-browser-result.json"
    require(not path.exists(), "FINAL_BROWSER_RECEIPT_ALREADY_EXISTS")
    intent = json.loads((PRIVATE / "evidence/phase4-browser-intent.json").read_bytes())
    workspace, version, connection = (
        str(UUID(intent[k])) for k in ("workspace", "version", "connection")
    )
    batches = [str(UUID(intent[k])) for k in ("batch", "signed_batch")]
    result = {
        "checks": [],
        "provider_calls": 0,
        "new_cloud_resources": 0,
        "new_worker_executions_this_resume": 0,
        "worker_executions_across_preserved_probe": 2,
        "harness_findings": [
            "Separate Playwright request client CA failure; temporary credential revoked.",
            "Revoke checkbox is inside collapsed details; resume expands it before checking.",
        ],
    }
    with LiveSession() as live:
        client = live.login(workspace)
        statuses = [client.get("/v1/batches/" + identity).json() for identity in batches]
        require(
            all(s["state"] == "COMPLETED" and s["version_id"] == version for s in statuses),
            "PRESERVED_BATCHES_NOT_COMPLETED",
        )
        require(live.sql("SELECT count(*) FROM pf_product.jobs;") == b"12", "BATCH_COUNT_CHANGED")
        delivery = json.loads(
            live.sql(
                "SELECT json_build_object('revoked',c.revoked_at IS NOT NULL,"  # noqa: S608 - canonical UUID
                "'batch',d.batch_id,'event',d.event_id,'body_sha256',d.body_sha256) "
                "FROM pf_product.batch_connections c JOIN pf_product.batch_deliveries d "
                "ON d.connection_id=c.id "
                f"WHERE c.id='{connection}';"
            )
        )
        require(
            delivery["revoked"] and delivery["batch"] == batches[1],
            "SIGNED_DELIVERY_BINDING_CHANGED",
        )
        result["batches"] = statuses
        result["delivery"] = delivery
        result["checks"].append(
            "readback_two_actual_completed_batches_single_signed_receipt_connection_revoked"
        )
        cert = x509.load_pem_x509_certificate(live.cert.encode())
        spki = base64.b64encode(
            hashlib.sha256(
                cert.public_key().public_bytes(
                    serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
                )
            ).digest()
        ).decode()
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--ignore-certificate-errors-spki-list=" + spki])
            context = browser.new_context(viewport={"width": 1366, "height": 1000})
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(type(error).__name__))
            page.goto(ORIGIN + "/")
            page.locator("#session-token").fill(live.secret.token)
            page.locator("#csrf-token").fill(live.secret.csrf)
            page.locator("#login button").click()
            expect(page.locator("#workspace")).to_be_visible()
            page.goto(ORIGIN + "/?version=" + version + "&batch=" + batches[0])
            expect(page.locator("#batch-result")).to_contain_text("COMPLETED")
            status = client.get("/v1/versions/" + version).json()
            if status["revoked_at"] is None:
                page.get_by_text("Revoke this version", exact=True).click()
                page.locator("#version-revoke-confirm").check()
                page.locator("#version-revoke").click()
            expect(page.locator("#batch-start")).to_be_disabled()
            expect(page.locator("#version-details")).not_to_contain_text('"revoked_at": null')
            page.locator("#batch-refresh").click()
            expect(page.locator("#batch-result")).to_contain_text(
                "Historical results remain recorded"
            )
            page.screenshot(
                path=str(PRIVATE / "evidence/phase4-browser-final-desktop.png"), full_page=True
            )
            page.set_viewport_size({"width": 390, "height": 844})
            require(
                page.evaluate("document.documentElement.scrollWidth<=innerWidth"), "MOBILE_OVERFLOW"
            )
            page.screenshot(
                path=str(PRIVATE / "evidence/phase4-browser-final-mobile.png"), full_page=True
            )
            require(not errors, "BROWSER_ERROR")
            result["checks"].append(
                "actual_browser_revocation_history_desktop_mobile_and_no_javascript_error"
            )
            page.locator("#logout").click()
            expect(page.locator("#access")).to_be_visible()
            context.close()
            browser.close()
        require(
            live.sql("SELECT bool_and(blocked) FROM pf_budget.accounts;", "proofflow_budget")
            == b"t",
            "INFERENCE_NOT_BLOCKED",
        )
        result["services"] = (
            live.host(
                "systemctl is-active proofflow-product-api.service "
                "proofflow-product-dispatcher.service proofflow-product-retention.timer"
            )
            .decode()
            .splitlines()
        )
        require(result["services"] == ["active"] * 3, "SERVICES_UNHEALTHY")
        result.update(observed_at=datetime.now(UTC).isoformat(), credit=live.credit)
        path.write_bytes(json.dumps(result).encode())
    print(
        json.dumps(
            {
                "status": "passed",
                "checks": result["checks"],
                "new_worker_executions": 0,
                "provider_calls": 0,
            }
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        frames = [
            {"file": frame.filename.rsplit("\\", 1)[-1], "line": frame.lineno}
            for frame in traceback.extract_tb(error.__traceback__)
        ]
        (PRIVATE / "evidence/phase4-browser-readback-failure.json").write_bytes(
            json.dumps({"exception_type": type(error).__name__, "frames": frames}).encode()
        )
        raise SystemExit("PHASE4_READBACK_FAILED_SEE_PRIVATE_SANITIZED_RECEIPT") from None
