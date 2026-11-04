"""Actual private Chromium + signed ingress + worker. Synthetic approval, zero inference."""

import base64
import csv
import hashlib
import hmac
import io
import json
import re
import ssl
import sys
import time
import traceback
import zipfile
from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from playwright.sync_api import expect, sync_playwright
from product_live_session import ORIGIN, PRIVATE, LiveSession, require

from api.app.auth import session_digest


def main():
    intent_path = PRIVATE / "evidence/phase4-browser-intent.json"
    resume = sys.argv[1:] == ["--resume"]
    require(resume == intent_path.exists(), "RECONCILE_EXISTING_PHASE4_BROWSER_INTENT")
    source = json.loads((PRIVATE / "evidence/phase3-live-v3-intent.json").read_bytes())
    version = str(UUID(source["repair_id"]))
    workspace = str(UUID(source["workspace"]))
    intent = {
        "workspace": workspace,
        "version": version,
        "synthetic_automated_approval_not_human_signoff": True,
    }
    if resume:
        intent = json.loads(intent_path.read_bytes())
        require(
            intent.get("test_session_revoked") is True
            and "batch_request" in intent
            and "signed_batch" not in intent,
            "RESUME_REQUIRES_RECONCILED_BROWSER_BATCH",
        )
    result = {"checks": [], "provider_calls": 0, "new_cloud_resources": 0}

    def save():
        intent_path.write_bytes(json.dumps(intent).encode())

    save()
    with zipfile.ZipFile(PRIVATE / "evidence/phase3-candidate-bundle.zip") as archive:
        customers = archive.read("input/customers.csv")
        reader = csv.DictReader(io.StringIO(archive.read("input/transactions.csv").decode()))
        rows = list(reader)
        for n, row in enumerate(rows):
            row["transaction_id"] = "phase4-browser-" + str(n)
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=reader.fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        transactions = output.getvalue().encode()
    with LiveSession() as live:
        client = live.login(workspace)
        reservations = live.sql("SELECT count(*) FROM pf_budget.reservations;", "proofflow_budget")
        require(
            live.sql("SELECT bool_and(blocked) FROM pf_budget.accounts;", "proofflow_budget")
            == b"t",
            "PAID_ADMISSION_NOT_CLOSED",
        )
        require(
            live.sql("SELECT count(*) FROM pf_product.jobs;") == (b"11" if resume else b"10"),
            "REVIEW_CHANGED_JOB_CAPACITY",
        )
        cert = x509.load_pem_x509_certificate(live.cert.encode())
        spki = base64.b64encode(
            hashlib.sha256(
                cert.public_key().public_bytes(
                    serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
                )
            ).digest()
        ).decode()
        live.admission(True)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                args=["--ignore-certificate-errors-spki-list=" + spki]
            )
            context = browser.new_context(viewport={"width": 1366, "height": 1000})
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(ORIGIN + "/")
            page.locator("#session-token").fill(live.secret.token)
            page.locator("#csrf-token").fill(live.secret.csrf)
            page.locator("#login button").click()
            expect(page.locator("#workspace")).to_be_visible()
            if not resume:
                page.goto(ORIGIN + "/?repair=" + version)
                expect(page.locator("#version-prepare")).to_be_enabled()
                page.locator("#version-prepare").click()
                expect(page.locator("#version-preview")).to_be_enabled()
                page.locator("#version-preview").click()
                expect(page.locator("#approval-details")).to_contain_text("bundle_sha256")
                expect(page.locator("#version-approve")).to_be_disabled()
                preview = json.loads(page.locator("#approval-details").inner_text())
                intent["approval_intent"] = preview["intent_id"]
                save()
                require(
                    preview["bundle"]["candidate_sha256"]
                    == client.get("/v1/repairs/" + version + "/export").json()["candidate_sha256"],
                    "SOURCE_PREVIEW_HASH_CHANGED",
                )
                page.locator("#version-confirm").check()
                page.locator("#version-approve").click()
                expect(page.locator("#batch-start")).to_be_enabled()
                result["checks"].append("deployed_browser_exact_candidate_preview_and_activation")
                for kind, raw in (("transactions", transactions), ("customers", customers)):
                    page.locator("#batch-" + kind).set_input_files(
                        {"name": kind + ".csv", "mimeType": "text/csv", "buffer": raw}
                    )
            else:
                page.goto(ORIGIN + "/?version=" + version)
                expect(page.locator("#batch-start")).to_be_enabled()
                current = client.get("/v1/session").json()
                pending = {
                    "workspace": workspace,
                    "expires": current["expires_at"],
                    "pipeline": intent["pipeline"],
                    "request": intent["batch_request"],
                }
                page.evaluate(
                    "(value)=>sessionStorage.setItem('proofflow.pending-batch',JSON.stringify(value))",
                    pending,
                )
                page.reload()
                expect(page.locator("#batch-retry")).to_be_visible()
                result["checks"].append(
                    "resumed_actual_activation_and_completed_batch_without_new_execution"
                )
            observed = []
            faults = []

            def lost_reply(route):
                try:
                    observed.append(route.request.post_data_json)
                    intent["batch_request"] = observed[-1]
                    save()
                    # CA-verified client sends this exact request, then the harness drops the reply.
                    path = route.request.url.removeprefix(ORIGIN)
                    require(path.startswith("/v1/pipelines/"), "FAULT_ROUTE_CHANGED")
                    response = client.post(path, json=observed[-1])
                    require(response.status_code == 202, "ACTUAL_BATCH_NOT_ACCEPTED")
                    intent["batch"] = response.json()["batch_id"]
                    save()
                except Exception:
                    faults.append("FAULT_INJECTION_FAILED")
                finally:
                    route.abort("failed")

            page.route("**/v1/pipelines/*/batches", lost_reply, times=1)
            page.locator("#batch-retry" if resume else "#batch-start").click()
            expect(page.locator("#notice")).to_contain_text(
                re.compile("REQUEST_FAILED|Failed to fetch")
            )
            require(not faults, "FAULT_INJECTION_FAILED")
            expect(page.locator("#batch-retry")).to_be_visible()
            page.reload()
            expect(page.locator("#batch-retry")).to_be_visible()
            require(len(observed) == 1, "RELOAD_RESUBMITTED_BATCH")
            page.locator("#batch-retry").click()
            expect(page.locator("#batch-evidence")).to_be_visible()
            require(
                page.locator("#batch-evidence").get_attribute("href")
                == "/v1/batches/" + intent["batch"],
                "RECOVERY_CHANGED_BATCH",
            )
            for _ in range(120):
                status = client.get("/v1/batches/" + intent["batch"]).json()
                if status["state"] in ("COMPLETED", "FAILED_INFRA", "HELD_FOR_REVIEW", "CANCELLED"):
                    break
                time.sleep(0.5)
            require(status["state"] == "COMPLETED", "BROWSER_BATCH_NOT_COMPLETED")
            page.locator("#batch-refresh").click()
            expect(page.locator("#batch-result")).to_contain_text("COMPLETED")
            result["browser_batch"] = status
            result["checks"].append("actual_worker_batch_lost_reply_reload_same_assignment")
            # App absent must stay an honest setup error, with no fabricated PR.
            page.locator("#pr-preview").click()
            expect(page.locator("#notice")).to_contain_text("GITHUB_NOT_CONFIGURED")
            page.screenshot(
                path=str(PRIVATE / "evidence/phase4-browser-desktop.png"), full_page=True
            )
            page.set_viewport_size({"width": 390, "height": 844})
            require(
                page.evaluate("document.documentElement.scrollWidth<=innerWidth"), "MOBILE_OVERFLOW"
            )
            page.screenshot(
                path=str(PRIVATE / "evidence/phase4-browser-mobile.png"), full_page=True
            )
            require(not errors, "BROWSER_JAVASCRIPT_FAILED")
            result["checks"].append("deployed_desktop_mobile_honest_github_setup_gap")

            connection, event = str(uuid4()), str(uuid4())
            pipeline = client.get("/v1/versions/" + version).json()["pipeline_id"]
            intent.update(connection=connection, event=event, pipeline=pipeline)
            save()
            live.sql(
                "SET ROLE pf_product_provisioner; SELECT pf_product.provision_batch_connection("
                f"'{workspace}','{session_digest(live.secret.token)}','{pipeline}','{connection}',"
                "clock_timestamp()+interval '20 minutes');"
            )
            code = (
                "from uuid import UUID; "
                "from api.app.batch_events import connection_key,load_batch_master; "
                "print(connection_key(load_batch_master(),UUID('" + connection + "')).hex())"
            )
            key = bytes.fromhex(
                live.host(
                    "docker exec --user=10003:10003 proofflow-product-api python -c "
                    + "'"
                    + code.replace("'", "'\\''")
                    + "'"
                ).decode()
            )
            raw = json.dumps(
                {k: intent["batch_request"][k] for k in ("transactions_id", "customers_id")},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()

            def signed(payload, event_id=event):
                stamp = str(int(time.time()))
                signature = hmac.digest(
                    key, stamp.encode() + b"\n" + event_id.encode() + b"\n" + payload, "sha256"
                ).hex()
                return {
                    "X-ProofFlow-Event-ID": event_id,
                    "X-ProofFlow-Timestamp": stamp,
                    "X-ProofFlow-Signature": "sha256=" + signature,
                }

            signed_path = "/v1/connections/" + connection + "/batch-events"
            with httpx.Client(
                base_url=ORIGIN,
                verify=ssl.create_default_context(cafile=str(PRIVATE / "tls/ca.pem")),
                trust_env=False,
                timeout=20,
            ) as ingress:
                bad = ingress.post(signed_path, content=raw + b" ", headers=signed(raw))
                require(bad.status_code == 403, "ALTERED_SIGNATURE_ACCEPTED")
                # Durable ingress must survive a stopped controller without dispatching.
                live.host("systemctl stop proofflow-product-dispatcher.service")
                try:
                    response = ingress.post(signed_path, content=raw, headers=signed(raw))
                    require(response.status_code == 202, "SIGNED_INGRESS_FAILED")
                    intent["signed_batch"] = response.json()["batch_id"]
                    save()
                    replay = ingress.post(signed_path, content=raw, headers=signed(raw))
                    require(
                        replay.status_code == 202
                        and replay.json()["already_accepted"]
                        and replay.json()["batch_id"] == intent["signed_batch"],
                        "SIGNED_REPLAY_DUPLICATED",
                    )
                    changed = ingress.post(
                        signed_path, content=raw + b" ", headers=signed(raw + b" ")
                    )
                    require(changed.status_code == 409, "CHANGED_REPLAY_ACCEPTED")
                finally:
                    live.host("systemctl start proofflow-product-dispatcher.service")
                for _ in range(120):
                    status = client.get("/v1/batches/" + intent["signed_batch"]).json()
                    if status["state"] in (
                        "COMPLETED",
                        "FAILED_INFRA",
                        "HELD_FOR_REVIEW",
                        "CANCELLED",
                    ):
                        break
                    time.sleep(0.5)
                require(status["state"] == "COMPLETED", "SIGNED_BATCH_NOT_COMPLETED")
                result["signed_batch"] = status
                require(
                    client.post(
                        "/v1/connections/" + connection + "/revoke", json={"confirm": True}
                    ).status_code
                    == 200,
                    "CONNECTION_REVOCATION_FAILED",
                )
                require(
                    ingress.post(signed_path, content=raw, headers=signed(raw)).status_code == 409,
                    "REVOKED_CONNECTION_ACCEPTED",
                )
            result["checks"].append(
                "real_signed_delivery_replay_conflict_controller_restart_worker_completion_revocation"
            )
            (PRIVATE / "evidence/phase4-browser-progress.json").write_bytes(
                json.dumps(result).encode()
            )
            page.get_by_text("Revoke this version", exact=True).click()
            page.locator("#version-revoke-confirm").check()
            page.locator("#version-revoke").click()
            expect(page.locator("#batch-start")).to_be_disabled()
            expect(page.locator("#version-details")).not_to_contain_text('"revoked_at": null')
            page.locator("#batch-refresh").click()
            expect(page.locator("#batch-result")).to_contain_text(
                "Historical results remain recorded"
            )
            require(
                live.sql("SELECT count(*) FROM pf_budget.reservations;", "proofflow_budget")
                == reservations,
                "UNEXPECTED_PAID_RESERVATION",
            )
            require(
                live.sql("SELECT count(*) FROM pf_product.jobs;") == b"12", "UNEXPECTED_BATCH_COUNT"
            )
            result["checks"].append("browser_revocation_preserves_history_two_jobs_zero_inference")
            page.locator("#logout").click()
            expect(page.locator("#access")).to_be_visible()
            context.close()
            browser.close()
        result.update(observed_at=datetime.now(UTC).isoformat(), credit=live.credit)
        (PRIVATE / "evidence/phase4-browser-result.json").write_bytes(json.dumps(result).encode())
    print(
        json.dumps(
            {
                "status": "passed",
                "checks": result["checks"],
                "worker_jobs": 2,
                "provider_calls": 0,
                "github": "NOT_CONFIGURED_NO_EXTERNAL_WRITES",
            }
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Browser/native errors can include HTTP credentials. Never print their text or traceback.
        frames = [
            {"file": frame.filename.rsplit("\\", 1)[-1].rsplit("/", 1)[-1], "line": frame.lineno}
            for frame in traceback.extract_tb(error.__traceback__)
        ]
        (PRIVATE / "evidence/phase4-browser-failure.json").write_bytes(
            json.dumps({"exception_type": type(error).__name__, "frames": frames}).encode()
        )
        raise SystemExit("PHASE4_BROWSER_PROBE_FAILED_RECONCILE_PRIVATE_INTENT") from None
