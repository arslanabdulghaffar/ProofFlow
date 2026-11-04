"""Actual private worker approval/batch probe; synthetic operator, no inference or GitHub write."""

import csv
import hashlib
import io
import json
import time
import zipfile
from datetime import UTC, datetime
from uuid import uuid4

from product_live_session import PRIVATE, LiveSession, require


def main():
    intent_path = PRIVATE / "evidence/phase4-batches-intent.json"
    require(not intent_path.exists(), "RECONCILE_EXISTING_PHASE4_INTENT")
    guest = str(uuid4())
    intent = {"guest": guest, "synthetic_automated_approval_not_human_signoff": True}

    def save():
        intent_path.write_bytes(json.dumps(intent).encode())

    save()
    result = {"checks": [], "provider_calls": 0, "new_cloud_resources": 0}
    with zipfile.ZipFile(PRIVATE / "evidence/phase3-candidate-bundle.zip") as z:
        sources = {
            k: z.read(v)
            for k, v in {
                "pipeline": "candidate/pipeline.py",
                "contract": "input/contract.json",
                "transactions": "input/transactions.csv",
                "customers": "input/customers.csv",
            }.items()
        }
    with LiveSession() as live:
        baseline = json.loads(
            live.sql(
                "SELECT json_build_object('workspaces',(SELECT count(*) "
                "FROM pf_product.workspaces),'assets',(SELECT count(*) FROM pf_product.assets),"
                "'jobs',(SELECT count(*) FROM pf_product.jobs),'versions',(SELECT count(*) FROM "
                "pf_product.versions));"
            )
        )
        require(
            live.sql("SELECT bool_and(blocked) FROM pf_budget.accounts;", "proofflow_budget")
            == b"t",
            "PAID_ADMISSION_NOT_CLOSED",
        )
        live.sql(
            "SET ROLE pf_product_provisioner; SELECT pf_product.create_workspace('"
            + guest
            + "','guest',clock_timestamp()+interval '2 hours');"
        )
        client = live.login(guest)

        def upload(kind, raw):
            identity = str(uuid4())
            response = client.post("/v1/assets/" + kind + "/" + identity, content=raw)
            require(response.status_code == 201, "PHASE4_UPLOAD_FAILED")
            return identity

        ids = {k + "_id": upload(k, v) for k, v in sources.items()}
        intent["assets"] = ids
        save()
        require(
            client.post(
                "/v1/contracts/" + ids["contract_id"] + "/approve",
                json={
                    "expected_sha256": hashlib.sha256(sources["contract"]).hexdigest(),
                    "confirm": True,
                },
            ).status_code
            == 200,
            "EXACT_CONTRACT_FAILED",
        )
        live.admission(True)
        response = client.post("/v1/jobs", json={**ids, "idempotency_key": str(uuid4())})
        require(response.status_code == 202, "ORIGINAL_ENQUEUE_FAILED")
        original = response.json()["job_id"]
        intent["original"] = original
        save()

        def wait(path, terminals):
            for _ in range(180):
                response = client.get(path)
                require(response.status_code == 200, "STATUS_READ_FAILED")
                value = response.json()
                if value["state"] in terminals:
                    return value
                time.sleep(0.5)
            raise RuntimeError("LIVE_JOB_WAIT_EXCEEDED")

        first = wait("/v1/jobs/" + original, {"NEEDS_REVIEW", "FAILED_INFRA", "CANCELLED"})
        require(first["outcome"] == "match", "VERIFIED_SOURCE_ORIGINAL_CHANGED")
        response = client.post(
            "/v1/repairs", json={"parent_id": original, "idempotency_key": str(uuid4())}
        )
        require(response.status_code == 202, "UNCHANGED_CHECK_ENQUEUE_FAILED")
        version = response.json()["repair_id"]
        intent["version"] = version
        save()
        repair = wait(
            "/v1/repairs/" + version,
            {"AWAITING_APPROVAL", "NEEDS_REVIEW", "FAILED_INFRA", "CANCELLED"},
        )
        require(
            repair["state"] == "AWAITING_APPROVAL" and repair["calls"] == 0, "FRESH_CANARIES_FAILED"
        )
        response = client.post(
            "/v1/repairs/" + version + "/version", json={"prepare_verified_source": True}
        )
        require(response.status_code == 200, "VERSION_PREPARE_FAILED")
        pipeline = response.json()["pipeline_id"]
        intent["pipeline"] = pipeline
        save()

        def preview():
            response = client.post(
                "/v1/versions/" + version + "/preview", json={"intent_id": str(uuid4())}
            )
            require(response.status_code == 200, "EXACT_PREVIEW_FAILED")
            return response.json()

        a, b = preview(), preview()

        def approval(p):
            return {
                "intent_id": p["intent_id"],
                "bundle_sha256": p["bundle_sha256"],
                "confirm": True,
            }

        path = "/v1/versions/" + version + "/approve"
        require(
            client.post(path, json={**approval(a), "bundle_sha256": "0" * 64}).status_code == 409,
            "ALTERED_BUNDLE_APPROVED",
        )
        require(client.post(path, json=approval(a)).status_code == 200, "EXACT_ACTIVATION_FAILED")
        duplicate = client.post(path, json=approval(a))
        require(
            duplicate.status_code == 200 and duplicate.json()["already_applied"],
            "APPROVAL_REPLAY_CHANGED",
        )
        require(client.post(path, json=approval(b)).status_code == 409, "STALE_PREVIEW_APPROVED")
        result["checks"].append(
            "actual_exact_hash_actor_intent_activation_idempotency_stale_preview"
        )
        result["approval_preview"] = a
        tx = list(csv.DictReader(io.StringIO(sources["transactions"].decode())))
        for row in tx:
            row["transaction_id"] += "-fresh"
            row["amount"] = "14.63" if row["currency"] == "USD" else "27"

        def csv_bytes(rows):
            stream = io.StringIO(newline="")
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
            return stream.getvalue().encode()

        fresh = upload("transactions", csv_bytes(tx))

        def enqueue(customers, key=None):
            request = {
                "version_id": version,
                "transactions_id": fresh,
                "customers_id": customers,
                "idempotency_key": key or str(uuid4()),
            }
            response = client.post("/v1/pipelines/" + pipeline + "/batches", json=request)
            require(response.status_code == 202, "FRESH_BATCH_ENQUEUE_FAILED")
            return response.json()["batch_id"], request

        clean, request = enqueue(ids["customers_id"])
        intent["clean_batch"] = clean
        save()
        value = wait(
            "/v1/batches/" + clean, {"COMPLETED", "HELD_FOR_REVIEW", "FAILED_INFRA", "CANCELLED"}
        )
        require(
            value["state"] == "COMPLETED" and value["version_id"] == version,
            "FRESH_BATCH_NOT_COMPLETED",
        )
        repeated = client.post("/v1/pipelines/" + pipeline + "/batches", json=request)
        require(
            repeated.status_code == 202 and repeated.json()["batch_id"] == clean, "BATCH_DUPLICATED"
        )
        result["completed_batch"] = value
        result["checks"].append(
            "actual_new_input_isolated_execution_verification_completed_exact_version_retry"
        )
        customers = list(csv.DictReader(io.StringIO(sources["customers"].decode())))
        customers = customers[1:]
        held, request = enqueue(upload("customers", csv_bytes(customers)))
        intent["held_batch"] = held
        save()
        value = wait(
            "/v1/batches/" + held, {"COMPLETED", "HELD_FOR_REVIEW", "FAILED_INFRA", "CANCELLED"}
        )
        require(
            value["state"] == "HELD_FOR_REVIEW" and value["outcome"] == "held",
            "INVALID_SOURCE_BATCH_COMPLETED",
        )
        result["held_batch"] = value
        result["checks"].append(
            "actual_missing_customer_holds_batch_preserves_all_occurrences"
        )
        # Stop only the trusted queue consumer so revocation can deterministically
        # race a queued batch. No fake status or execution receipt is written.
        live.host("systemctl stop proofflow-product-dispatcher.service")
        try:
            cancelled, _ = enqueue(ids["customers_id"])
            intent["cancelled_batch"] = cancelled
            save()
            current = client.get("/v1/versions/" + version).json()
            response = client.post(
                "/v1/versions/" + version + "/revoke",
                json={"expected_revision": current["pipeline_revision"], "confirm": True},
            )
            require(response.status_code == 200, "VERSION_REVOCATION_FAILED")
        finally:
            live.host("systemctl start proofflow-product-dispatcher.service")
        value = wait(
            "/v1/batches/" + cancelled,
            {"COMPLETED", "HELD_FOR_REVIEW", "FAILED_INFRA", "CANCELLED"},
        )
        require(value["state"] == "CANCELLED", "REVOKED_QUEUE_EXECUTED")
        current = client.get("/v1/batches/" + clean).json()
        require(
            current["state"] == "COMPLETED" and not current["version_currently_eligible"],
            "HISTORY_REWRITTEN_OR_REVOCATION_HIDDEN",
        )
        require(
            client.post(
                "/v1/versions/" + version + "/preview", json={"intent_id": str(uuid4())}
            ).status_code
            == 409,
            "REVOKED_VERSION_PREVIEWED",
        )
        result["checks"].append(
            "actual_revoked_queue_cancelled_completed_history_preserved_and_marked_affected"
        )
        require(
            client.post(
                "/v1/workspace/delete", json={"workspace_id": guest, "confirm": True}
            ).status_code
            == 200,
            "VERSION_GUEST_REVOCATION_FAILED",
        )
        for _ in range(180):
            done = live.sql(
                "SELECT completed_at IS NOT NULL FROM pf_product.deletions WHERE workspace_id='"  # noqa: S608 - generated UUID
                + guest
                + "';"
            )
            if done == b"t":
                break
            time.sleep(0.5)
        require(done == b"t", "VERSION_GUEST_RETENTION_FAILED")
        after = json.loads(
            live.sql(
                "SELECT json_build_object('workspaces',(SELECT count(*) "
                "FROM pf_product.workspaces),'assets',(SELECT count(*) FROM pf_product.assets),"
                "'jobs',(SELECT count(*) FROM pf_product.jobs),'versions',(SELECT count(*) FROM "
                "pf_product.versions));"
            )
        )
        require(after == baseline, "EXISTING_EVIDENCE_CHANGED")
        result["checks"].append("actual_version_batch_intent_journal_erasure_preserves_existing")
        result["retained_counts"] = after
        result["credit"] = live.credit
        result["observed_at"] = datetime.now(UTC).isoformat()
        (PRIVATE / "evidence/phase4-batches-result.json").write_bytes(json.dumps(result).encode())
        print(
            json.dumps(
                {"passed": len(result["checks"]), "provider_calls": 0, "guest_deleted": True}
            )
        )


if __name__ == "__main__":
    main()
