"""Real private repair acceptance on new synthetic development data, never final evaluation.

Programs are uploaded as inert bytes. Only the designated worker executes them.
The retained intent prevents repeating an uncertain model/worker submission.
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

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import expect, sync_playwright  # noqa: E402
from vultr_credit_guard import run as credit_guard  # noqa: E402
from vultr_phase1 import PRIVATE, ROOT, Admin  # noqa: E402

from api.app.auth import SessionSecrets, csrf_digest, session_digest  # noqa: E402

ORIGIN = "https://127.0.0.1:18443"


def require(condition, code):
    if not condition:
        raise RuntimeError(code)


def main():
    mode = sys.argv[1:]
    if mode not in ([], ["--revised-planner"], ["--bounded-context"]):
        raise RuntimeError("UNSUPPORTED_ACCEPTANCE_MODE")
    revision = 3 if mode == ["--bounded-context"] else 2 if mode else 1
    revised = revision > 1
    prior_name = "phase3-live-v2-intent.json" if revision == 3 else "phase3-live-intent.json"
    previous = json.loads((PRIVATE / "evidence" / prior_name).read_bytes()) if revised else None
    suffix = "-v" + str(revision) if revised else ""
    intent_path = PRIVATE / ("evidence/phase3-live" + suffix + "-intent.json")
    result_path = PRIVATE / ("evidence/phase3-live" + suffix + "-result.json")
    if intent_path.exists():
        raise RuntimeError("RECONCILE_RETAINED_PHASE3_INTENT_NO_BLIND_RESEND")
    intent = {
        "fixture_only": True,
        "created_at": datetime.now(UTC).isoformat(),
        "asset_ids": {
            k: str(uuid4()) for k in ("pipeline", "contract", "transactions", "customers")
        },
        "original_key": str(uuid4()),
        "repair_key": str(uuid4()),
    }
    if previous:
        intent["asset_ids"] = previous["asset_ids"]
        intent["previous_failed_repair"] = previous["repair_id"]
        intent["original_job"] = previous["original_job"]
    intent_path.write_bytes(json.dumps(intent, sort_keys=True).encode())
    admin, tunnel, policy, opened = Admin(), None, None, False
    report = {"checks": [], "fixture_only": True, "new_cloud_resources": 0}
    try:
        guard = credit_guard(admin, datetime.now(UTC))
        require(guard["credit_guard"] == "within_early_cutoff", "CREDIT_GUARD_NOT_ADMITTING")
        report["credit_before"] = guard

        def host(command, raw=None, timeout=60):
            result = admin.host("control", command, stdin=raw, timeout=timeout)
            if result.returncode:
                (PRIVATE / "evidence/phase3-host-failure.txt").write_bytes(result.stderr)
                raise RuntimeError("PHASE3_HOST_OPERATION_FAILED")
            return result.stdout.strip()

        def sql(statement, database="proofflow_product"):
            require(database in ("proofflow_product", "proofflow_budget"), "DATABASE_NOT_ALLOWED")
            return host(
                "docker exec -i --user=70:70 proofflow-budget psql -X -qAt "
                "-h /run/proofflow-budget -U postgres -d " + database + " --set ON_ERROR_STOP=1",
                statement.encode(),
            )

        require(
            host("cat /etc/machine-id").decode() == admin.state["control_machine_id"],
            "DESIGNATED_CONTROL_CHANGED",
        )
        old_id = str(
            UUID(
                json.loads((PRIVATE / "evidence/product-http-latest.json").read_bytes())["jobs"][0][
                    "id"
                ]
            )
        )
        old = json.loads(
            sql(
                "SELECT row_to_json(j) FROM pf_product.jobs j WHERE id='"  # noqa: S608
                + old_id
                + "';"
            )
        )
        workspace = str(UUID(old["workspace_id"]))
        secret = SessionSecrets.create()
        sql(
            "SET ROLE pf_product_provisioner; "
            f"SELECT pf_product.create_session('{workspace}','{session_digest(secret.token)}',"
            f"'{csrf_digest(secret.csrf)}',clock_timestamp()+interval '45 minutes');"
        )
        intent["workspace"] = workspace
        policy = json.loads(sql("SELECT row_to_json(p) FROM pf_product.execution_policy p;"))
        require(
            not policy["enabled"]
            and sql(
                "SELECT count(*) FROM pf_product.repairs WHERE "
                "state IN ('QUEUED','RUNNING','RECONCILING');"
            )
            == b"0",
            "QUEUE_NOT_CLOSED_IDLE",
        )
        report["reservations_before"] = json.loads(
            sql(
                "SELECT json_build_object('count',count(*),"
                "'held_micro',COALESCE(sum(reserved_micro),0)) FROM pf_budget.reservations;",
                "proofflow_budget",
            )
        )
        args = [
            "C:/Windows/System32/OpenSSH/ssh.exe",
            "-F",
            "NUL",
            "-N",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "HostKeyAlgorithms=ssh-ed25519",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "ExitOnForwardFailure=yes",
            "-o",
            "ConnectTimeout=10",
            "-o",
            "UserKnownHostsFile=" + str(PRIVATE / "known_hosts"),
            "-p",
            "443",
            "-i",
            str(PRIVATE / "operator_ed25519"),
            "-L",
            "127.0.0.1:18443:/run/proofflow-product-api/api.sock",
            "root@" + admin.state["hosts"]["control"]["address"],
        ]
        tunnel = subprocess.Popen(  # noqa: S603 - fixed pinned SSH, no candidate arguments
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )  # noqa: S603 - pinned host/key/local port
        for attempt in range(40):
            try:
                cert = ssl.get_server_certificate(
                    ("127.0.0.1", 18443), ca_certs=str(PRIVATE / "tls/ca.pem"), timeout=2
                )
                break
            except OSError:
                if tunnel.poll() is not None or attempt == 39:
                    raise RuntimeError("PRIVATE_TUNNEL_UNAVAILABLE") from None
                time.sleep(0.25)
        headers = {
            "Cookie": "__Host-proofflow=" + secret.token,
            "Origin": ORIGIN,
            "X-ProofFlow-CSRF": secret.csrf,
        }
        with httpx.Client(
            base_url=ORIGIN,
            headers=headers,
            timeout=15,
            trust_env=False,
            verify=ssl.create_default_context(cafile=str(PRIVATE / "tls/ca.pem")),
        ) as client:
            raw = {
                "pipeline": (ROOT / "tests/fixtures/phase2/wrong_owner.py.txt").read_bytes(),
                "contract": (ROOT / "contracts/examples/synthetic-v1.1.json").read_bytes(),
                "transactions": (
                    b"merchant_id,transaction_id,customer_id,amount,currency,occurred_at\n"
                    b"studio-north,new-sale,shared-development,73.41,USD,2026-11-04T08:30:00+09:00\n"
                    b"studio-south,new-refund,shared-development,-911,JPY,2026-11-04T00:00:00Z\n"
                    b"studio-north,new-sale,shared-development,73.41,USD,2026-11-04T08:30:00+09:00\n"
                    b"studio-south,new-zero,shared-development,0,JPY,2026-11-04T01:00:00Z\n"
                ),
                "customers": (
                    b"merchant_id,customer_id,canonical_customer_id\n"
                    b"studio-south,shared-development,dev-owner-south\n"
                    b"studio-north,shared-development,dev-owner-north\n"
                ),
            }
            intent["source_hashes"] = {k: hashlib.sha256(v).hexdigest() for k, v in raw.items()}
            intent_path.write_bytes(json.dumps(intent, sort_keys=True).encode())
            for kind, content in raw.items():
                response = client.post(
                    "/v1/assets/" + kind + "/" + intent["asset_ids"][kind], content=content
                )
                require(response.status_code == 201, "PHASE3_UPLOAD_REJECTED")
            response = client.post(
                "/v1/contracts/" + intent["asset_ids"]["contract"] + "/approve",
                json={"expected_sha256": intent["source_hashes"]["contract"], "confirm": True},
            )
            require(response.status_code == 200, "EXACT_SYNTHETIC_CONTRACT_REJECTED")
            sql(
                "SET ROLE pf_product_provisioner; SELECT pf_product.configure_execution('"
                + policy["runtime_sha256"]
                + "','"
                + policy["verifier_sha256"]
                + "',true);"
            )
            opened = True
            account = str(UUID(admin.state["budget_install_intent"]["account_id"]))
            sql(
                "UPDATE pf_budget.accounts SET blocked=false WHERE id='"  # noqa: S608 - UUID validated
                + account  # noqa: S608
                + "' AND expires_at>clock_timestamp();",
                "proofflow_budget",
            )
            if previous:
                prior = client.get("/v1/repairs/" + str(UUID(previous["repair_id"]))).json()
                require(
                    prior["state"] == "NEEDS_REVIEW"
                    and prior["outcome"]
                    == ("context_limit" if revision == 3 else "provider_unavailable"),
                    "PREVIOUS_REPAIR_NOT_TERMINAL_PROVIDER_FAILURE",
                )
                require(
                    intent["source_hashes"] == previous["source_hashes"],
                    "DEVELOPMENT_INPUT_CHANGED",
                )
                job = str(UUID(previous["original_job"]))
            else:
                enqueued = client.post(
                    "/v1/jobs",
                    json={
                        "idempotency_key": intent["original_key"],
                        **{k + "_id": v for k, v in intent["asset_ids"].items()},
                    },
                )
                require(enqueued.status_code == 202, "ORIGINAL_ENQUEUE_REJECTED")
                job = str(UUID(enqueued.json()["job_id"]))
            intent["original_job"] = job
            intent_path.write_bytes(json.dumps(intent, sort_keys=True).encode())
            for _ in range(90):
                original = client.get("/v1/jobs/" + job).json()
                if original["state"] in ("NEEDS_REVIEW", "FAILED_INFRA", "CANCELLED"):
                    break
                time.sleep(1)
            report["original"] = original
            require(original["outcome"] == "mismatch", "ORIGINAL_NOT_ACTUALLY_REJECTED")
            request = {"parent_id": job, "idempotency_key": intent["repair_key"]}
            response = client.post("/v1/repairs", json=request)
            require(response.status_code == 202, "REPAIR_ENQUEUE_REJECTED")
            repair = str(UUID(response.json()["repair_id"]))
            intent["repair_id"] = repair
            intent_path.write_bytes(json.dumps(intent, sort_keys=True).encode())
            require(
                client.post("/v1/repairs", json=request).json()["repair_id"] == repair,
                "REPAIR_IDEMPOTENCY_FAILED",
            )
            print(json.dumps({"original": "real_mismatch", "repair": "queued"}), flush=True)
            for _ in range(360):
                result = client.get("/v1/repairs/" + repair).json()
                if result["state"] not in ("QUEUED", "RUNNING", "RECONCILING"):
                    break
                time.sleep(1)
            report["repair"] = result
            result_path.write_bytes(json.dumps(report).encode())
            require(result["state"] == "AWAITING_APPROVAL", "REPAIR_DID_NOT_PASS")
            export = client.get("/v1/repairs/" + repair + "/export")
            require(export.status_code == 200, "VERIFIED_EXPORT_UNAVAILABLE")
            candidate = export.json()
            require(
                not candidate["activation_approved"]
                and candidate["diff"]
                and hashlib.sha256(candidate["candidate_source"].encode()).hexdigest()
                == candidate["candidate_sha256"],
                "CANDIDATE_EXPORT_BINDING_FAILED",
            )
            report["export"] = candidate
            executions = json.loads(
                sql(
                    "SELECT json_agg(e ORDER BY generation) FROM "  # noqa: S608
                    "pf_product.repair_executions e WHERE repair_id='" + repair + "';"
                )
            )
            report["executions"] = executions
            require(
                len({e["execution_id"] for e in executions}) == len(executions),
                "EXECUTION_ID_REUSED",
            )
            require(
                [e["purpose"] for e in executions[-3:]]
                == ["candidate", "canary_ownership", "canary_quarantine"],
                "PROTECTED_PROOFS_MISSING",
            )
            report["checks"].extend(
                [
                    "new_development_original_real_mismatch",
                    "real_vultr_bounded_candidate_fresh_worker_and_protected_canaries",
                    "owned_idempotent_repair_source_hash_export_no_activation",
                ]
            )
            # The same already-completed repair is displayed; no browser POST can
            # create a second inference request during this readback.
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
                input=cert.encode(),
                capture_output=True,
                check=True,
                timeout=15,
            ).stdout  # noqa: S603
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
            ).stdout  # noqa: S603
            spki = base64.b64encode(hashlib.sha256(der).digest()).decode()
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    args=["--ignore-certificate-errors-spki-list=" + spki]
                )
                page = browser.new_page(viewport={"width": 1366, "height": 1000})
                errors = []
                page.on("pageerror", lambda _: errors.append("BROWSER_SCRIPT_ERROR"))
                page.goto(ORIGIN)
                page.locator("#session-token").fill(secret.token)
                page.locator("#csrf-token").fill(secret.csrf)
                page.locator("#login button").click()
                expect(page.locator("#workspace")).to_be_visible()
                page.goto(ORIGIN + "/?job=" + job + "&repair=" + repair)
                expect(page.locator("#repair-state")).to_contain_text("AWAITING APPROVAL")
                expect(page.locator("#repair-export")).to_be_visible()
                page.locator("#repair-refresh").click()
                require(not errors, "REPAIR_BROWSER_SCRIPT_FAILED")
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
                browser.close()
            report["checks"].append("actual_browser_recorded_attempts_export_desktop_mobile")
            report["reservations_after"] = json.loads(
                sql(
                    "SELECT json_build_object('count',count(*),"
                    "'held_micro',COALESCE(sum(reserved_micro),0)) FROM pf_budget.reservations;",
                    "proofflow_budget",
                )
            )
            report["observed_at"] = datetime.now(UTC).isoformat()
            result_path.write_bytes(json.dumps(report).encode())
            print(
                json.dumps(
                    {
                        "passed": len(report["checks"]),
                        "calls": result["calls"],
                        "worker_executions": len(executions),
                        "reserved_micro": result["reserved_micro"],
                        "state": result["state"],
                        "activation_approved": False,
                    }
                ),
                flush=True,
            )
    finally:
        try:
            if opened:
                sql("UPDATE pf_budget.accounts SET blocked=true;", "proofflow_budget")
                sql(
                    "SET ROLE pf_product_provisioner; SELECT pf_product.configure_execution('"
                    + policy["runtime_sha256"]
                    + "','"
                    + policy["verifier_sha256"]
                    + "',false);"
                )
        finally:
            if tunnel is not None:
                tunnel.terminate()
                tunnel.wait(timeout=10)
            admin.close()


if __name__ == "__main__":
    main()
