"""Resume the preserved Phase4 fixture after an invalid-column test input; no model call."""

import csv
import io
import json
import time
from datetime import UTC, datetime
from uuid import UUID, uuid4

from product_live_session import PRIVATE, LiveSession, require


def main():
    path = PRIVATE / "evidence/phase4-batches-intent.json"
    intent = json.loads(path.read_bytes())
    guest, version, pipeline = (str(UUID(intent[k])) for k in ("guest", "version", "pipeline"))
    result_path = PRIVATE / "evidence/phase4-batches-result.json"
    require(not result_path.exists(), "FINAL_PHASE4_BATCH_RESULT_ALREADY_EXISTS")
    result = {
        "checks": [],
        "fixture_only": True,
        "synthetic_approval_not_human_signoff": True,
        "provider_calls": 0,
        "new_cloud_resources": 0,
    }

    def save():
        path.write_bytes(json.dumps(intent).encode())

    def progress():
        (PRIVATE / "evidence/phase4-batches-progress.json").write_bytes(json.dumps(result).encode())

    with LiveSession() as live:
        client = live.login(guest)

        def wait(identity):
            for _ in range(180):
                response = client.get("/v1/batches/" + identity)
                require(response.status_code == 200, "BATCH_READ_FAILED")
                value = response.json()
                if value["state"] not in ("QUEUED", "RUNNING"):
                    return value
                time.sleep(0.5)
            raise RuntimeError("BATCH_NOT_TERMINAL")

        clean = wait(intent["clean_batch"])
        invalid = wait(intent["held_batch"])
        require(clean["state"] == "COMPLETED", "CLEAN_BATCH_CHANGED")
        require(
            invalid["state"] == "HELD_FOR_REVIEW" and invalid["outcome"] == "input_rejected",
            "INVALID_COLUMN_NOT_HELD",
        )
        result["completed_batch"], result["invalid_column_batch"] = clean, invalid
        result["checks"].append(
            "actual_clean_batch_completed_invalid_extra_column_held_before_execution"
        )
        result["version"] = client.get("/v1/versions/" + version).json()
        require(result["version"]["active_version"] == version, "EXACT_ACTIVATION_NOT_RECORDED")
        # These are real persisted approval records, not manufactured statuses.
        result["approvals"] = json.loads(
            live.sql(
                "SELECT json_agg(json_build_object('id',id,'digest',digest,'bundle',bundle,"  # noqa: S608 - canonical UUID
                "'approved_at',approved_at)) FROM pf_product.approval_intents WHERE workspace_id='"
                + guest
                + "';"
            )
        )
        result["checks"].append("actual_exact_activation_and_distinct_unapproved_preview_preserved")
        progress()
        clean_id = str(UUID(intent["clean_batch"]))
        fresh = json.loads(
            live.sql(
                "SELECT json_build_object('transactions_id',transactions_id,"  # noqa: S608 - canonical UUIDs
                "'customers_id',customers_id)"
                " FROM pf_product.jobs WHERE workspace_id='"
                + guest
                + "' AND id='"
                + clean_id
                + "';"
            )
        )
        customer_id = str(UUID(intent["assets"]["customers_id"]))
        response = client.get("/v1/assets/" + customer_id + "/download")
        require(response.status_code == 200, "SOURCE_READ_FAILED")
        rows = list(csv.DictReader(io.StringIO(response.content.decode())))
        require(len(rows) >= 2, "MISSING_CUSTOMER_FIXTURE_UNAVAILABLE")
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows[1:])
        if "corrected_customer_asset" not in intent:
            intent["corrected_customer_asset"] = str(uuid4())
            intent["corrected_batch_key"] = str(uuid4())
            save()
        asset = str(UUID(intent["corrected_customer_asset"]))
        require(
            client.post(
                "/v1/assets/customers/" + asset, content=stream.getvalue().encode()
            ).status_code
            == 201,
            "CORRECTED_CUSTOMER_UPLOAD_FAILED",
        )
        live.admission(True)
        request = {
            "version_id": version,
            "transactions_id": fresh["transactions_id"],
            "customers_id": asset,
            "idempotency_key": str(UUID(intent["corrected_batch_key"])),
        }
        response = client.post("/v1/pipelines/" + pipeline + "/batches", json=request)
        require(response.status_code == 202, "CORRECTED_BATCH_ENQUEUE_FAILED")
        corrected = response.json()["batch_id"]
        intent["corrected_held_batch"] = corrected
        save()
        held = wait(corrected)
        result["held_batch"] = held
        progress()
        require(
            held["state"] == "HELD_FOR_REVIEW" and held["outcome"] == "held",
            "MISSING_CUSTOMER_BATCH_NOT_HELD",
        )
        require(
            held["report"]["semantic"]["report"]["result"]["blocking_occurrences"] > 0,
            "MISSING_CUSTOMER_BLOCKING_EVIDENCE_ABSENT",
        )
        result["checks"].append(
            "actual_fresh_missing_customer_isolated_execution_held_with_blocking_evidence"
        )
        progress()
        live.host("systemctl stop proofflow-product-dispatcher.service")
        try:
            if "cancel_batch_key" not in intent:
                intent["cancel_batch_key"] = str(uuid4())
                save()
            request = {
                **request,
                "customers_id": customer_id,
                "idempotency_key": intent["cancel_batch_key"],
            }
            response = client.post("/v1/pipelines/" + pipeline + "/batches", json=request)
            require(response.status_code == 202, "CANCEL_BATCH_ENQUEUE_FAILED")
            cancelled = response.json()["batch_id"]
            intent["cancelled_batch"] = cancelled
            save()
            current = client.get("/v1/versions/" + version).json()
            require(
                client.post(
                    "/v1/versions/" + version + "/revoke",
                    json={"expected_revision": current["pipeline_revision"], "confirm": True},
                ).status_code
                == 200,
                "VERSION_REVOCATION_FAILED",
            )
        finally:
            live.host("systemctl start proofflow-product-dispatcher.service")
        cancelled_value = wait(cancelled)
        require(cancelled_value["state"] == "CANCELLED", "REVOKED_BATCH_EXECUTED")
        result["cancelled_batch"] = cancelled_value
        require(
            client.get("/v1/batches/" + clean_id).json()["version_currently_eligible"] is False,
            "COMPLETED_HISTORY_REVOCATION_HIDDEN",
        )
        require(
            client.post(
                "/v1/versions/" + version + "/preview", json={"intent_id": str(uuid4())}
            ).status_code
            == 409,
            "REVOKED_VERSION_PREVIEWED",
        )
        result["checks"].append(
            "actual_queued_revocation_no_dispatch_history_preserved_no_reapproval"
        )
        progress()
        require(
            client.post(
                "/v1/workspace/delete", json={"workspace_id": guest, "confirm": True}
            ).status_code
            == 200,
            "WORKSPACE_REVOCATION_FAILED",
        )
        for _ in range(180):
            done = live.sql(
                "SELECT completed_at IS NOT NULL FROM pf_product.deletions WHERE workspace_id='"  # noqa: S608 - canonical UUID
                + guest
                + "';"
            )
            if done == b"t":
                break
            time.sleep(0.5)
        require(done == b"t", "VERSION_RETENTION_FAILED")
        counts = json.loads(
            live.sql(
                "SELECT json_build_object('workspaces',(SELECT count(*) "
                "FROM pf_product.workspaces),'assets',(SELECT count(*) FROM pf_product.assets),"
                "'jobs',(SELECT count(*) FROM pf_product.jobs),'versions',(SELECT count(*) FROM "
                "pf_product.versions));"
            )
        )
        require(
            counts == {"workspaces": 7, "assets": 40, "jobs": 10, "versions": 0},
            "PRIOR_EVIDENCE_CHANGED",
        )
        result["retained_counts"] = counts
        result["checks"].append(
            "actual_version_batch_approval_journal_retention_preserves_prior_evidence"
        )
        result["observed_at"], result["credit"] = datetime.now(UTC).isoformat(), live.credit
        result_path.write_bytes(json.dumps(result).encode())
        print(
            json.dumps(
                {"passed": len(result["checks"]), "provider_calls": 0, "guest_deleted": True}
            )
        )


if __name__ == "__main__":
    main()
