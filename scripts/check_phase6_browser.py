"""Fresh private Chromium rehearsal, synthetic template-derived inputs, zero inference.

No hidden stored AI patch; the correct source is a disclosed test fixture. Uploads
execute only on the designated worker. No GitHub action or persistent browser profile.
Each run has its own durable receipt; reconcile failed receipts before another run.
"""

import argparse
import base64
import hashlib
import json
import ssl
import time
from datetime import UTC, datetime
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


def version_rehearsal(page, client, files, run, item, save):
    """Known-correct disclosed source, three real checks, exact test approval, new batch."""
    page.locator("#repair-start").click()
    page.wait_for_url("**/*repair=*", timeout=20000)
    repair = str(UUID(page.url.split("repair=", 1)[1].split("&", 1)[0]))
    item["repair"] = repair
    save()
    for _ in range(150):
        result = client.get("/v1/repairs/" + repair).json()
        if result["state"] not in ("QUEUED", "RUNNING", "RECONCILING"):
            break
        time.sleep(1)
    item["repair_result"] = result
    save()
    require(result["state"] == "AWAITING_APPROVAL" and result["mode"] == "original"
            and result["calls"] == 0 and len(result["checks"]) == 3
            and all(check["cleanup_confirmed"] for check in result["checks"]),
            "UNCHANGED_SOURCE_CHECKS_FAILED")
    page.locator("#repair-refresh").click()
    expect(page.locator("#repair-state")).to_contain_text("Original source, no AI")
    export = client.get("/v1/repairs/" + repair + "/export").json()
    require(export["candidate_source"].encode() == files["pipeline.py.txt"]
            and not export["activation_approved"], "UNCHANGED_EXPORT_MISMATCH")
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
    item["checks"].extend(["three_fresh_checks_of_disclosed_original_no_model",
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version-only", action="store_true",
                        help="Rehearse correct original, exact approval and fresh batch only")
    options = parser.parse_args()
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
              "synthetic_automated_contract_approval_not_human_signoff": True}

    def save():
        path.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")

    with LiveSession() as live:
        record["credit"] = live.credit
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
            live.admission(True)
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    args=["--ignore-certificate-errors-spki-list=" + spki])
                for index, name, expected, files in variants(run):
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
                             + "','operator',clock_timestamp()+interval '1 hour');")
                    client = live.login(workspace, minutes=20)
                    context = browser.new_context(viewport={"width": 1366, "height": 900})
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
                    if options.version_only:
                        version_rehearsal(page, client, files, run, item, save)
                    image = PRIVATE / "evidence" / ("phase6-" + run + "-" + str(index) + ".png")
                    page.locator("#job").screenshot(path=str(image))
                    item["screenshot_sha256"] = hashlib.sha256(image.read_bytes()).hexdigest()
                    page.set_viewport_size({"width": 390, "height": 844})
                    require(page.evaluate("document.documentElement.scrollWidth<=innerWidth"),
                            "MOBILE_PAGE_OVERFLOW")
                    require(not errors, "BROWSER_SCRIPT_ERROR")
                    page.locator("#logout").click()
                    expect(page.locator("#access")).to_be_visible()
                    # Test the revoked credential on a NEW transport. A server idle
                    # close racing an older pooled connection is not an auth result.
                    with httpx.Client(base_url=ORIGIN, trust_env=False, timeout=20,
                                      verify=ssl.create_default_context(
                                          cafile=str(PRIVATE / "tls/ca.pem")),
                                      headers=client.headers) as negative:
                        require(negative.get("/v1/jobs/" + item["job"]).status_code == 403,
                                "LOGGED_OUT_SESSION_STILL_READS_JOB")
                    context.close()
                    item["checks"].extend(["mobile_no_page_overflow", "logout_revokes_evidence"])
                    item["elapsed_seconds"] = round(time.monotonic()-started, 3)
                    save()
                    print(json.dumps({"case": name, "outcome": expected}), flush=True)
                browser.close()
            require(live.sql(counts) == baseline, "MODEL_CALL_OR_PR_INTENT_CREATED")
        finally:
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
