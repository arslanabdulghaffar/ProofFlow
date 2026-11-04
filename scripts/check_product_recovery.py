"""Real queued cancellation and dispatcher death, preserving every execution record."""

import base64
import json
import shlex
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vultr_credit_guard import run as credit_guard  # noqa: E402
from vultr_phase1 import PRIVATE, ROOT, Admin  # noqa: E402

from api.app.auth import SessionSecrets, csrf_digest, session_digest  # noqa: E402


def main():
    probe, workspace, secret = uuid4().hex, uuid4(), SessionSecrets.create()
    cases = {name: str(uuid4()) for name in ("cancel", "dispatcher_death")}
    evidence = {"probe": probe, "workspace": str(workspace), "cases": cases,
                "fixture_only": True, "started_at": datetime.now(UTC).isoformat()}
    path = PRIVATE / "evidence" / (probe + ".recovery-intent.json")
    with path.open("x", encoding="utf-8") as file:
        json.dump(evidence, file)
    admin = Admin()
    try:
        if credit_guard(admin, datetime.now(UTC)).get("credit_guard") != "within_early_cutoff":
            raise RuntimeError("CREDIT_GUARD_NOT_ADMITTING")
        def host(command, raw=None, timeout=90):
            result = admin.host("control", command, stdin=raw, timeout=timeout)
            if result.returncode:
                raise RuntimeError("RECOVERY_PROBE_FAILED_RECONCILE")
            return result.stdout
        psql = ("docker exec -i --user=70:70 proofflow-budget psql -X -qAt "
                "-h /run/proofflow-budget -U postgres -d proofflow_product --set ON_ERROR_STOP=1")
        def sql(statement):
            return host(psql, statement.encode()).strip()
        if host("cat /etc/machine-id").decode().strip() != admin.state["control_machine_id"]:
            raise RuntimeError("DESIGNATED_CONTROL_CHANGED")
        if sql("SELECT count(*) FROM pf_product.jobs WHERE state NOT IN "
               "('NEEDS_REVIEW','FAILED_INFRA','CANCELLED');") != b"0":
            raise RuntimeError("PRIOR_JOB_UNSETTLED")
        sql("BEGIN; SET ROLE pf_product_provisioner; "
            f"SELECT pf_product.create_workspace('{workspace}','operator',"
            "clock_timestamp()+interval '23 hours'); "
            f"SELECT pf_product.create_session('{workspace}','{session_digest(secret.token)}',"
            f"'{csrf_digest(secret.csrf)}',clock_timestamp()+interval '2 hours'); COMMIT;")
        client = (ROOT / "scripts/probe_product_recovery_http.py").read_text(encoding="utf-8")
        def http(value):
            return json.loads(host("docker exec -i proofflow-product-api python -c "
                + shlex.quote(client), json.dumps({"session": secret.token, "csrf": secret.csrf,
                                                   **value}).encode()))
        payload = {key: base64.b64encode(raw).decode() for key, raw in {
            "pipeline": (ROOT / "tests/fixtures/phase2/deadline.py.txt").read_bytes(),
            "contract": (ROOT / "contracts/examples/synthetic-v1.1.json").read_bytes(),
            "transactions": b"merchant_id,transaction_id,customer_id,amount,currency,occurred_at\n"
                            b"A,T1,C,1.00,USD,2026-11-01T00:00:00Z\n",
            "customers": b"merchant_id,customer_id,canonical_customer_id\nA,C,owner-A\n",
        }.items()}
        results = []
        for case, key in cases.items():
            job = str(UUID(http({**payload, "operation": "enqueue",
                                 "idempotency_key": key})["job_id"]))
            def state(job=job):
                return json.loads(sql("SELECT row_to_json(j) FROM pf_product.jobs j "  # noqa: S608 - UUIDs
                    f"WHERE workspace_id='{workspace}' AND id='{job}';"))
            deadline = time.monotonic() + 45
            while True:
                before = state()
                if before["execution_id"] is not None:
                    break
                if time.monotonic() > deadline:
                    raise RuntimeError("EXECUTION_NOT_STARTED")
                time.sleep(0.2)
            # The immutable execution intent has committed. No direct job status edits.
            if case == "cancel":
                http({"operation": "cancel", "job": job})
            else:
                host("docker kill --signal=KILL proofflow-product-dispatcher")
            deadline = time.monotonic() + 110
            while True:
                after = state()
                if after["state"] in ("CANCELLED", "FAILED_INFRA"):
                    break
                if time.monotonic() > deadline:
                    raise RuntimeError("RECOVERY_NOT_TERMINAL")
                time.sleep(1)
            if (after["execution_id"] != before["execution_id"]
                    or after["execution_generation"] != before["execution_generation"]
                    or after["worker_receipt"]["cleanup"] != "confirmed"
                    or after["state"] != ("CANCELLED" if case == "cancel" else "FAILED_INFRA")):
                raise RuntimeError("RECOVERY_BINDING_OR_CLEANUP_FAILED")
            if case == "dispatcher_death" and after["generation"] <= before["generation"]:
                raise RuntimeError("RECOVERY_DID_NOT_RECLAIM_LEASE")
            results.append({"case": case, "job": job, "execution": after["execution_id"],
                "execution_generation": after["execution_generation"],
                "final_generation": after["generation"], "state": after["state"],
                "worker_receipt": after["worker_receipt"], "cleanup": "confirmed"})
            print(json.dumps({"case": case, "state": after["state"],
                              "same_execution": True, "cleanup": "confirmed"}), flush=True)
        evidence.update(results=results, completed_at=datetime.now(UTC).isoformat(),
                        provider_calls=0)
        (PRIVATE / "evidence/product-recovery-latest.json").write_bytes(
            json.dumps(evidence).encode())
    finally:
        admin.close()


if __name__ == "__main__":
    main()
