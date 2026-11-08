"""Fresh private Chromium rehearsal with an explicit, bounded real-inference demo mode.

Without --ai-demo, correct source is a disclosed fixture and inference stays closed. Uploads
execute only on the designated worker. No GitHub action or persistent browser profile.
Each run has its own durable receipt; reconcile failed receipts before another run.
"""

import argparse
import base64
import hashlib
import json
import re
import ssl
import time
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from playwright.sync_api import expect, sync_playwright
from product_live_session import ORIGIN, PRIVATE, LiveSession, require

from contracts.policy import parse_contract
from eval.development import cases
from verifier.canaries import generate
from worker.protocol import authority_id

CAPTION = """document.addEventListener('DOMContentLoaded',()=>{
 const d=document.createElement('div');
 d.textContent='PRIVATE SYNTHETIC DEMO · REAL VULTR REQUEST · AUTOMATED TEST APPROVAL';
 d.style='position:fixed;top:0;left:0;right:0;z-index:9999;background:#062f2b;'+
 'color:white;padding:8px;text-align:center;font:14px sans-serif';
 document.body.append(d);});"""


def containment_rehearsal(page, client, files, item, save, *, live):
    page.goto(ORIGIN, wait_until="networkidle")
    for kind, key in (("pipeline","pipeline.py.txt"),("transactions","transactions.csv"),
                      ("customers","customers.csv"),("contract","contract.json")):
        raw = b"# Deliberate containment demonstration, not AI output\nwhile True:\n    pass\n" \
              if kind == "pipeline" else files[key]
        page.locator("#"+kind).set_input_files({"name":key.removesuffix(".txt"),
                                              "mimeType":"text/plain","buffer":raw})
    page.locator("#files button").click()
    expect(page.locator("#confirm-contract")).to_be_enabled()
    page.locator("#confirm-contract").check()
    page.locator("#approve").click()
    expect(page.locator("#run")).to_be_enabled()
    page.locator("#run").click()
    page.wait_for_url("**/?job=*",timeout=20000)
    job = str(UUID(page.url.split("?job=",1)[1]))
    item["containment_job"] = job
    save()
    expect(page.locator("#state")).to_have_text(
        re.compile("Needs review|Execution failed"),timeout=120000)
    result = client.get("/v1/jobs/"+job).json()
    # The public job view intentionally has report=null on infrastructure failure.
    # Read the committed termination receipt through trusted admin access; never
    # invent a public verification report or change the job's terminal state.
    worker = json.loads(live.sql("SELECT worker_receipt FROM pf_product.jobs WHERE id='"  # noqa: S608 - parsed UUID
                                 +job+"';"))
    require(result["outcome"] in ("execution_failed", "infrastructure_failed")
            and worker["cleanup"] == "confirmed" and worker["error"] == "MISSING_OUTPUT_FILE"
            and worker["runtime_exit_code"] == "9" and not worker["collected"]
            and worker["verification"] == "NOT_PERFORMED"
            and worker["termination"]["kernel_writers"] == "absent_or_populated_zero",
            "RECORDED_CONTAINMENT_FAILED")
    item["containment_result"] = result
    item["containment_worker_receipt"] = worker
    item["checks"].append("deliberate_loop_failed_and_worker_cleanup_confirmed")
    save()


def version_rehearsal(page, client, files, run, item, save, *, real_ai=False):
    """Disclosed original or real AI repair, fresh checks, exact test approval, new batch."""
    page.locator("#repair-start").click()
    page.wait_for_url("**/*repair=*", timeout=20000)
    repair = str(UUID(page.url.split("repair=", 1)[1].split("&", 1)[0]))
    item["repair"] = repair
    save()
    for step in range(360):
        result = client.get("/v1/repairs/" + repair).json()
        if result["state"] not in ("QUEUED", "RUNNING", "RECONCILING"):
            break
        if step % 3 == 0:
            page.locator("#repair-refresh").click()
        time.sleep(1)
    item["repair_result"] = result
    save()
    require(result["state"] == "AWAITING_APPROVAL"
            and (1 <= result["calls"] <= 3 if real_ai else
                 result["mode"] == "original" and result["calls"] == 0)
            and len(result["checks"]) >= 3
            and all(check["cleanup_confirmed"] for check in result["checks"]),
            "RECORDED_REPAIR_CHECKS_FAILED")
    page.locator("#repair-refresh").click()
    if not real_ai:
        expect(page.locator("#repair-state")).to_contain_text("Original source, no AI")
    export = client.get("/v1/repairs/" + repair + "/export").json()
    same = export["candidate_source"].encode() == files["pipeline.py.txt"]
    require(same != real_ai and not export["activation_approved"], "DEMO_SOURCE_ORIGIN_MISMATCH")
    with page.expect_download() as download:
        page.locator("#repair-bundle").click()
    target = PRIVATE / "evidence" / ("phase6-" + run + "-bundle.zip")
    download.value.save_as(target)
    item["bundle_sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
    page.locator("#version-prepare").click()
    expect(page.locator("#version-preview")).to_be_enabled()
    page.locator("#version-preview").click()
    expect(page.locator("#approval-details")).to_contain_text("bundle_sha256")
    expect(page.locator("#version-approve")).to_be_disabled()
    preview = json.loads(page.locator("#approval-details").inner_text())
    require(preview["bundle"]["candidate_sha256"] == export["candidate_sha256"],
            "ACTIVATION_PREVIEW_SOURCE_CHANGED")
    item["approval_digest"] = preview["bundle_sha256"]
    item["synthetic_version_approval_not_human_signoff"] = True
    save()
    page.locator("#version-confirm").check()
    page.locator("#version-approve").click()
    expect(page.locator("#batch-start")).to_be_enabled()
    policy = parse_contract(files["contract.json"])
    new = generate(policy, hashlib.sha256((run+"fresh-batch").encode()).hexdigest(), "ownership")
    require(new[0] != files["transactions.csv"], "FRESH_BATCH_REUSED_INPUTS")
    for kind, raw in zip(("transactions", "customers"), new, strict=True):
        page.locator("#batch-"+kind).set_input_files(
            {"name": kind+".csv", "mimeType": "text/csv", "buffer": raw})
    page.locator("#batch-start").click()
    expect(page.locator("#batch-evidence")).to_be_visible()
    route = page.locator("#batch-evidence").get_attribute("href")
    batch = str(UUID(route.rsplit("/", 1)[1]))
    item["batch"] = batch
    save()
    for _ in range(90):
        result = client.get("/v1/batches/" + batch).json()
        if result["state"] not in ("QUEUED", "RUNNING", "VERIFYING", "RECONCILING"):
            break
        time.sleep(1)
    item["batch_result"] = result
    save()
    require(result["state"] == "COMPLETED", "FRESH_BATCH_FAILED")
    page.locator("#batch-refresh").click()
    expect(page.locator("#batch-result")).to_contain_text("COMPLETED")
    item["checks"].extend(["real_vultr_changed_source_and_fresh_checks" if real_ai else
                           "three_fresh_checks_of_disclosed_original_no_model",
                           "actual_browser_bundle_download", "exact_synthetic_version_approval",
                           "fresh_batch_completed_on_designated_worker"])


def variants(run):
    development = {case["id"]: case for case in cases()}
    for index, (name, expected) in enumerate((
        ("joins-repairable", "mismatch"), ("units-repairable", "mismatch"),
        ("completeness-repairable", "match"), ("joins-ambiguous", "held"),
    )):
        files = dict(development[name]["files"])
        policy = parse_contract(files["contract.json"])
        seed = hashlib.sha256((run + name).encode()).hexdigest()
        txs, customers = generate(policy, seed,
                                  "quarantine" if expected == "held" else "ownership")
        files.update({"transactions.csv": txs, "customers.csv": customers})
        if name == "joins-repairable":
            # Disclosed first-match composite-key bug: unlike the older development
            # fault, this emits a wrong owner instead of rejecting duplicate matches.
            source = files["pipeline.py.txt"].decode()
            before = "    joined = lookup[tx['customer_id']]\n"
            require(source.count(before) == 1, "REHEARSAL_TEMPLATE_CHANGED")
            files["pipeline.py.txt"] = source.replace(before, before +
                                                      "    joined = joined[:1]\n").encode()
        if expected in ("match", "held"):
            fixture = Path("tests/fixtures/phase2/canary_correct.py.txt")
            files["pipeline.py.txt"] = fixture.read_bytes()
        yield index, name, expected, files


def main():
    global ORIGIN
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version-only", action="store_true",
                        help="Rehearse correct original, exact approval and fresh batch only")
    parser.add_argument("--ai-demo", action="store_true",
                        help="One bounded Vultr repair, activation and batch recording")
    parser.add_argument("--public-guest", action="store_true",
                        help="Use deployed public TLS with fresh guest workspaces; no AI/PR")
    options = parser.parse_args()
    require(not (options.public_guest and (options.ai_demo or options.version_only)),
            "PUBLIC_GUEST_BASIC_REHEARSAL_ONLY")
    require(not (options.ai_demo and options.version_only), "DEMO_MODES_EXCLUSIVE")
    run = uuid4().hex
    path = PRIVATE / "evidence" / ("phase6-browser-" + run + ".json")
    # No automatic replay after an uncertain job or failed fixture cleanup.
    for old in path.parent.glob("phase6-browser-*.json"):
        previous = json.loads(old.read_bytes())
        require(previous.get("completed") or (previous.get("reconciled_no_retry")
                and previous.get("cleanup_confirmed")), "RECONCILE_PHASE6_BROWSER_RECEIPT")
    record = {"observed_at": datetime.now(UTC).isoformat(), "completed": False,
              "scope": "private_fresh_context_template_derived_synthetic_rehearsal",
              "provider_calls": 0, "new_resources": 0, "workspaces": [], "cases": [],
              "version_rehearsal": options.version_only,
              "real_ai_demo": options.ai_demo,
              "synthetic_automated_contract_approval_not_human_signoff": True}

    def save():
        path.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")

    with LiveSession() as live:
        record["credit"] = live.credit
        if options.public_guest:
            ORIGIN = "https://" + live.admin.state["hosts"]["control"]["address"] + ":8443"
            record["scope"] = "external_public_tls_fresh_guest_contexts"
            record["origin"] = ORIGIN
        require(live.sql("SELECT count(*) FROM pf_product.workspaces;") == b"0",
                "REHEARSAL_REQUIRES_EMPTY_WORKSPACE_SET")
        require(live.sql("SELECT bool_and(blocked) FROM pf_budget.accounts;", "proofflow_budget")
                == b"t", "INFERENCE_MUST_REMAIN_CLOSED")
        counts = "SELECT json_build_array((SELECT count(*) FROM pf_product.repair_calls)," \
                 "(SELECT count(*) FROM pf_product.pr_intents));"
        baseline = live.sql(counts)
        certificate = x509.load_pem_x509_certificate(live.cert.encode())
        spki = base64.b64encode(hashlib.sha256(certificate.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo,
        )).digest()).decode()
        save()
        try:
            if options.ai_demo:
                config = json.loads((PRIVATE / "repair-provider.json").read_bytes())
                require(json.loads(live.host("cat /etc/proofflow-repair/config.json")) == config,
                        "DEMO_PROVIDER_CONFIG_DRIFT")
                quote = config["quote"]
                require(quote["model"] == "qwen3.8-flash-next"
                        and quote["input_micro_usd_per_million"] == 100000
                        and quote["output_micro_usd_per_million"] == 200000
                        and datetime.fromisoformat(quote["valid_until"])
                        > datetime.now(UTC)+timedelta(minutes=10), "DEMO_QUOTE_NOT_CURRENT")
                record["quote"] = quote
                save()
                require(live.sql("UPDATE pf_budget.accounts SET blocked=false WHERE blocked "
                                 "AND project_limit=150000000 AND inference_limit=25000000 "
                                 "RETURNING blocked;", "proofflow_budget") == b"f",
                        "BOUNDED_INFERENCE_ADMISSION_FAILED")
            live.admission(True)
            with sync_playwright() as playwright, ExitStack() as browser_cleanup:
                browser = playwright.chromium.launch(
                    args=[] if options.public_guest else
                    ["--ignore-certificate-errors-spki-list=" + spki])
                browser_cleanup.callback(browser.close)
                for index, name, expected, files in variants(run):
                    if options.ai_demo and name != "joins-repairable":
                        continue
                    if options.version_only and expected != "match":
                        continue
                    started = time.monotonic()
                    workspace = str(authority_id())
                    record["workspaces"].append(workspace)
                    item = {"case": name, "expected": expected, "checks": [],
                            "file_sha256": {k: hashlib.sha256(v).hexdigest()
                                            for k, v in files.items()}}
                    record["cases"].append(item)
                    save()
                    live.sql("SET ROLE pf_product_provisioner; "
                             "SELECT pf_product.create_workspace('" + workspace
                             + "','" + ("guest" if options.public_guest else "operator")
                             + "',clock_timestamp()+interval '1 hour');")
                    client = live.login(workspace, minutes=20)
                    if options.public_guest:
                        headers = dict(client.headers)
                        headers["origin"] = ORIGIN
                        client = httpx.Client(base_url=ORIGIN, trust_env=False, timeout=20,
                                              headers=headers)
                        browser_cleanup.callback(client.close)
                    context = browser.new_context(viewport={"width": 1366, "height": 900})
                    browser_cleanup.callback(context.close)
                    page = context.new_page()
                    errors = []
                    page.on("pageerror", lambda _, errors=errors: errors.append("SCRIPT_ERROR"))
                    page.goto(ORIGIN, wait_until="networkidle")
                    expect(page.locator("#access")).to_be_visible()
                    require(page.evaluate("fetch('/v1/session').then(r=>r.status)") == 403,
                            "UNAUTHENTICATED_SESSION_ALLOWED")
                    page.locator("#session-token").fill(live.secret.token)
                    page.locator("#csrf-token").fill(live.secret.csrf)
                    page.locator("#login button").click()
                    expect(page.locator("#workspace")).to_be_visible()
                    require(not page.locator("#session-token").input_value()
                            and not page.locator("#csrf-token").input_value(),
                            "LOGIN_FIELDS_NOT_CLEARED")
                    if options.ai_demo:
                        cookies = context.cookies()  # In memory only, never storage_state on disk.
                        context.close()
                        context = browser.new_context(viewport={"width":1366,"height":900},
                            record_video_dir=str(PRIVATE / "evidence"),
                            record_video_size={"width":1366,"height":900})
                        # ExitStack closes contexts before the browser on any assertion,
                        # flushing the original recording without another paid run.
                        browser_cleanup.callback(context.close)
                        context.add_init_script(CAPTION)
                        context.add_cookies(cookies)
                        page = context.new_page()
                        page.on("pageerror",lambda _,errors=errors: errors.append("SCRIPT_ERROR"))
                        page.goto(ORIGIN,wait_until="networkidle")
                        expect(page.locator("#workspace")).to_be_visible()
                        item["video_started_at"] = datetime.now(UTC).isoformat()
                    for kind, key in (("pipeline", "pipeline.py.txt"),
                                      ("transactions", "transactions.csv"),
                                      ("customers", "customers.csv"),
                                      ("contract", "contract.json")):
                        page.locator("#"+kind).set_input_files({
                            "name": key.removesuffix(".txt"), "mimeType": "text/plain",
                            "buffer": files[key]})
                    page.locator("#files button").click()
                    expect(page.locator("#confirm-contract")).to_be_enabled()
                    expect(page.locator("#run")).to_be_disabled()
                    expect(page.locator("#contract-hash")).to_contain_text(
                        hashlib.sha256(files["contract.json"]).hexdigest())
                    page.locator("#confirm-contract").check()
                    page.locator("#approve").click()
                    expect(page.locator("#run")).to_be_enabled()
                    page.locator("#run").click()
                    page.wait_for_url("**/?job=*", timeout=20000)
                    item["job"] = str(UUID(page.url.split("?job=", 1)[1]))
                    save()
                    expect(page.locator("#state")).to_have_text("Needs review", timeout=120000)
                    summary = client.get("/v1/jobs/" + item["job"] + "/summary").json()
                    item["outcome"] = summary["outcome"]
                    item["blocking_occurrences"] = summary["blocking_occurrences"]
                    item["ownership_witness_count"] = len(summary["ownership_witnesses"])
                    item["summary"] = summary
                    save()
                    require(summary["outcome"] == expected, "UNEXPECTED_REHEARSAL_OUTCOME")
                    if expected == "held":
                        expect(page.locator("#repair-start")).to_be_disabled()
                        require(summary["blocking_occurrences"] > 0, "AMBIGUITY_NOT_HELD")
                    if name == "joins-repairable":
                        require(item["ownership_witness_count"] > 0, "OWNERSHIP_WITNESS_MISSING")
                    count = live.sql("SELECT count(*) FROM pf_product.jobs;")
                    page.reload(wait_until="networkidle")
                    expect(page.locator("#state")).to_have_text("Needs review")
                    page.locator("#refresh").click()
                    require(live.sql("SELECT count(*) FROM pf_product.jobs;") == count,
                            "REFRESH_REPOSTED_JOB")
                    item["checks"].extend(["clean_unauthenticated_context_denied",
                                           "exact_contract_required_before_run",
                                           "actual_worker_original_and_independent_comparison",
                                           "refresh_preserves_job_identity"])
                    if options.version_only or options.ai_demo:
                        version_rehearsal(page, client, files, run, item, save,
                                          real_ai=options.ai_demo)
                    image = PRIVATE / "evidence" / ("phase6-" + run + "-" + str(index) + ".png")
                    page.locator("#job").screenshot(path=str(image))
                    item["screenshot_sha256"] = hashlib.sha256(image.read_bytes()).hexdigest()
                    page.set_viewport_size({"width": 390, "height": 844})
                    require(page.evaluate("document.documentElement.scrollWidth<=innerWidth"),
                            "MOBILE_PAGE_OVERFLOW")
                    require(not errors, "BROWSER_SCRIPT_ERROR")
                    if options.ai_demo:
                        page.set_viewport_size({"width":1366,"height":900})
                        containment_rehearsal(page,client,files,item,save,live=live)
                    page.locator("#logout").click()
                    expect(page.locator("#access")).to_be_visible()
                    # Close pooled transports before the independent revocation request;
                    # the public edge intentionally admits only eight connections.
                    context.close()
                    client.close()
                    # Test the revoked credential on a NEW transport. A server idle
                    # close racing an older pooled connection is not an auth result.
                    with httpx.Client(base_url=ORIGIN, trust_env=False, timeout=20,
                                      verify=ssl.create_default_context(
                                          cafile=None if options.public_guest else
                                          str(PRIVATE / "tls/ca.pem")),
                                      headers=client.headers) as negative:
                        revoked_status = negative.get("/v1/jobs/" + item["job"]).status_code
                        item["logout_readback_status"] = revoked_status
                        save()
                        require(revoked_status == 403,
                                "LOGGED_OUT_SESSION_STILL_READS_JOB")
                    context.close()
                    if options.ai_demo:
                        video = Path(page.video.path())
                        item["video_file"] = video.name
                        item["video_sha256"] = hashlib.sha256(video.read_bytes()).hexdigest()
                        item["video_finished_at"] = datetime.now(UTC).isoformat()
                    item["checks"].extend(["mobile_no_page_overflow", "logout_revokes_evidence"])
                    item["elapsed_seconds"] = round(time.monotonic()-started, 3)
                    save()
                    print(json.dumps({"case": name, "outcome": expected}), flush=True)
            after = live.sql(counts)
            if options.ai_demo:
                first, last = json.loads(baseline), json.loads(after)
                record["provider_calls"] = last[0]-first[0]
                require(1 <= record["provider_calls"] <= 3 and last[1] == first[1],
                        "DEMO_CALL_OR_PR_BOUNDARY_CHANGED")
            else:
                require(after == baseline, "MODEL_CALL_OR_PR_INTENT_CREATED")
        finally:
            if options.ai_demo:
                live.sql("UPDATE pf_budget.accounts SET blocked=true;", "proofflow_budget")
                record["provider_calls"] = json.loads(live.sql(counts))[0]-json.loads(baseline)[0]
                save()
            live.admission(False)
            for workspace in record["workspaces"]:
                if live.sql("SELECT count(*) FROM pf_product.workspaces WHERE id='"  # noqa: S608 - generated UUID
                            + str(UUID(workspace)) + "';") == b"0":
                    continue
                client = live.login(workspace, minutes=10)
                require(client.post("/v1/workspace/delete",
                        json={"workspace_id": workspace, "confirm": True}).status_code == 200,
                        "REHEARSAL_DELETION_FAILED")
            live.host("systemctl start proofflow-product-retention.service")
            record["cleanup_confirmed"] = live.sql(
                "SELECT count(*) FROM pf_product.workspaces;") == b"0"
            save()
            require(record["cleanup_confirmed"], "REHEARSAL_CLEANUP_UNCERTAIN")
        record.update(completed=True, finished_at=datetime.now(UTC).isoformat(),
                      product_admission="closed", inference_admission="closed")
        save()
    print(json.dumps({"completed": True, "receipt": path.name, "cases": len(record["cases"])}))


if __name__ == "__main__":
    main()
