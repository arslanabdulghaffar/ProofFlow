"""Actual private Chromium/HTTP/worker/retention probe; never executes candidate code locally.

Development-only Playwright 1.64.1; install its Chromium headless shell. TLS is
verified with the project CA first; Chromium trusts only the exact leaf SPKI.
No global TLS bypass, secret URLs, persisted browser profile or credential logs.
"""

import base64
import hashlib
import json
import ssl
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import expect, sync_playwright  # noqa: E402
from vultr_credit_guard import run as credit_guard  # noqa: E402
from vultr_phase1 import PRIVATE, Admin  # noqa: E402

from api.app.auth import SessionSecrets, csrf_digest, session_digest  # noqa: E402

ORIGIN = "https://127.0.0.1:18443"


def main():
    admin, tunnel, policy = Admin(), None, None
    guest = uuid4()
    intent_path = PRIVATE / "evidence/browser-intent.json"
    previous = json.loads(intent_path.read_bytes()) if intent_path.exists() else None
    resume = str(UUID(sys.argv[2])) if len(sys.argv) == 3 and sys.argv[1] == "--resume" else None
    if previous and previous.get("submitted") and resume is None:
        raise RuntimeError("RECONCILE_PREVIOUS_BROWSER_SUBMISSION_BEFORE_RERUN")
    if previous:
        guest = UUID(previous["guest"])
    report = {"observed_at": datetime.now(UTC).isoformat(), "checks": [], "fixture_only": True,
              "provider_calls": 0, "new_cloud_resources": 0, "guest": str(guest)}
    try:
        guard = credit_guard(admin, datetime.now(UTC))
        if guard.get("credit_guard") != "within_early_cutoff":
            raise RuntimeError("CREDIT_GUARD_NOT_ADMITTING")
        report["credit_guard"] = guard

        def host(command, raw=None, timeout=60):
            result = admin.host("control", command, stdin=raw, timeout=timeout)
            if result.returncode:
                (PRIVATE / "evidence/browser-host-failure.txt").write_bytes(result.stderr)
                raise RuntimeError("BROWSER_HOST_OPERATION_FAILED")
            return result.stdout.strip()

        def sql(statement):
            return host("docker exec -i --user=70:70 proofflow-budget psql -X -qAt "
                "-h /run/proofflow-budget -U postgres -d proofflow_product --set ON_ERROR_STOP=1",
                statement.encode())

        if host("cat /etc/machine-id").decode() != admin.state["control_machine_id"]:
            raise RuntimeError("DESIGNATED_CONTROL_CHANGED")
        existing = str(UUID(json.loads((PRIVATE / "evidence/product-http-latest.json")
                                      .read_bytes())["jobs"][0]["id"]))
        old = json.loads(sql("SELECT row_to_json(j) FROM pf_product.jobs j WHERE id='"  # noqa: S608
                             + existing + "';"))
        workspace = str(UUID(old["workspace_id"]))
        policy = json.loads(sql("SELECT row_to_json(p) FROM pf_product.execution_policy p;"))
        if policy["enabled"] or sql("SELECT count(*) FROM pf_product.jobs WHERE state NOT IN "
                "('NEEDS_REVIEW','FAILED_INFRA','CANCELLED');") != b"0":
            raise RuntimeError("BROWSER_CHECK_REQUIRES_CLOSED_IDLE_QUEUE")
        secret, other = SessionSecrets.create(), SessionSecrets.create()
        if sql("SELECT count(*) FROM pf_product.workspaces WHERE id='"  # noqa: S608
               + str(guest) + "';") == b"0":
            sql("SET ROLE pf_product_provisioner; SELECT pf_product.create_workspace('"
                + str(guest) + "','guest',clock_timestamp()+interval '1 hour');")
        for wid, value in ((workspace, secret), (str(guest), other)):
            sql("SET ROLE pf_product_provisioner; "
                f"SELECT pf_product.create_session('{wid}','{session_digest(value.token)}',"
                f"'{csrf_digest(value.csrf)}',clock_timestamp()+interval '30 minutes');")
        intent = {
            "guest": str(guest), "workspace": workspace, "existing_job": existing,
            "fixture_only": True}
        if previous and previous.get("submitted"):
            intent.update(previous)
        intent_path.write_bytes(json.dumps(intent).encode())
        args = ["C:/Windows/System32/OpenSSH/ssh.exe", "-F", "NUL", "-N", "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=yes", "-o", "HostKeyAlgorithms=ssh-ed25519",
            "-o", "IdentitiesOnly=yes", "-o", "ExitOnForwardFailure=yes", "-o", "ConnectTimeout=10",
            "-o", "UserKnownHostsFile=" + str(PRIVATE / "known_hosts"), "-p", "443",
            "-i", str(PRIVATE / "operator_ed25519"), "-L",
            "127.0.0.1:18443:/run/proofflow-product-api/api.sock",
            "root@" + admin.state["hosts"]["control"]["address"]]
        tunnel = subprocess.Popen(  # noqa: S603 - pinned host/key and local port
            args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW)  # noqa: S603 - pinned host/key and local port
        for attempt in range(40):
            try:
                cert = ssl.get_server_certificate(("127.0.0.1", 18443),
                    ca_certs=str(PRIVATE / "tls/ca.pem"), timeout=2)
                break
            except OSError:
                if tunnel.poll() is not None or attempt == 39:
                    raise RuntimeError("PRIVATE_BROWSER_TUNNEL_UNAVAILABLE") from None
                time.sleep(0.25)
        public = subprocess.run(["C:/Windows/System32/wsl.exe", "-d", "Ubuntu-24.04",
            "--", "/usr/bin/openssl", "x509",
            "-pubkey", "-noout"], input=cert.encode(), capture_output=True,
            check=True, timeout=15).stdout  # noqa: S603 - public certificate only
        der = subprocess.run(["C:/Windows/System32/wsl.exe", "-d", "Ubuntu-24.04",
            "--", "/usr/bin/openssl", "pkey", "-pubin",
            "-outform", "DER"], input=public, capture_output=True, check=True,
            timeout=15).stdout  # noqa: S603 - public key only
        spki = base64.b64encode(hashlib.sha256(der).digest()).decode()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(args=["--ignore-certificate-errors-spki-list="
                                                       + spki])
            context = browser.new_context(viewport={"width": 1366, "height": 1000})
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda _: errors.append("BROWSER_SCRIPT_ERROR"))
            page.goto(ORIGIN, wait_until="networkidle")

            def login(value):
                page.locator("#session-token").fill(value.token)
                page.locator("#csrf-token").fill(value.csrf)
                page.locator("#login button").click()
                expect(page.locator("#workspace")).to_be_visible()
                if page.locator("#session-token").input_value():
                    raise RuntimeError("LOGIN_SECRET_NOT_CLEARED")

            login(secret)
            def fetch(path, data=None):
                return page.evaluate("""async ({path,data})=>{
                  const options=data===null?{}:{method:'POST',body:data,
                    headers:{'X-Proofflow-CSRF':document.cookie.split('; ').find(
                      v=>v.startsWith('__Host-proofflow-csrf=')).split('=')[1]}};
                  const response=await fetch(path,options);
                  return {status:response.status,body:Array.from(new Uint8Array(
                    await response.arrayBuffer()))};} """, {"path": path, "data": data})
            cookies = {c["name"]: c for c in context.cookies()}
            if not cookies["__Host-proofflow"]["httpOnly"] or not all(
                c["secure"] and c["sameSite"] == "Strict" for c in cookies.values()):
                raise RuntimeError("BROWSER_COOKIE_FLAGS_CHANGED")
            report["checks"].append("actual_tls_bridge_secure_cookies_and_secret_form_cleared")
            if resume is None:
                for kind in ("pipeline", "transactions", "customers", "contract"):
                    response = fetch("/v1/assets/" + old[kind + "_id"] + "/download")
                    if response["status"] != 200:
                        raise RuntimeError("EXISTING_SYNTHETIC_ASSET_UNAVAILABLE")
                    extension = {"pipeline": "py", "contract": "json"}.get(kind, "csv")
                    page.locator("#" + kind).set_input_files({"name": kind + "." + extension,
                        "mimeType": "text/plain", "buffer": bytes(response["body"])})
                page.locator("#files button").click()
                expect(page.locator("#confirm-contract")).to_be_enabled()
                expect(page.locator("#run")).to_be_disabled()
                page.locator("#confirm-contract").check()
                page.locator("#approve").click()
                expect(page.locator("#run")).to_be_enabled()
                sql("SET ROLE pf_product_provisioner; SELECT pf_product.configure_execution('"
                    + policy["runtime_sha256"] + "','" + policy["verifier_sha256"] + "',true);")
                before = int(sql("SELECT count(*) FROM pf_product.jobs;"))
                intent.update(submitted=True, baseline_jobs=before)
                intent_path.write_bytes(json.dumps(intent).encode())
                page.locator("#run").click()
            else:
                current = json.loads(sql("SELECT row_to_json(j) FROM pf_product.jobs j WHERE id='"  # noqa: S608
                                         + resume + "';"))
                before = previous["baseline_jobs"]
                if current["workspace_id"] != workspace or current["outcome"] != "mismatch":
                    raise RuntimeError("BROWSER_RESUME_JOB_MISMATCH")
                for kind in ("pipeline", "transactions", "customers", "contract"):
                    matched = sql("SELECT count(DISTINCT sha256)=1 FROM pf_product.assets WHERE "  # noqa: S608
                        "id IN ('" + str(UUID(current[kind+"_id"])) + "','"
                        + str(UUID(old[kind+"_id"])) + "');")
                    if matched != b"t":
                        raise RuntimeError("BROWSER_RESUME_SOURCE_MISMATCH")
                page.goto(ORIGIN + "/?job=" + resume, wait_until="networkidle")
                report["resumed_existing_execution"] = True
            expect(page.locator("#state")).to_have_text("Needs review", timeout=90000)
            expect(page.locator("#outcome")).to_contain_text("violates")
            expect(page.locator("#witnesses")).to_contain_text("owner-A")
            expect(page.locator("#witnesses")).to_contain_text("owner-B")
            job = str(UUID(page.url.split("?job=", 1)[1]))
            report["job"] = job
            report["checks"].append("browser_upload_exact_approval_actual_worker_wrong_owner_rejected")
            if resume is None:
                page.locator("#job details summary").click()
                expect(page.locator("#events li").first).to_be_visible()
            else:
                states = page.evaluate("""path=>new Promise((resolve,reject)=>{
                  const seen=[];const stream=new EventSource(path);
                  const timeout=setTimeout(()=>{stream.close();reject('event timeout');},10000);
                  stream.addEventListener('job_state',e=>{const value=JSON.parse(e.data);
                    seen.push(value.state);if(value.state==='NEEDS_REVIEW'){
                      clearTimeout(timeout);stream.close();resolve(seen);}});
                })""", "/v1/jobs/"+job+"/events")
                if states[0] != "QUEUED" or states[-1] != "NEEDS_REVIEW":
                    raise RuntimeError("BROWSER_EVENT_REPLAY_FAILED")
            page.reload(wait_until="networkidle")
            expect(page.locator("#state")).to_have_text("Needs review")
            page.locator("#refresh").click()
            if int(sql("SELECT count(*) FROM pf_product.jobs;")) != before + 1:
                raise RuntimeError("BROWSER_REFRESH_RESUBMITTED")
            report["checks"].append("committed_sse_and_refresh_without_resubmit")
            page.screenshot(path=str(PRIVATE / "evidence/browser-desktop.png"), full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            if page.evaluate("document.documentElement.scrollWidth > innerWidth"):
                raise RuntimeError("BROWSER_MOBILE_OVERFLOW")
            page.screenshot(path=str(PRIVATE / "evidence/browser-mobile.png"), full_page=True)
            page.locator("#logout").click()
            expect(page.locator("#access")).to_be_visible()
            login(other)
            if fetch("/v1/jobs/" + job + "/summary")["status"] != 404:
                raise RuntimeError("CROSS_WORKSPACE_DISCLOSURE")
            response = fetch("/v1/assets/pipeline/" + str(uuid4()),
                             "# synthetic retention fixture; never executed")
            if response["status"] != 201:
                raise RuntimeError("RETENTION_FIXTURE_UPLOAD_FAILED")
            page.locator("details.panel summary").click()
            page.locator("#confirm-delete").check()
            page.locator("#delete").click()
            expect(page.locator("#access")).to_be_visible()
            if fetch("/v1/session")["status"] != 403:
                raise RuntimeError("DELETED_SESSION_STILL_USABLE")
            host("systemctl start proofflow-product-retention.service", timeout=245)
            deleted = sql("SELECT completed_at IS NOT NULL FROM pf_product.deletions "  # noqa: S608
                          "WHERE workspace_id='" + str(guest) + "';")
            if deleted != b"t":
                raise RuntimeError("RETENTION_NOT_COMPLETED")
            host("test ! -e /var/lib/proofflow-product/assets/" + guest.hex
                 + " && test -f /var/lib/proofflow-product/assets/.deleted-" + guest.hex)
            report["checks"].append("browser_logout_cross_workspace_revocation_and_actual_byte_deletion")
            if errors:
                raise RuntimeError("BROWSER_SCRIPT_ERROR")
            browser.close()
        (PRIVATE / "evidence/product-browser-latest.json").write_bytes(json.dumps(report).encode())
        print(json.dumps({"passed": len(report["checks"]), "checks": report["checks"],
                          "new_cloud_resources": 0, "provider_calls": 0}))
    finally:
        try:
            if policy is not None:
                sql("SET ROLE pf_product_provisioner; SELECT pf_product.configure_execution('"
                    + policy["runtime_sha256"] + "','" + policy["verifier_sha256"] + "',false);")
        finally:
            if tunnel is not None:
                tunnel.terminate()
                tunnel.wait(timeout=5)
            admin.close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        (PRIVATE / "evidence/browser-failure.txt").write_text(
            traceback.format_exc(), encoding="utf-8")
        raise SystemExit("BROWSER_CHECK_FAILED: inspect private diagnostic; reconcile before rerun"
                         ) from None
