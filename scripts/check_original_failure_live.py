"""Three finite real HTTP/worker/source-verifier fixtures; no inference/activation/PR."""

import hashlib
import json
import sys
import time
from datetime import UTC, datetime
from uuid import uuid4

from product_live_session import LiveSession, require
from vultr_phase1 import PRIVATE, ROOT


def main():
    require(sys.argv[1:] in ([], ["--followup"]), "UNEXPECTED_PROBE_MODE")
    followup = sys.argv[1:] == ["--followup"]
    path = PRIVATE / (
        "evidence/phase5-original-failure-live" + ("-followup" if followup else "") + ".json"
    )
    require(not path.exists(), "SOURCE_FAILURE_PROBE_STARTED_RECONCILE_NO_RETRY")
    workspace = str(uuid4())
    contract = (ROOT / "contracts/examples/synthetic-v1.1.json").read_bytes()
    tx = (
        b"merchant_id,transaction_id,customer_id,amount,currency,occurred_at\n"
        b"A,t1,c1,1.23,USD,2026-11-01T00:00:00Z\n"
    )
    cs = b"merchant_id,customer_id,canonical_customer_id\nA,c1,owner-A\n"
    record = {
        "fixture_only": True,
        "workspace": workspace,
        "created_at": datetime.now(UTC).isoformat(),
        "cases": [],
        "completed": False,
        "provider_calls": 0,
    }

    def persist():
        path.write_text(json.dumps(record, indent=2), encoding="utf-8")

    with LiveSession() as live:
        record["credit"] = live.credit
        record["policy"] = live.policy
        require(
            live.sql("SELECT bool_and(blocked) FROM pf_budget.accounts;", "proofflow_budget")
            == b"t",
            "BUDGET_MUST_BE_CLOSED",
        )
        persist()
        live.sql(
            "SET ROLE pf_product_provisioner; SELECT pf_product.create_workspace('"
            + workspace
            + "','operator',clock_timestamp()+interval '2 hours');"
        )
        client = live.login(workspace)
        try:
            # Mark before COMMIT delivery: the finally path closes even if its reply is lost.
            live.opened = True
            live.admission(True)
            for name, pipeline, customers, expected, blocked in (
                (
                    "code_failure",
                    b"raise KeyError('legacy customer column')\n",
                    cs,
                    "execution_failed",
                    0,
                ),
                ("missing_outputs", b"# deliberately no output files\n", cs, "execution_failed", 0),
                (
                    "invalid_source",
                    b"raise KeyError('legacy customer column')\n",
                    b"merchant_id,customer_id,canonical_customer_id\nA,other,owner-A\n",
                    "held",
                    1,
                ),
            ):
                if followup and name == "code_failure":
                    continue  # Already passed; keep its exact receipt in the prior record.
                data = {
                    "pipeline": pipeline,
                    "transactions": tx,
                    "customers": customers,
                    "contract": contract,
                }
                case = {
                    "name": name,
                    "assets": {kind: str(uuid4()) for kind in data},
                    "idempotency_key": str(uuid4()),
                    "expected": expected,
                }
                record["cases"].append(case)
                persist()
                for kind, raw in data.items():
                    response = client.post(
                        "/v1/assets/" + kind + "/" + case["assets"][kind], content=raw
                    )
                    require(response.status_code == 201, "FIXTURE_UPLOAD_FAILED")
                    require(
                        response.json()["sha256"] == hashlib.sha256(raw).hexdigest(),
                        "FIXTURE_UPLOAD_CHANGED",
                    )
                response = client.post(
                    "/v1/contracts/" + case["assets"]["contract"] + "/approve",
                    json={"expected_sha256": hashlib.sha256(contract).hexdigest(), "confirm": True},
                )
                require(response.status_code == 200, "SYNTHETIC_CONTRACT_APPROVAL_FAILED")
                request = {k + "_id": value for k, value in case["assets"].items()}
                request["idempotency_key"] = case["idempotency_key"]
                response = client.post("/v1/jobs", json=request)
                require(response.status_code == 202, "ORIGINAL_ENQUEUE_FAILED")
                case["job_id"] = response.json()["job_id"]
                persist()
                deadline = time.monotonic() + 90
                while True:
                    response = client.get("/v1/jobs/" + case["job_id"])
                    require(response.status_code == 200, "JOB_READBACK_FAILED")
                    value = response.json()
                    if value["state"] in ("NEEDS_REVIEW", "FAILED_INFRA", "CANCELLED"):
                        break
                    require(time.monotonic() < deadline, "ORIGINAL_DEADLINE")
                    time.sleep(1)
                case["result"] = value
                persist()  # Preserve failures before any acceptance assertion.
                require(
                    value["state"] == "NEEDS_REVIEW" and value["outcome"] == expected,
                    "SOURCE_FAILURE_OUTCOME_CHANGED",
                )
                require(
                    value["report"]["semantic"] is None
                    and value["report"]["source"]["report"]["result"]["blocking_occurrences"]
                    == blocked,
                    "SOURCE_DIAGNOSIS_CHANGED",
                )
                require(
                    "failure_log_preview" not in value["report"]["worker"]
                    and value["report"]["worker"]["cleanup"] == "confirmed",
                    "RAW_LOG_OR_CLEANUP",
                )
                summary = client.get("/v1/jobs/" + case["job_id"] + "/summary")
                require(
                    summary.status_code == 200 and summary.json()["finding_count"] is None,
                    "UNVERIFIED_OUTPUT_FINDING_CLAIMED",
                )
                page = client.get("/jobs/" + case["job_id"])
                require(page.status_code == 200, "FAILURE_PAGE_FAILED")
                case["accepted"] = True
                persist()
                print(
                    json.dumps({"case": name, "outcome": expected, "cleanup": "confirmed"}),
                    flush=True,
                )
            record["completed"] = True
        finally:
            live.admission(False)
            record["admission_closed"] = True
            record["finished_at"] = datetime.now(UTC).isoformat()
            persist()
        print(
            json.dumps(
                {
                    "cases_passed": len(record["cases"]),
                    "provider_calls": 0,
                    "workspace": "retained_temporarily_for_real_repair_check",
                }
            )
        )


if __name__ == "__main__":
    main()
