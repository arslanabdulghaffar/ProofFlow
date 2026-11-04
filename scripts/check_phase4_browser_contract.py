"""Chromium UI against explicitly mocked HTTP. No cloud, GitHub, provider or worker calls."""

import json
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1] / "api/app/static"


def require(value):
    if not value:
        raise RuntimeError("BROWSER_CONTRACT_CHECK_FAILED")


class Static(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]
        name = "index.html" if path == "/" else path.removeprefix("/static/")
        if name not in (
            "index.html",
            "intake.js",
            "versions.js",
            "github.js",
            "recovery.js",
            "intake.css",
        ):
            self.send_error(404)
            return
        raw = (ROOT / name).read_bytes()
        kind = (
            "text/html"
            if name.endswith(".html")
            else "text/css"
            if name.endswith(".css")
            else "application/javascript"
        )
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *args):
        pass


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Static)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = "http://127.0.0.1:" + str(server.server_port)
    version, pipeline, workspace, batch, pr = (str(uuid4()) for _ in range(5))
    expiry = (datetime.now(UTC) + timedelta(minutes=30)).isoformat()
    state = {"active": False, "batch_posts": [], "pr_posts": [], "pr_state": "PREVIEW"}
    checks = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            context = browser.new_context(viewport={"width": 1366, "height": 1000})
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))

            def route(call):
                request = call.request
                path = request.url.removeprefix(base)
                data = (
                    request.post_data_json
                    if request.method == "POST"
                    and request.headers.get("content-type") == "application/json"
                    else None
                )
                if path == "/v1/session":
                    value = {"workspace_id": workspace, "kind": "operator", "expires_at": expiry}
                elif path == "/v1/versions/" + version:
                    value = {
                        "id": version,
                        "pipeline_id": pipeline,
                        "code_sha256": "a" * 64,
                        "contract_sha256": "b" * 64,
                        "runtime_sha256": "c" * 64,
                        "verifier_sha256": "d" * 64,
                        "evidence_sha256": "e" * 64,
                        "active_version": version if state["active"] else None,
                        "eligible": True,
                        "revoked_at": None,
                        "pipeline_revision": "1",
                    }
                elif path.endswith("/preview"):
                    value = {
                        "intent_id": data["intent_id"],
                        "bundle_sha256": "a" * 64,
                        "expires_at": expiry,
                        "bundle": {"version_id": version},
                    }
                elif path == "/v1/versions/" + version + "/approve":
                    state["active"] = True
                    value = {"approved": True}
                elif path.startswith("/v1/assets/"):
                    value = {"stored": True}
                elif path == "/v1/pipelines/" + pipeline + "/batches":
                    state["batch_posts"].append(data)
                    if len(state["batch_posts"]) == 1:
                        call.abort("failed")
                        return
                    value = {"batch_id": batch, "status_url": "/v1/batches/" + batch}
                elif path == "/v1/batches/" + batch:
                    value = {
                        "state": "COMPLETED",
                        "outcome": "match",
                        "version_id": version,
                        "version_currently_eligible": True,
                    }
                elif path == "/v1/versions/" + version + "/pr-preview":
                    state["pr_posts"].append(("preview", data))
                    state["intent"] = data["intent_id"]
                    value = {
                        "intent_id": data["intent_id"],
                        "status_url": "/v1/pr-intents/" + data["intent_id"],
                    }
                elif path == "/v1/pr-intents/" + state.get("intent", pr) + "/approve":
                    state["pr_posts"].append(("approve", data))
                    state["pr_state"] = "APPROVED"
                    call.abort("failed")
                    return
                elif path == "/v1/pr-intents/" + state.get("intent", pr):
                    value = {
                        "intent_id": state["intent"],
                        "version_id": version,
                        "state": state["pr_state"],
                        "currently_authorized": True,
                        "expires_at": expiry,
                        "preview_sha256": "f" * 64,
                        "preview": {
                            "candidate_source": "</pre><img src=x onerror=alert(1)>",
                            "draft": True,
                        },
                        "result": None,
                    }
                else:
                    raise RuntimeError("UNEXPECTED_MOCK_ROUTE " + path)
                call.fulfill(status=200, content_type="application/json", body=json.dumps(value))

            page.route("**/v1/**", route)
            page.goto(base + "/?version=" + version)
            expect(page.locator("#version-preview")).to_be_enabled()
            page.locator("#version-preview").click()
            expect(page.locator("#approval-details")).to_contain_text("bundle_sha256")
            expect(page.locator("#version-approve")).to_be_disabled()
            page.locator("#version-confirm").check()
            page.locator("#version-approve").click()
            expect(page.locator("#batch-start")).to_be_enabled()
            checks.append("explicit_exact_activation_confirmation")
            for kind in ("transactions", "customers"):
                page.locator("#batch-" + kind).set_input_files(
                    {"name": kind + ".csv", "mimeType": "text/csv", "buffer": b"inert\nfixture\n"}
                )
            page.evaluate(
                "() => { const f=document.getElementById('batch-form'); "
                "f.dispatchEvent(new Event('submit',{cancelable:true})); "
                "f.dispatchEvent(new Event('submit',{cancelable:true})); }"
            )
            expect(page.locator("#batch-retry")).to_be_visible()
            require(len(state["batch_posts"]) == 1)
            saved = dict(state["batch_posts"][0])
            page.reload()
            expect(page.locator("#batch-retry")).to_be_visible()
            require(len(state["batch_posts"]) == 1)
            page.locator("#batch-retry").click()
            expect(page.locator("#batch-result")).to_contain_text("COMPLETED")
            require(state["batch_posts"] == [saved, saved])
            checks.append("double_submit_denied_lost_reply_reload_explicit_same_batch_retry")
            page.locator("#pr-preview").click()
            expect(page.locator("#pr-details")).to_contain_text("candidate_source")
            require(page.locator("#pr-details img").count() == 0)
            expect(page.locator("#pr-approve")).to_be_disabled()
            page.locator("#pr-confirm").check()
            page.locator("#pr-approve").click()
            expect(page.locator("#notice")).to_contain_text("Refresh the existing intent")
            require(len(state["pr_posts"]) == 2)
            page.reload()
            expect(page.locator("#pr-details")).to_contain_text("APPROVED")
            expect(page.locator("#pr-approve")).to_be_disabled()
            require(len(state["pr_posts"]) == 2)
            checks.append("escaped_pr_preview_separate_confirmation_no_reapprove_after_lost_reply")
            page.set_viewport_size({"width": 390, "height": 844})
            require(page.evaluate("document.documentElement.scrollWidth<=innerWidth"))
            require(not errors)
            checks.append("mobile_width_and_no_browser_errors")
            context.close()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
    print(
        json.dumps(
            {"status": "passed", "checks": checks, "mode": "HTTP_doubles_only", "external_calls": 0}
        )
    )


if __name__ == "__main__":
    main()
