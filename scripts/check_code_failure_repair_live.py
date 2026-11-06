"""One real private API repair of the retained crash fixture; no activation/PR/final score."""

import hashlib
import json
import os
import shlex
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from product_live_session import LiveSession, require
from vultr_phase1 import PRIVATE

from orchestrator.probe_plan import RateQuote
from orchestrator.repair_provider import prepare_repair_plan


def main():
    path = PRIVATE / "evidence/phase5-code-failure-repair.json"
    require(not path.exists(), "CRASH_REPAIR_STARTED_RECONCILE_NO_RETRY")
    prior = json.loads((PRIVATE / "evidence/phase5-original-failure-live.json").read_bytes())
    followup = json.loads(
        (PRIVATE / "evidence/phase5-original-failure-live-followup.json").read_bytes()
    )
    require(
        followup["completed"] and all(c["accepted"] for c in followup["cases"]),
        "ORIGINAL_FAILURE_GATES_NOT_PASSED",
    )
    first = prior["cases"][0]
    require(first["name"] == "code_failure" and first["accepted"], "ORIGINAL_CRASH_NOT_PASSED")
    workspace, job = str(UUID(prior["workspace"])), str(UUID(first["job_id"]))
    config = json.loads((PRIVATE / "repair-provider.json").read_bytes())
    quote = dict(config["quote"])
    for field in ("observed_at", "valid_until"):
        quote[field] = datetime.fromisoformat(quote[field])
    now = datetime.now(UTC)
    require(quote["valid_until"] > now + timedelta(minutes=10), "QUOTE_WINDOW_TOO_SHORT")
    per_call = prepare_repair_plan(
        "bounded fixture estimate", RateQuote(**quote), now
    ).reserve_micro_usd
    require(3 * per_call <= 100000, "ONE_JOB_EVALUATION_CAP")
    record = {
        "fixture_only": True,
        "workspace": workspace,
        "parent_id": job,
        "idempotency_key": str(uuid4()),
        "max_calls": 3,
        "max_reserved_micro": 3 * per_call,
        "created_at": now.isoformat(),
        "completed": False,
    }

    def persist():
        with path.open('w', encoding='utf-8') as output:
            json.dump(record, output, indent=2)
            output.flush()
            os.fsync(output.fileno())

    with LiveSession() as live:
        require(
            live.sql("SELECT bool_and(blocked) FROM pf_budget.accounts;", "proofflow_budget")
            == b"t",
            "BUDGET_MUST_START_CLOSED",
        )
        installed = json.loads(live.host("cat /etc/proofflow-repair/config.json"))
        require(installed == config, "INSTALLED_QUOTE_CHANGED")
        used = int(live.sql("SELECT reserved_micro FROM pf_product.repair_allocation;"))
        require(used + 3 * per_call <= 5000000, "DEVELOPMENT_ENVELOPE_EXHAUSTED")
        record.update(
            credit=live.credit, policy=live.policy, development_before=used, quote=config["quote"]
        )
        persist()  # No paid action can precede this durable intent.
        client = live.login(workspace)
        before = live.sql("SELECT json_agg(to_jsonb(p)) FROM pf_product.pr_intents p;")
        stop = [
            "/usr/bin/docker",
            "exec",
            "--user=70:70",
            "proofflow-budget",
            "psql",
            "-X",
            "-qAt",
            "-h",
            "/run/proofflow-budget",
            "-U",
            "postgres",
            "-d",
            "proofflow_budget",
            "-c",
            "UPDATE pf_budget.accounts SET blocked=true;",
        ]
        live.host(
            "systemd-run --quiet --on-active=12min --unit=proofflow-crash-repair-budget-stop "
            + shlex.join(stop)
        )
        try:
            live.sql("UPDATE pf_budget.accounts SET blocked=false;", "proofflow_budget")
            live.opened = True
            live.admission(True)
            request = {"parent_id": job, "idempotency_key": record["idempotency_key"]}
            response = client.post("/v1/repairs", json=request)
            require(response.status_code == 202, "CRASH_REPAIR_ENQUEUE_FAILED")
            repair = str(UUID(response.json()["repair_id"]))
            record["repair_id"] = repair
            persist()
            print(
                json.dumps({"repair": "queued", "maximum_reserved_usd": 3 * per_call / 1000000}),
                flush=True,
            )
            deadline = time.monotonic() + 360
            while True:
                response = client.get("/v1/repairs/" + repair)
                require(response.status_code == 200, "CRASH_REPAIR_READBACK_FAILED")
                result = response.json()
                if result["state"] not in ("QUEUED", "RUNNING", "RECONCILING"):
                    break
                require(time.monotonic() < deadline, "CRASH_REPAIR_DEADLINE")
                time.sleep(1)
            record["repair"] = result
            record["executions"] = json.loads(
                live.sql(
                    "SELECT json_agg(e ORDER BY generation) FROM pf_product.repair_executions e "  # noqa: S608 - canonical UUID above
                    "WHERE repair_id='" + repair + "';"
                )
            )
            record["development_after"] = int(
                live.sql("SELECT reserved_micro FROM pf_product.repair_allocation;")
            )
            persist()
            require(
                result["state"] == "AWAITING_APPROVAL" and result["outcome"] == "candidate_passed",
                "CRASH_REPAIR_DID_NOT_PASS",
            )
            require(
                1 <= result["calls"] <= 3 and record["development_after"] - used <= 3 * per_call,
                "CRASH_REPAIR_BOUND_EXCEEDED",
            )
            executions = record["executions"]
            require(
                len({e["execution_id"] for e in executions}) == len(executions)
                and [e["purpose"] for e in executions[-3:]]
                == ["candidate", "canary_ownership", "canary_quarantine"],
                "FRESH_PROOFS_MISSING",
            )
            require(
                all(e["result"]["worker"]["cleanup"] == "confirmed" for e in executions),
                "CRASH_REPAIR_CLEANUP_UNCERTAIN",
            )
            response = client.get("/v1/repairs/" + repair + "/export")
            require(response.status_code == 200, "CRASH_REPAIR_EXPORT_FAILED")
            export = response.json()
            require(
                export["activation_approved"] is False
                and hashlib.sha256(export["candidate_source"].encode()).hexdigest()
                == export["candidate_sha256"],
                "CRASH_REPAIR_EXPORT_BINDING",
            )
            record["export"] = export
            require(
                live.sql("SELECT json_agg(to_jsonb(p)) FROM pf_product.pr_intents p;") == before,
                "PR_STATE_CHANGED",
            )
            record["completed"] = True
        finally:
            live.sql("UPDATE pf_budget.accounts SET blocked=true;", "proofflow_budget")
            live.admission(False)
            record["budget_and_admission_closed"] = True
            record["finished_at"] = datetime.now(UTC).isoformat()
            persist()
            live.host("systemctl stop proofflow-crash-repair-budget-stop.timer")
        print(
            json.dumps(
                {
                    "completed": record["completed"],
                    "calls": record["repair"]["calls"],
                    "execution_count": len(record["executions"]),
                    "activated": False,
                    "reserved_micro": record["development_after"] - used,
                }
            )
        )


if __name__ == "__main__":
    main()
