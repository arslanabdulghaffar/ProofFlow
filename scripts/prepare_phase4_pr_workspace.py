"""Fresh synthetic proof after workspace expiry; no PR preview, approval or GitHub write."""

import argparse
import hashlib
import json
import time
import zipfile
from datetime import UTC, datetime
from uuid import UUID, uuid4

from product_live_session import PRIVATE, LiveSession, require
from refresh_phase4_pr_preview import SOURCE


def wait_terminal(client, path, terminals):
    for _ in range(240):
        response = client.get(path)
        require(response.status_code == 200, "FRESH_PROOF_STATUS_UNAVAILABLE")
        result = response.json()
        if result["state"] in terminals:
            return result
        time.sleep(1)
    raise RuntimeError("FRESH_PROOF_WAIT_EXCEEDED")


def main(resume_original=False, retry_cancelled=False):
    require(not retry_cancelled or resume_original, "RESUME_REQUIRED_FOR_CANCELLED_RETRY")
    require(resume_original or not SOURCE.exists(), "RECONCILE_EXISTING_WORKSPACE_PREPARATION")
    prior = json.loads((PRIVATE / "evidence/phase4-pr-preview-intent.json").read_bytes())
    expected = prior["pr"]["preview"]["candidate_source"].encode()
    # Read retained bytes only. Never import or execute the candidate locally.
    with zipfile.ZipFile(PRIVATE / "evidence/phase3-candidate-bundle.zip") as bundle:
        sources = {kind: bundle.read(name) for kind, name in {
            "pipeline": "candidate/pipeline.py", "contract": "input/contract.json",
            "transactions": "input/transactions.csv", "customers": "input/customers.csv",
        }.items()}
    require(sources["pipeline"] == expected, "RETAINED_CANDIDATE_CHANGED")
    record = json.loads(SOURCE.read_bytes()) if resume_original else {
        "workspace": str(uuid4()), "previous_workspace": prior["workspace"],
        "candidate_sha256": hashlib.sha256(expected).hexdigest(),
        "status": "preparing", "external_approval": False,
        "synthetic_activation_not_human_signoff": True,
    }
    if resume_original:
        require(record["status"] == "preparing" and "original" in record
                and "version" not in record and "assets" in record
                and record["candidate_sha256"] == hashlib.sha256(expected).hexdigest(),
                "RESUME_ONLY_RECORDED_ORIGINAL")
        record["workspace"] = str(UUID(record["workspace"]))
        record["original"] = str(UUID(record["original"]))
    else:
        with SOURCE.open("x", encoding="utf-8") as output:
            json.dump(record, output)

    def save():
        SOURCE.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

    with LiveSession() as live:
        require(live.sql("SELECT bool_and(blocked) FROM pf_budget.accounts;",
                         "proofflow_budget") == b"t", "INFERENCE_MUST_REMAIN_BLOCKED")
        require(live.sql("SELECT count(*) FROM pf_product.pr_writes;") == b"0",
                "REVIEW_EXISTING_EXTERNAL_WRITES")
        baseline = live.sql("SELECT count(*) FROM pf_budget.reservations;", "proofflow_budget")
        if not resume_original:
            live.sql("SET ROLE pf_product_provisioner; SELECT pf_product.create_workspace('"
                     + record["workspace"] + "','operator',clock_timestamp()+interval '23 hours');")
        client = live.login(record["workspace"])
        ids = record["assets"] if resume_original else {}
        if not resume_original:
            for kind, raw in sources.items():
                identity = str(uuid4())
                require(client.post("/v1/assets/" + kind + "/" + identity,
                                    content=raw).status_code == 201, "FRESH_UPLOAD_FAILED")
                ids[kind + "_id"] = identity
                record["assets"] = ids
                save()
            require(client.post("/v1/contracts/" + ids["contract_id"] + "/approve", json={
                "expected_sha256": hashlib.sha256(sources["contract"]).hexdigest(), "confirm": True,
            }).status_code == 200, "SYNTHETIC_CONTRACT_APPROVAL_FAILED")

        if retry_cancelled:
            require(live.sql(
                "SELECT state='CANCELLED' AND lease_owner IS NULL AND "  # noqa: S608 - parsed UUID
                "(worker_receipt->>'cleanup'='confirmed' OR "
                "worker_receipt='{" + '"not_dispatched":true' + "}'::jsonb) "
                "FROM pf_product.jobs WHERE id='" + record["original"] + "';"
            ) == b"t", "CANCELLED_CLEANUP_REQUIRED")
            require("cancelled_original" not in record, "CANCELLED_RETRY_ALREADY_USED")
            record["cancelled_original"] = {
                "id": record["original"], "result": record["original_result"],
                "cleanup_confirmed_by_database": True,
            }
            save()

        live.admission(True)
        if not resume_original or retry_cancelled:
            record["original_request"] = {**ids, "idempotency_key": str(uuid4())}
            save()
            response = client.post("/v1/jobs", json=record["original_request"])
            require(response.status_code == 202, "FRESH_ORIGINAL_NOT_ACCEPTED")
            record["original"] = response.json()["job_id"]
            save()
        original = wait_terminal(client, "/v1/jobs/" + record["original"], {
            "NEEDS_REVIEW", "FAILED_INFRA", "CANCELLED",
        })
        record["original_result"] = original
        save()
        require(original["outcome"] == "match" and original["state"] == "NEEDS_REVIEW",
                "FRESH_ORIGINAL_NOT_MATCHED")
        response = client.post("/v1/repairs", json={
            "parent_id": record["original"], "idempotency_key": str(uuid4()),
        })
        require(response.status_code == 202, "FRESH_PROOF_NOT_ACCEPTED")
        record["version"] = response.json()["repair_id"]
        save()
        proof = wait_terminal(client, "/v1/repairs/" + record["version"], {
            "AWAITING_APPROVAL", "NEEDS_REVIEW", "FAILED_INFRA", "CANCELLED",
        })
        record["proof"] = proof
        save()
        require(proof["state"] == "AWAITING_APPROVAL" and proof["calls"] == 0
                and proof["mode"] == "original" and proof["reserved_micro"] == 0
                and len(proof["checks"]) == 3
                and all(c["cleanup_confirmed"] and c["comparison"] == "match"
                        for c in proof["checks"]), "FRESH_ISOLATED_PROOF_FAILED")
        version = record["version"]
        require(client.post("/v1/repairs/" + version + "/version", json={
            "prepare_verified_source": True,
        }).status_code == 200, "FRESH_VERSION_PREPARATION_FAILED")
        response = client.post("/v1/versions/" + version + "/preview", json={
            "intent_id": str(uuid4()),
        })
        require(response.status_code == 200, "SYNTHETIC_ACTIVATION_PREVIEW_FAILED")
        record["activation"] = response.json()
        save()
        require(client.post("/v1/versions/" + version + "/approve", json={
            "intent_id": record["activation"]["intent_id"],
            "bundle_sha256": record["activation"]["bundle_sha256"], "confirm": True,
        }).status_code == 200, "SYNTHETIC_ACTIVATION_FAILED")
        live.admission(False)
        require(live.sql("SELECT count(*) FROM pf_budget.reservations;", "proofflow_budget")
                == baseline, "UNEXPECTED_INFERENCE_RESERVATION")
        require(live.sql("SELECT count(*) FROM pf_product.pr_writes;") == b"0",
                "UNAPPROVED_EXTERNAL_WRITE")
        record["workspace_expires_at"] = live.sql(
            "SELECT expires_at FROM pf_product.workspaces WHERE id='"  # noqa: S608 - generated UUID
            + record["workspace"] + "';"
        ).decode()
        require(client.post("/v1/logout").status_code == 204, "PREPARATION_LOGOUT_FAILED")
        record.update(status="ready", observed_at=datetime.now(UTC).isoformat(), credit=live.credit)
        save()
        print(json.dumps({k: record[k] for k in (
            "status", "workspace", "version", "workspace_expires_at", "credit",
        )}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume-original", action="store_true")
    parser.add_argument("--retry-cancelled", action="store_true")
    args = parser.parse_args()
    try:
        main(args.resume_original, args.retry_cancelled)
    except Exception:
        raise SystemExit("FRESH_WORKSPACE_STOPPED_RECONCILE_PRIVATE_RECORD") from None
