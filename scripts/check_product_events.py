"""Reuse existing synthetic workspaces; verify real event transport without worker execution."""

import json
import shlex
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vultr_credit_guard import run as credit_guard  # noqa: E402
from vultr_phase1 import PRIVATE, ROOT, Admin  # noqa: E402

from api.app.auth import SessionSecrets, csrf_digest, session_digest  # noqa: E402


def main():
    admin, stopped, policy = Admin(), False, None
    try:
        guard = credit_guard(admin, datetime.now(UTC))
        if guard.get("credit_guard") != "within_early_cutoff":
            raise RuntimeError("CREDIT_GUARD_NOT_ADMITTING")
        def host(command, raw=None, timeout=90):
            result = admin.host("control", command, stdin=raw, timeout=timeout)
            if result.returncode:
                (PRIVATE / "evidence/product-events-failure.txt").write_bytes(result.stderr)
                raise RuntimeError("EVENT_PROBE_FAILED_RECONCILE")
            return result.stdout
        def sql(statement):
            return host("docker exec -i --user=70:70 proofflow-budget psql -X -qAt "
                "-h /run/proofflow-budget -U postgres -d proofflow_product --set ON_ERROR_STOP=1",
                statement.encode()).strip()
        if host("cat /etc/machine-id").decode().strip() != admin.state["control_machine_id"]:
            raise RuntimeError("DESIGNATED_CONTROL_CHANGED")
        existing = str(UUID(json.loads((PRIVATE / "evidence/product-http-latest.json")
                                      .read_bytes())["jobs"][0]["id"]))
        job = json.loads(sql("SELECT row_to_json(j) FROM pf_product.jobs j WHERE id='"  # noqa: S608 - UUID
                             + existing + "';"))
        workspace = str(UUID(job["workspace_id"]))
        foreign = str(UUID(sql("SELECT id FROM pf_product.workspaces WHERE id<>'"  # noqa: S608 - UUID
                    + workspace + "' AND expires_at>clock_timestamp() AND revoked_at IS NULL "
                    "ORDER BY created_at LIMIT 1;").decode()))
        if sql("SELECT count(*) FROM pf_product.jobs WHERE state NOT IN "
               "('NEEDS_REVIEW','FAILED_INFRA','CANCELLED');") != b"0":
            raise RuntimeError("EVENT_PROBE_REQUIRES_IDLE_QUEUE")
        policy = json.loads(sql("SELECT row_to_json(p) FROM pf_product.execution_policy p;"))
        if policy["enabled"]:
            raise RuntimeError("EVENT_PROBE_REQUIRES_CLOSED_ADMISSION")
        secrets = {key: SessionSecrets.create() for key in ("control", "stream", "foreign")}
        for key, value in secrets.items():
            wid = foreign if key == "foreign" else workspace
            sql("SET ROLE pf_product_provisioner; "
                f"SELECT pf_product.create_session('{wid}','{session_digest(value.token)}',"
                f"'{csrf_digest(value.csrf)}',clock_timestamp()+interval '1 hour');")
        host("systemctl stop proofflow-product-dispatcher.service")
        stopped = True
        running = json.loads(host(
            "docker inspect proofflow-product-dispatcher"))[0]["State"]["Running"]
        if running:
            raise RuntimeError("DISPATCHER_STOP_UNCONFIRMED")
        key = str(uuid4())
        intent = {"existing_job": existing, "workspace": workspace, "idempotency_key": key,
                  "dispatcher_stopped": True, "fixture_only": True}
        (PRIVATE / "evidence" / (key + ".events-intent.json")).write_bytes(
            json.dumps(intent).encode())
        sql("SET ROLE pf_product_provisioner; SELECT pf_product.configure_execution('"
            + policy["runtime_sha256"] + "','" + policy["verifier_sha256"] + "',true);")
        script = (ROOT / "scripts/probe_product_events_http.py").read_text(encoding="utf-8")
        payload = {key: {"session": val.token, "csrf": val.csrf} for key, val in secrets.items()}
        payload.update(existing_job=existing, enqueue={"idempotency_key": key,
            **{k: job[k] for k in ("pipeline_id", "transactions_id",
                                  "customers_id", "contract_id")}})
        report = json.loads(host("docker exec -i proofflow-product-api python -c "
                                + shlex.quote(script), json.dumps(payload).encode()))
        fixture = str(UUID(report["fixture_job"]))
        if sql("SELECT execution_id IS NULL FROM pf_product.jobs WHERE id='"  # noqa: S608 - UUID
               + fixture + "';") != b"t":
            raise RuntimeError("EVENT_FIXTURE_EXECUTED_UNEXPECTEDLY")
        report.update(observed_at=datetime.now(UTC).isoformat(), credit_guard=guard)
        (PRIVATE / "evidence/product-events-latest.json").write_bytes(json.dumps(report).encode())
        print(json.dumps({"groups": len(report["checks"]), "replayed_events": report["events"],
                          "worker_executions": 0, "provider_calls": 0}))
    finally:
        try:
            if stopped:
                sql("SET ROLE pf_product_provisioner; SELECT pf_product.configure_execution('"
                    + policy["runtime_sha256"] + "','" + policy["verifier_sha256"] + "',false);")
                host("systemctl start proofflow-product-dispatcher.service")
        finally:
            admin.close()


if __name__ == "__main__":
    main()
