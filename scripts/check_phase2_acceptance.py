"""Live private Phase2 gate: lost reply, same-job recovery, journal crash/cleanup.

Only the generated disposable synthetic workspace is retired. Existing evidence
is preserved. Candidate source is transported as bytes and runs on the worker.
"""

import base64
import hashlib
import json
import shlex
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
from vultr_phase1 import PRIVATE, ROOT, Admin  # noqa: E402

from api.app.auth import SessionSecrets, csrf_digest, session_digest  # noqa: E402

ORIGIN = "https://127.0.0.1:18443"


def require(condition, code):
    if not condition:
        raise RuntimeError(code)


def main():
    intent_path = PRIVATE / "evidence/phase2-final-intent.json"
    if intent_path.exists():
        raise RuntimeError("RECONCILE_RETAINED_ACCEPTANCE_INTENT_BEFORE_RERUN")
    workspace, secret = uuid4(), SessionSecrets.create()
    intent = {"workspace": str(workspace), "fixture_only": True, "submitted": False}
    intent_path.write_text(json.dumps(intent), encoding="utf-8")
    admin, tunnel, policy, timer_stopped = Admin(), None, None, False
    checks = []
    try:
        guard = credit_guard(admin, datetime.now(UTC))
        require(guard.get("credit_guard") == "within_early_cutoff", "CREDIT_GUARD_NOT_ADMITTING")

        def host(command, raw=None, timeout=60):
            result = admin.host("control", command, stdin=raw, timeout=timeout)
            if result.returncode:
                (PRIVATE / "evidence/phase2-final-host-failure.txt").write_bytes(result.stderr)
                raise RuntimeError("ACCEPTANCE_HOST_OPERATION_FAILED")
            return result.stdout.strip()

        def sql(statement):
            return host(
                "docker exec -i --user=70:70 proofflow-budget psql -X -qAt "
                "-h /run/proofflow-budget -U postgres -d proofflow_product --set ON_ERROR_STOP=1",
                statement.encode(),
            )

        require(
            host("cat /etc/machine-id").decode() == admin.state["control_machine_id"],
            "DESIGNATED_CONTROL_CHANGED",
        )
        before = {
            t: int(sql("SELECT count(*) FROM pf_product." + t + ";"))  # noqa: S608
            for t in ("workspaces", "assets", "jobs")
        }
        policy = json.loads(sql("SELECT row_to_json(p) FROM pf_product.execution_policy p;"))
        require(
            not policy["enabled"]
            and sql(
                "SELECT count(*) FROM pf_product.jobs WHERE state "
                "NOT IN ('NEEDS_REVIEW','FAILED_INFRA','CANCELLED');"
            )
            == b"0",
            "QUEUE_NOT_IDLE_CLOSED",
        )
        sql(
            "SET ROLE pf_product_provisioner; SELECT pf_product.create_workspace('"
            + str(workspace)
            + "','guest',clock_timestamp()+interval '1 hour');"
            f"SELECT pf_product.create_session('{workspace}','{session_digest(secret.token)}',"
            f"'{csrf_digest(secret.csrf)}',clock_timestamp()+interval '30 minutes');"
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
        tunnel = subprocess.Popen(  # noqa: S603 - pinned host/key and local port
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )  # noqa: S603 - pinned host/key and local port
        for attempt in range(40):
            try:
                cert = ssl.get_server_certificate(
                    ("127.0.0.1", 18443), ca_certs=str(PRIVATE / "tls/ca.pem"), timeout=2
                )
                break
            except OSError:
                if tunnel.poll() is not None or attempt == 39:
                    raise RuntimeError("PRIVATE_BROWSER_TUNNEL_UNAVAILABLE") from None
                time.sleep(0.25)
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
        ).stdout  # noqa: S603 - public certificate only
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
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            page = context.new_page()
            page.goto(ORIGIN, wait_until="networkidle")
            page.locator("#session-token").fill(secret.token)
            page.locator("#csrf-token").fill(secret.csrf)
            page.locator("#login button").click()
            expect(page.locator("#workspace")).to_be_visible()
            data = {
                "pipeline": (ROOT / "tests/fixtures/phase2/wrong_owner.py.txt").read_bytes(),
                "contract": (ROOT / "contracts/examples/synthetic-v1.1.json").read_bytes(),
                "transactions": b"merchant_id,transaction_id,customer_id,amount,currency,"
                b"occurred_at\n"
                b"A,t1,shared,1.00,USD,2026-11-01T00:00:00Z\n"
                b"B,t2,shared,2.00,USD,2026-11-01T00:00:00Z\n",
                "customers": b"merchant_id,customer_id,canonical_customer_id\n"
                b"A,shared,owner-A\nB,shared,owner-B\n",
            }
            for kind, raw in data.items():
                extension = {"pipeline": "py", "contract": "json"}.get(kind, "csv")
                page.locator("#" + kind).set_input_files(
                    {"name": kind + "." + extension, "mimeType": "text/plain", "buffer": raw}
                )
            page.locator("#files button").click()
            expect(page.locator("#confirm-contract")).to_be_enabled()
            expect(page.locator("#run")).to_be_disabled()
            page.locator("#confirm-contract").check()
            page.locator("#approve").click()
            expect(page.locator("#run")).to_be_enabled()
            sql(
                "SET ROLE pf_product_provisioner; SELECT pf_product.configure_execution('"
                + policy["runtime_sha256"]
                + "','"
                + policy["verifier_sha256"]
                + "',true);"
            )
            # Deliberately lose the acknowledged POST response, not the committed job.
            page.evaluate("""()=>{const original=window.fetch;window.fetch=async(...args)=>{
              const result=await original(...args);
              if(args[0]==='/v1/jobs'&&args[1]?.method==='POST'){
                window.fetch=original;throw new Error('synthetic lost response');}
              return result;};}""")
            intent["submitted"] = True
            intent_path.write_text(json.dumps(intent), encoding="utf-8")
            page.locator("#run").click()
            expect(page.locator("#retry")).to_be_visible()
            row = json.loads(
                sql(
                    "SELECT row_to_json(j) FROM pf_product.jobs j "  # noqa: S608
                    "WHERE workspace_id='" + str(workspace) + "';"
                )
            )
            job = str(UUID(row["id"]))
            intent["job"] = job
            intent_path.write_text(json.dumps(intent), encoding="utf-8")
            cached = page.evaluate("JSON.stringify(sessionStorage)")
            require(
                secret.token not in cached and secret.csrf not in cached,
                "SECRET_IN_BROWSER_RECOVERY_STORAGE",
            )
            page.reload(wait_until="networkidle")
            expect(page.locator("#retry")).to_be_visible()
            require(
                int(sql("SELECT count(*) FROM pf_product.jobs;")) == before["jobs"] + 1,
                "RELOAD_RESUBMITTED_JOB",
            )
            page.locator("#retry").click()
            expect(page.locator("#state")).to_have_text("Needs review", timeout=90000)
            require(page.url.endswith("?job=" + job), "RETRY_CREATED_DIFFERENT_JOB")
            require(
                int(sql("SELECT count(*) FROM pf_product.jobs;")) == before["jobs"] + 1,
                "IDEMPOTENCY_DID_NOT_DEDUPLICATE",
            )
            expect(page.locator("#witnesses")).to_contain_text("owner-A")
            expect(page.locator("#witnesses")).to_contain_text("owner-B")
            checks.append("lost_http_reply_reload_explicit_retry_same_committed_worker_job")
            row = json.loads(
                sql(
                    "SELECT row_to_json(j) FROM pf_product.jobs j "  # noqa: S608
                    "WHERE id='" + job + "';"
                )
            )
            execution = UUID(row["execution_id"]).hex
            require(row["worker_receipt"]["cleanup"] == "confirmed", "WORKER_CLEANUP_MISSING")
            host("test -f /var/lib/proofflow-product/jobs/" + execution + "/intent.json")
            host(
                "systemctl stop proofflow-product-retention.timer "
                "proofflow-product-retention.service"
            )
            timer_stopped = True
            page.locator("details.panel summary").click()
            page.locator("#confirm-delete").check()
            page.locator("#delete").click()
            expect(page.locator("#access")).to_be_visible()
            plans = json.loads(
                sql("SET ROLE pf_product_provisioner; SELECT pf_product.retention_plan();")
            )
            require(
                len(plans) == 1
                and plans[0]["workspace"] == str(workspace)
                and plans[0]["jobs"] == [job],
                "UNEXPECTED_DELETION_PLAN",
            )
            plan = plans[0]
            revision = json.loads(
                (PRIVATE / "evidence/product-retention-install.json").read_bytes()
            )["revision"]
            require(
                len(revision) == 64 and all(c in "0123456789abcdef" for c in revision),
                "INVALID_RETENTION_REVISION",
            )
            probe = (ROOT / "tests/security/retention_deployed_fault.py").read_bytes()
            digest = hashlib.sha256(probe).hexdigest()
            path = "/opt/proofflow-retention-probe/" + digest + ".py"
            host("install -d -m 0755 /opt/proofflow-retention-probe")
            host("umask 022; cat > " + path + " && chmod 0444 " + path, probe)
            require(host("sha256sum " + path).decode().split()[0] == digest, "PROBE_BYTES_CHANGED")
            args = [
                "systemd-run",
                "--quiet",
                "--wait",
                "--collect",
                "--pipe",
                "--unit=proofflow-retention-fault",
                "-p",
                "User=10003",
                "-p",
                "Group=10003",
                "-p",
                "UMask=0077",
                "-p",
                "PrivateNetwork=yes",
                "-p",
                "PrivateDevices=yes",
                "-p",
                "NoNewPrivileges=yes",
                "-p",
                "CapabilityBoundingSet=",
                "-p",
                "ProtectSystem=strict",
                "-p",
                "ProtectHome=yes",
                "-p",
                "RestrictNamespaces=yes",
                "-p",
                "RestrictAddressFamilies=AF_UNIX",
                "-p",
                "SystemCallFilter=~@network-io @mount @privileged",
                "-p",
                "BindPaths=/var/lib/proofflow-product/assets:/run/proofflow-retention-assets "
                "/var/lib/proofflow-product/jobs:/run/proofflow-retention-jobs",
                "-p",
                "ReadWritePaths=/run/proofflow-retention-assets /run/proofflow-retention-jobs",
                "-p",
                "MemoryMax=128M",
                "-p",
                "MemorySwapMax=0",
                "-p",
                "CPUQuota=100%",
                "-p",
                "TasksMax=16",
                "-p",
                "RuntimeMaxSec=20",
                "-p",
                "LimitNOFILE=64",
                "/usr/bin/python3",
                "-I",
                "-B",
                path,
                revision,
            ]
            fault = json.loads(host(shlex.join(args), json.dumps(plan).encode()))
            require(fault["partial_journal_retirement"], "FAULT_NOT_EXERCISED")
            retiring = (
                "/var/lib/proofflow-product/jobs/.retiring-" + workspace.hex + "-" + execution
            )
            host("test -d " + retiring + " && test ! -e " + retiring + "/intent.json")
            require(
                sql(
                    "SELECT completed_at IS NULL FROM pf_product.deletions "  # noqa: S608
                    "WHERE workspace_id='" + str(workspace) + "';"
                )
                == b"t",
                "FALSE_DELETION_COMPLETION",
            )
            checks.append("actual_journal_partial_deletion_does_not_claim_completion")
            host("systemctl start proofflow-product-retention.service", timeout=245)
            require(
                sql(
                    "SELECT completed_at IS NOT NULL FROM pf_product.deletions "  # noqa: S608
                    "WHERE workspace_id='" + str(workspace) + "';"
                )
                == b"t",
                "RETIREMENT_NOT_RECOVERED",
            )
            host(
                "test ! -e "
                + retiring
                + " && test ! -e /var/lib/proofflow-product/assets/"
                + workspace.hex
                + " && test -f /var/lib/proofflow-product/jobs/.deleted-"
                + UUID(job).hex
            )
            checks.append("production_timer_recovers_and_erases_actual_assets_journal_and_registry")
            after = {
                t: int(sql("SELECT count(*) FROM pf_product." + t + ";"))  # noqa: S608
                for t in before
            }
            require(before == after, "EXISTING_WORKSPACE_EVIDENCE_CHANGED")
            checks.append("preexisting_workspace_asset_and_job_counts_preserved")
            browser.close()
        report = {
            "observed_at": datetime.now(UTC).isoformat(),
            "checks": checks,
            "scope": "actual_deployed_private_phase2_acceptance",
            "fixture_only": True,
            "job": job,
            "execution": execution,
            "disposable_workspace": str(workspace),
            "counts_before_after": before,
            "new_worker_executions": 1,
            "new_provider_calls": 0,
            "new_cloud_resources": 0,
            "credit_guard": guard,
        }
        (PRIVATE / "evidence/phase2-final-latest.json").write_text(
            json.dumps(report), encoding="utf-8"
        )
        print(json.dumps({"passed": len(checks), "checks": checks, "new_provider_calls": 0}))
    finally:
        try:
            if policy is not None:
                sql(
                    "SET ROLE pf_product_provisioner; SELECT pf_product.configure_execution('"
                    + policy["runtime_sha256"]
                    + "','"
                    + policy["verifier_sha256"]
                    + "',false);"
                )
            if timer_stopped:
                host("systemctl start proofflow-product-retention.timer")
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

        (PRIVATE / "evidence/phase2-final-failure.txt").write_text(
            traceback.format_exc(), encoding="utf-8"
        )
        raise SystemExit(
            "PHASE2_ACCEPTANCE_FAILED: inspect private evidence, no blind retry"
        ) from None
