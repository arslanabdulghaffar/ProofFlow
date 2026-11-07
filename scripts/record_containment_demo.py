"""Separate explicit containment recording; no new AI repair or external GitHub action."""

import base64
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from check_phase6_browser import CAPTION, containment_rehearsal, variants
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from playwright.sync_api import expect, sync_playwright
from product_live_session import ORIGIN, PRIVATE, LiveSession, require

from worker.protocol import authority_id


def main():
    path = PRIVATE / "evidence/phase6-containment-recording.json"
    require(not path.exists(), "RECONCILE_CONTAINMENT_RECORDING_RECEIPT")
    record = {"completed":False,"provider_calls":0,"observed_at":datetime.now(UTC).isoformat(),
              "workspace":str(authority_id()),"checks":[]}
    video = None

    def save():
        path.write_text(json.dumps(record,indent=2,sort_keys=True),encoding="utf-8")

    files = next(value[3] for value in variants(uuid4().hex) if value[2] == "match")
    save()
    with LiveSession() as live:
        require(live.sql("SELECT bool_and(blocked) FROM pf_budget.accounts;","proofflow_budget")
                == b"t", "CONTAINMENT_INFERENCE_MUST_STAY_CLOSED")
        try:
            live.sql("SET ROLE pf_product_provisioner; SELECT pf_product.create_workspace('"
                +record["workspace"]+"','operator',clock_timestamp()+interval '1 hour');")
            client = live.login(record["workspace"],minutes=20)
            cert = x509.load_pem_x509_certificate(live.cert.encode())
            spki = base64.b64encode(hashlib.sha256(cert.public_key().public_bytes(
                serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)
            ).digest()).decode()
            live.admission(True)
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    args=["--ignore-certificate-errors-spki-list="+spki])
                login = browser.new_context()
                page = login.new_page()
                page.goto(ORIGIN)
                page.locator("#session-token").fill(live.secret.token)
                page.locator("#csrf-token").fill(live.secret.csrf)
                page.locator("#login button").click()
                expect(page.locator("#workspace")).to_be_visible()
                cookies = login.cookies()
                login.close()
                context = browser.new_context(viewport={"width":1366,"height":900},
                    record_video_dir=str(PRIVATE/"evidence"),
                    record_video_size={"width":1366,"height":900})
                context.add_cookies(cookies)
                context.add_init_script(CAPTION.replace("REAL VULTR REQUEST",
                    "SEGMENT 2: DELIBERATE LOOP, NO AI CALL"))
                page = context.new_page()
                video = page.video
                try:
                    containment_rehearsal(page,client,files,record,save,live=live)
                    page.locator("#job").scroll_into_view_if_needed()
                    page.evaluate("""()=>{const d=document.createElement('p');
                      d.textContent='Worker evidence: killed (signal 9); no output accepted; '+
                      'cleanup confirmed; kernel writers absent. '+
                      'This loop was deliberate, not AI output.';
                      document.getElementById('job').prepend(d);} """)
                    page.wait_for_timeout(5000)  # Readable evidence, not a processing delay.
                    record["completed"] = True
                finally:
                    context.close()  # Flush video even when a real assertion fails.
                    browser.close()
                    filename = video.path()
                    record["video_file"] = Path(filename).name
                    record["video_sha256"] = hashlib.sha256(Path(filename).read_bytes()).hexdigest()
                    save()
        finally:
            live.admission(False)
            client = live.login(record["workspace"],minutes=10)
            require(client.post("/v1/workspace/delete",json={"workspace_id":record["workspace"],
                "confirm":True}).status_code == 200,"CONTAINMENT_RETIREMENT_FAILED")
            live.host("systemctl start proofflow-product-retention.service")
            record["cleanup_confirmed"] = live.sql(
                "SELECT count(*) FROM pf_product.workspaces;") == b"0"
            record["credit"] = live.credit
            save()
    print(json.dumps({"completed":record["completed"],"cleanup":record["cleanup_confirmed"],
                      "video_file":record["video_file"],"provider_calls":0}))


if __name__ == "__main__":
    main()
