"""Read back the actual model repair; replay exact bytes with zero model calls and erase guest."""

import base64
import hashlib
import io
import json
import subprocess
import time
import zipfile
from datetime import UTC, datetime
from uuid import UUID, uuid4

from playwright.sync_api import expect, sync_playwright
from product_live_session import ORIGIN, PRIVATE, LiveSession, require


def bundle(response):
    require(response.status_code == 200, "EVIDENCE_BUNDLE_UNAVAILABLE")
    raw = response.content
    require(
        hashlib.sha256(raw).hexdigest() == response.headers["x-proofflow-sha256"],
        "BUNDLE_TRANSPORT_HASH_CHANGED",
    )
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        require(
            set(archive.namelist())
            == {item["path"] for item in manifest["files"]} | {"manifest.json"},
            "BUNDLE_INVENTORY_CHANGED",
        )
        files = {}
        for item in manifest["files"]:
            value = archive.read(item["path"])
            require(
                len(value) == item["bytes"] and hashlib.sha256(value).hexdigest() == item["sha256"],
                "BUNDLE_FILE_HASH_CHANGED",
            )
            files[item["path"]] = value
    require(
        manifest["candidate_verified"]
        and not manifest["activation_approved"]
        and not manifest["protected_canary_material_included"],
        "BUNDLE_CLAIM_INVALID",
    )
    return files, manifest, raw


def main():
    intent_path = PRIVATE / "evidence/phase3-final-intent.json"
    if intent_path.exists():
        raise RuntimeError("RECONCILE_EXISTING_FINAL_INTENT_NO_BLIND_REPLAY")
    previous = json.loads((PRIVATE / "evidence/phase3-live-v3-intent.json").read_bytes())
    guest = str(uuid4())
    intent = {
        "guest": guest,
        "source_repair": str(UUID(previous["repair_id"])),
        "fixture_only": True,
    }
    intent_path.write_bytes(json.dumps(intent).encode())
    result = {"checks": [], "provider_calls": 0, "new_cloud_resources": 0, "fixture_only": True}
    with LiveSession() as session:
        client = session.login(previous["workspace"])
        files, manifest, raw = bundle(
            client.get("/v1/repairs/" + intent["source_repair"] + "/bundle")
        )
        (PRIVATE / "evidence/phase3-candidate-bundle.zip").write_bytes(raw)
        result["model_bundle"] = manifest
        result["bundle_sha256"] = hashlib.sha256(raw).hexdigest()
        result["checks"].append(
            "actual_owned_bundle_exact_source_inputs_outputs_receipts_inventory"
        )
        # Read the same passed model run in Chromium. No inference POST is made.
        public = subprocess.run(
            [
                "C:/Windows/System32/wsl.exe",
                "-d",
                "Ubuntu-24.04",
                "--",
                "/usr/bin/openssl",
                "x509",
                "-pubkey",
                "-noout",
            ],
            input=session.cert.encode(),
            capture_output=True,
            check=True,
            timeout=15,
        ).stdout  # noqa: S603 - certificate only
        der = subprocess.run(
            [
                "C:/Windows/System32/wsl.exe",
                "-d",
                "Ubuntu-24.04",
                "--",
                "/usr/bin/openssl",
                "pkey",
                "-pubin",
                "-outform",
                "DER",
            ],
            input=public,
            capture_output=True,
            check=True,
            timeout=15,
        ).stdout  # noqa: S603 - public key only
        spki = base64.b64encode(hashlib.sha256(der).digest()).decode()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                args=["--ignore-certificate-errors-spki-list=" + spki]
            )
            page = browser.new_page(viewport={"width": 1366, "height": 1000})
            errors = []
            page.on("pageerror", lambda _: errors.append("BROWSER_SCRIPT_ERROR"))
            page.goto(ORIGIN)
            page.locator("#session-token").fill(session.secret.token)
            page.locator("#csrf-token").fill(session.secret.csrf)
            page.locator("#login button").click()
            expect(page.locator("#workspace")).to_be_visible()
            page.goto(
                ORIGIN
                + "/?job="
                + str(UUID(previous["original_job"]))
                + "&repair="
                + intent["source_repair"]
            )
            expect(page.locator("#repair-state")).to_contain_text("AWAITING APPROVAL")
            expect(page.locator("#repair-bundle")).to_be_visible()
            expect(page.locator("#repair-attempts")).to_contain_text("canary ownership")
            page.screenshot(
                path=str(PRIVATE / "evidence/phase3-browser-desktop.png"), full_page=True
            )
            page.set_viewport_size({"width": 390, "height": 844})
            require(
                not page.evaluate("document.documentElement.scrollWidth>innerWidth"),
                "REPAIR_BROWSER_MOBILE_OVERFLOW",
            )
            page.screenshot(
                path=str(PRIVATE / "evidence/phase3-browser-mobile.png"), full_page=True
            )
            require(not errors, "REPAIR_BROWSER_SCRIPT_FAILED")
            browser.close()
        result["checks"].append("actual_browser_check_receipts_download_desktop_mobile")
        baseline = json.loads(
            session.sql(
                "SELECT json_build_object('workspaces',(SELECT count(*) FROM "
                "pf_product.workspaces),'assets',(SELECT count(*) FROM pf_product.assets),'jobs',"
                "(SELECT count(*) FROM pf_product.jobs),'repairs',"
                "(SELECT count(*) FROM pf_product.repairs));"
            )
        )
        reservations = session.sql(
            "SELECT count(*) FROM pf_budget.reservations;", "proofflow_budget"
        )
        require(
            session.sql("SELECT bool_and(blocked) FROM pf_budget.accounts;", "proofflow_budget")
            == b"t",
            "MODEL_ADMISSION_MUST_REMAIN_CLOSED",
        )
        session.sql(
            "SET ROLE pf_product_provisioner; SELECT pf_product.create_workspace('"
            + guest
            + "','guest',clock_timestamp()+interval '1 hour');"
        )
        client = session.login(guest)
        require(
            client.get("/v1/repairs/" + intent["source_repair"] + "/bundle").status_code == 404,
            "CROSS_WORKSPACE_BUNDLE_LEAK",
        )
        ids = {}
        source_files = {
            "pipeline": "candidate/pipeline.py",
            "contract": "input/contract.json",
            "transactions": "input/transactions.csv",
            "customers": "input/customers.csv",
        }
        for kind, name in source_files.items():
            ids[kind + "_id"] = str(uuid4())
            response = client.post(
                "/v1/assets/" + kind + "/" + ids[kind + "_id"], content=files[name]
            )
            require(response.status_code == 201, "REPLAY_UPLOAD_FAILED")
        require(
            client.post(
                "/v1/contracts/" + ids["contract_id"] + "/approve",
                json={
                    "expected_sha256": hashlib.sha256(files["input/contract.json"]).hexdigest(),
                    "confirm": True,
                },
            ).status_code
            == 200,
            "REPLAY_EXACT_CONTRACT_REJECTED",
        )
        session.admission(True)
        response = client.post("/v1/jobs", json={**ids, "idempotency_key": str(uuid4())})
        require(response.status_code == 202, "REPLAY_ENQUEUE_FAILED")
        original_id = str(UUID(response.json()["job_id"]))
        intent["original_job"] = original_id
        intent_path.write_bytes(json.dumps(intent).encode())
        for _ in range(90):
            original = client.get("/v1/jobs/" + original_id).json()
            if original["state"] in ("NEEDS_REVIEW", "FAILED_INFRA", "CANCELLED"):
                break
            time.sleep(1)
        require(original["outcome"] == "match", "EXACT_BYTE_REPLAY_DID_NOT_MATCH")
        selected = [
            e for e in json.loads(files["repair/receipts.json"]) if e["purpose"] == "candidate"
        ][-1]
        require(
            original["report"]["semantic"]["report"]["result"]["output_hashes"]
            == selected["result"]["semantic"]["report"]["result"]["output_hashes"],
            "REPLAY_OUTPUT_BYTES_DIFFERED",
        )
        request = {"parent_id": original_id, "idempotency_key": str(uuid4())}
        response = client.post("/v1/repairs", json=request)
        require(response.status_code == 202, "UNCHANGED_SOURCE_ENQUEUE_FAILED")
        repair_id = str(UUID(response.json()["repair_id"]))
        intent["repair_id"] = repair_id
        intent_path.write_bytes(json.dumps(intent).encode())
        for _ in range(180):
            repair = client.get("/v1/repairs/" + repair_id).json()
            if repair["state"] not in ("QUEUED", "RUNNING", "RECONCILING"):
                break
            time.sleep(1)
        result["replay_original"] = original
        result["unchanged"] = repair
        require(
            repair["state"] == "AWAITING_APPROVAL"
            and repair["calls"] == 0
            and repair["mode"] == "original"
            and repair["reserved_micro"] == 0,
            "UNCHANGED_PATH_NOT_VERIFIED_WITHOUT_MODEL",
        )
        require(
            len(repair["checks"]) == 3
            and all(
                c["cleanup_confirmed"] and c["comparison"] == "match" for c in repair["checks"]
            ),
            "UNCHANGED_CANARY_PROOFS_MISSING",
        )
        require(
            [e["sequence"] for e in repair["events"]] == list(range(1, len(repair["events"]) + 1)),
            "ACTUAL_REPAIR_EVENTS_NOT_MONOTONIC",
        )
        _, replay_manifest, replay_zip = bundle(client.get("/v1/repairs/" + repair_id + "/bundle"))
        (PRIVATE / "evidence/phase3-replay-bundle.zip").write_bytes(replay_zip)
        result["replay_bundle"] = replay_manifest
        result["checks"].append(
            "exact_byte_worker_replay_original_plus_fresh_canaries_zero_model_monotonic_events"
        )
        require(
            session.sql("SELECT count(*) FROM pf_budget.reservations;", "proofflow_budget")
            == reservations,
            "UNEXPECTED_PROVIDER_RESERVATION",
        )
        response = client.post(
            "/v1/workspace/delete", json={"workspace_id": guest, "confirm": True}
        )
        require(response.status_code == 200, "REPLAY_GUEST_REVOCATION_FAILED")
        require(
            client.get("/v1/repairs/" + repair_id + "/bundle").status_code == 403,
            "DELETED_WORKSPACE_BUNDLE_STILL_ACCESSIBLE",
        )
        for _ in range(90):
            done = session.sql(
                "SELECT completed_at IS NOT NULL FROM pf_product.deletions WHERE workspace_id='"  # noqa: S608 - generated UUID
                + guest
                + "';"
            )
            if done == b"t":
                break
            time.sleep(1)
        require(done == b"t", "REPAIR_GUEST_BYTES_NOT_RETIRED")
        after = json.loads(
            session.sql(
                "SELECT json_build_object('workspaces',(SELECT count(*) FROM "
                "pf_product.workspaces),'assets',(SELECT count(*) FROM pf_product.assets),'jobs',"
                "(SELECT count(*) FROM pf_product.jobs),'repairs',"
                "(SELECT count(*) FROM pf_product.repairs));"
            )
        )
        require(after == baseline, "RETENTION_CHANGED_EXISTING_EVIDENCE")
        result["checks"].append(
            "actual_repair_journal_candidate_registry_revocation_deletion_preserves_existing"
        )
        result["retained_counts"] = after
        result["credit"] = session.credit
        result["observed_at"] = datetime.now(UTC).isoformat()
        (PRIVATE / "evidence/phase3-final-result.json").write_bytes(json.dumps(result).encode())
        print(
            json.dumps(
                {
                    "passed": len(result["checks"]),
                    "provider_calls": 0,
                    "fresh_worker_executions": 4,
                    "guest_deleted": True,
                    "activation_approved": False,
                }
            )
        )


if __name__ == "__main__":
    main()
