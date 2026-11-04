"""Real disposable PostgreSQL reservation/approval/lease tests. No cloud charges."""

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from scripts.check_budget_postgres import require
from tests.integration.product_database_fixture import database

RESERVE = "SELECT pf_product.reserve_upload(:'w',:'s',:'c',:'a',:'k',:'d',:'n');"
COMPLETE = "SELECT pf_product.complete_upload(:'w',:'s',:'c',:'a',:'k',:'d',:'n');"
APPROVE = "SELECT pf_product.approve_contract(:'w',:'s',:'c',:'a',:'d');"
ENQUEUE = "SELECT pf_product.enqueue_original(:'w',:'s',:'c',:'j',:'i',:'p',:'t',:'u',:'a');"
CLAIM = "SELECT pf_product.claim_original(:'o');"
BEAT = "SELECT pf_product.heartbeat_original(:'w',:'j',:'o',:'g');"
BEGIN = "SELECT pf_product.begin_original(:'w',:'j',:'o',:'g',:'e',:'m');"
FAIL = "SELECT pf_product.fail_original(:'w',:'j',:'o',:'g',:'termination');"
COLLECT = "SELECT pf_product.original_collected(:'w',:'j',:'o',:'g',:'e',:'receipt');"
FINISH = "SELECT pf_product.finish_original(:'w',:'j',:'o',:'g',:'result');"


def main():
    checks = []
    with database() as db:
        one, two = db.workspace(), db.workspace()
        pending = {**one, "a": str(uuid4()), "k": "pipeline", "d": "a" * 64, "n": 10}
        db.expect(COMPLETE, "UPLOAD_RESERVATION_REQUIRED", **pending)
        require(db.sql(RESERVE, **pending) == "t", "Reservation missing")
        require(db.sql(RESERVE, **pending) == "t", "Retry changed reservation")
        db.expect(RESERVE, "ASSET_IDEMPOTENCY_CONFLICT", **{**pending, "n": 11})
        require(db.sql(COMPLETE, **pending) == "t", "Publication missing")
        require(db.sql(COMPLETE, **pending) == "f", "Publication retry changed")
        require(db.sql(RESERVE, **pending) == "f", "Existing publication not recognized")
        db.expect(RESERVE, "ACCESS_DENIED", **{**pending, "s": two["s"]})
        db.expect("SELECT pf_product.register_asset(NULL,NULL,NULL,NULL,NULL,NULL,NULL);",
                  "permission denied")
        checks.append("reserved_before_publish_scoped_idempotency_no_direct_register")

        quota = db.workspace()
        db.sql("SELECT pf_product.reserve_upload(:'w',:'s',:'c',"
               "('00000000-0000-0000-0000-'||lpad(i::text,12,'0'))::uuid,"
               "'pipeline',repeat('a',64),1) FROM generate_series(1,63) i;", **quota)
        def race(_):
            try:
                db.sql(RESERVE, **{**pending, **quota, "a": str(uuid4())})
                return True
            except subprocess.CalledProcessError as error:
                require("ASSET_QUOTA" in error.stderr, "Unexpected reservation race")
                return False
        with ThreadPoolExecutor(max_workers=8) as pool:
            require(sum(pool.map(race, range(8))) == 1, "Concurrent reservation quota exceeded")
        checks.append("uncertain_reservations_consume_quota_atomic_eight_way_race")

        assets = {kind: db.asset(one, kind) for kind in
                  ("pipeline", "transactions", "customers", "contract")}
        contract = assets["contract"]
        db.expect(APPROVE, "EXACT_CONTRACT_REQUIRED", **{**contract, "d": "0" * 64})
        db.expect(APPROVE, "ACCESS_DENIED", **{**contract, "c": two["c"]})
        require(db.sql(APPROVE, **contract) == "t", "Exact approval missing")
        require(db.sql(APPROVE, **contract) == "f", "Approval retry changed")
        job = {**one, "j": str(uuid4()), "i": str(uuid4()), "p": assets["pipeline"]["a"],
               "t": assets["transactions"]["a"], "u": assets["customers"]["a"], "a": contract["a"]}
        db.expect(ENQUEUE, "ADMISSION_CLOSED", **job)
        db.sql("SELECT pf_product.configure_execution(repeat('b',64),repeat('c',64),true);",
               "provisioner")
        require(db.sql(ENQUEUE, **job) == job["j"], "Enqueue missing")
        require(db.sql(ENQUEUE, **{**job, "j": str(uuid4())}) == job["j"], "Scoped retry changed")
        db.expect(ENQUEUE, "JOB_IDEMPOTENCY_CONFLICT", **{**job, "p": str(uuid4())})
        db.expect(ENQUEUE, "JOB_ASSETS_INVALID", **{**job, **two, "i": str(uuid4())})
        for statement in (CLAIM, "SELECT * FROM pf_product.jobs;", "SET ROLE pf_product_owner;"):
            db.expect(statement, "permission denied", o=str(uuid4()))
        db.expect(APPROVE, "permission denied", "dispatcher", **contract)
        checks.append("exact_contract_approval_scoped_job_idempotency_role_separation")

        owners = [str(uuid4()) for _ in range(8)]
        with ThreadPoolExecutor(max_workers=8) as pool:
            claimed = list(pool.map(
                lambda owner: (owner, db.sql(CLAIM, "dispatcher", o=owner)), owners))
        claimed = [(owner, json.loads(value)) for owner, value in claimed if value]
        require(len(claimed) == 1, "Single worker admitted more than one lease")
        owner, row = claimed[0]
        lease = {**job, "o": owner, "g": row["generation"], "e": str(uuid4()), "m": "d" * 64}
        db.sql(BEAT, "dispatcher", **lease)
        db.expect(BEAT, "STALE_JOB_LEASE", "dispatcher", **{**lease, "o": str(uuid4())})
        db.sql(BEGIN, "dispatcher", **lease)
        db.expect(BEGIN, "EXECUTION_INTENT_CONFLICT", "dispatcher", **lease)
        db.sql("UPDATE pf_product.jobs SET lease_until=clock_timestamp()-interval '1 second' "
               "WHERE workspace_id=:'w' AND id=:'j';", "admin", **job)
        replacement = str(uuid4())
        recovered = json.loads(db.sql(CLAIM, "dispatcher", o=replacement))
        require(recovered["state"] == "RECONCILING" and recovered["execution_id"] == lease["e"],
                "Expired execution was silently replaced")
        new_lease = {**lease, "o": replacement, "g": recovered["generation"]}
        db.expect(BEAT, "STALE_JOB_LEASE", "dispatcher", **lease)
        db.expect(BEGIN, "EXECUTION_INTENT_CONFLICT", "dispatcher", **new_lease)
        db.expect(FAIL, "CLEANUP_REQUIRED", "dispatcher", **new_lease, termination='{}')
        termination = {"execution": lease["e"].replace("-", ""),
                       "job": lease["j"].replace("-", ""), "generation": lease["g"],
                       "manifest": lease["m"], "cleanup": "confirmed"}
        db.sql(FAIL, "dispatcher", **new_lease, termination=json.dumps(termination))
        require(db.sql("SELECT worker_receipt=:'r'::jsonb AND worker_receipt_sha256="
            "encode(sha256(convert_to(worker_receipt::text,'UTF8')),'hex') "
            "FROM pf_product.jobs WHERE workspace_id=:'w' AND id=:'j';", "admin",
            **new_lease, r=json.dumps(termination)) == "t", "Terminal cleanup evidence lost")
        checks.append("single_worker_atomic_claim_generation_fence_recovery_cleanup_gate")
        events_sql = "SELECT pf_product.read_job_events(:'w',:'s',:'j',:'after');"
        replay = json.loads(db.sql(events_sql, **job, after=0))
        require([e["sequence"] for e in replay] == [str(i+1) for i in range(len(replay))],
                "Event replay has gaps or unsafe numeric wire IDs")
        require(replay[-1]["state"] == "FAILED_INFRA", "Missing committed terminal event")
        require(json.loads(db.sql(events_sql, **job, after=2)) == replay[2:],
                "Resume duplicated or skipped committed events")
        db.expect(events_sql, "INVALID_EVENT_CURSOR", **job, after=len(replay)+1)
        db.expect(events_sql, "ACCESS_DENIED", **{**job, "s": two["s"]}, after=0)
        db.expect(events_sql, "permission denied", "dispatcher", **job, after=0)
        checks.append("bounded_authorized_event_replay_cursor_and_role_isolation")

        job = {**job, "j": str(uuid4()), "i": str(uuid4())}
        db.sql(ENQUEUE, **job)
        owner = str(uuid4())
        row = json.loads(db.sql(CLAIM, "dispatcher", o=owner))
        lease = {**job, "o": owner, "g": row["generation"], "e": str(uuid4()), "m": "d" * 64}
        db.sql(BEGIN, "dispatcher", **lease)
        receipt = {"execution": lease["e"].replace("-", ""), "job": job["j"].replace("-", ""),
                   "generation": lease["g"], "manifest": lease["m"], "collected": True,
                   "cleanup": "confirmed", "runtime_client_exit_code": 0, "unit_result": "success",
                   "files": [{"name": "ledger.jsonl", "sha256": "e" * 64},
                             {"name": "unresolved.jsonl", "sha256": "f" * 64}]}
        db.expect(COLLECT, "COLLECTED_EXECUTION_MISMATCH", "dispatcher",
                  **lease, receipt=json.dumps({**receipt, "cleanup": "unknown"}))
        db.sql(COLLECT, "dispatcher", **lease, receipt=json.dumps(receipt))
        binding = {"execution": receipt["execution"], "job": receipt["job"],
                   "generation": lease["g"],
                   "purpose": "original", "manifest_sha256": lease["m"],
                   "runtime_sha256": "b" * 64, "verifier_rootfs": "c" * 64,
                   "contract_sha256": "1" * 64}
        binding.update({("contract_raw_sha256" if k == "contract" else k + "_sha256"): v["d"]
                        for k, v in assets.items()})
        semantic = {"operation": "verify", "comparison": "match", "blocking_occurrences": 2,
                    "finding_count": 0, "findings": [], "contract_sha256": "1" * 64,
                    "transactions_sha256": assets["transactions"]["d"],
                    "customers_sha256": assets["customers"]["d"],
                    "output_hashes": {f["name"]: f["sha256"] for f in receipt["files"]}}
        result = {"intent": binding, "worker": receipt, "semantic": {"cleanup_confirmed": True,
                  "rootfs_sha256": "c" * 64, "report": {"status": "processed",
                  "version": "proofflow-verifier-v1", "result": semantic}}}
        bad = json.loads(json.dumps(result))
        bad["semantic"]["report"]["result"]["output_hashes"]["ledger.jsonl"] = "0" * 64
        db.expect(FINISH, "ORIGINAL_OUTPUT_BINDING_MISMATCH", "dispatcher",
                  **lease, result=json.dumps(bad))
        bad = json.loads(json.dumps(result))
        bad["intent"]["pipeline_sha256"] = "0" * 64
        db.expect(FINISH, "ORIGINAL_SOURCE_HASH_MISMATCH", "dispatcher",
                  **lease, result=json.dumps(bad))
        db.sql(FINISH, "dispatcher", **lease, result=json.dumps(result))
        actual = json.loads(db.sql("SELECT pf_product.get_job(:'w',:'s',:'j');", **job))
        require(actual["state"] == "NEEDS_REVIEW" and actual["outcome"] == "held",
                "Matching quarantine escaped hold")
        db.expect(FINISH, "STALE_JOB_LEASE", "dispatcher", **lease, result=json.dumps(result))
        require(db.sql("SELECT pf_product.get_job(:'w',:'s',:'j');", **{**job, **two}) == "",
                "Cross-workspace report leaked")
        checks.append("exact_source_output_receipt_bindings_correct_match_held_no_activation")

        job = {**job, "j": str(uuid4()), "i": str(uuid4())}
        db.sql(ENQUEUE, **job)
        owner = str(uuid4())
        row = json.loads(db.sql(CLAIM, "dispatcher", o=owner))
        lease = {**job, "o": owner, "g": row["generation"]}
        db.sql("SELECT pf_product.revoke_contract(:'w',:'s',:'c',:'a');", **job)
        db.expect(BEAT, "JOB_AUTHORITY_REVOKED", "dispatcher", **lease)
        db.expect(APPROVE, "CONTRACT_REVOKED", **contract)
        db.sql(FAIL, "dispatcher", **lease, termination='{"not_dispatched":true}')
        actual = json.loads(db.sql("SELECT pf_product.get_job(:'w',:'s',:'j');", **job))
        require(actual["state"] == "CANCELLED", "Revoked authority mislabeled as infrastructure")
        checks.append("revoked_contract_blocks_live_job_and_cannot_reactivate")

        new_contract = db.asset(one, "contract")
        db.sql(APPROVE, **new_contract)
        job = {**job, "a": new_contract["a"], "j": str(uuid4()), "i": str(uuid4())}
        db.sql(ENQUEUE, **job)
        owner = str(uuid4())
        claimed = json.loads(db.sql(CLAIM, "dispatcher", o=owner))
        lease = {**job, "o": owner, "g": claimed["generation"], "e": str(uuid4()), "m": "d" * 64}
        db.sql(BEGIN, "dispatcher", **lease)
        db.sql("SELECT pf_product.configure_execution(repeat('b',64),repeat('d',64),true);",
               "provisioner")
        db.expect(BEAT, "JOB_AUTHORITY_REVOKED", "dispatcher", **lease)
        db.sql("UPDATE pf_product.jobs SET lease_until=clock_timestamp()-interval '1 second' "
               "WHERE workspace_id=:'w' AND id=:'j';", "admin", **job)
        replacement = str(uuid4())
        recovered = json.loads(db.sql(CLAIM, "dispatcher", o=replacement))
        require(recovered["verifier_sha256"] == "c" * 64 and recovered["cancel_requested"] is True,
                "Recovery overwrote the original verifier identity")
        old_receipt = {"execution": lease["e"].replace("-", ""),
                       "job": lease["j"].replace("-", ""), "generation": lease["g"],
                       "manifest": lease["m"], "cleanup": "confirmed"}
        db.sql(FAIL, "dispatcher", **{**lease, "o": replacement, "g": recovered["generation"]},
               termination=json.dumps(old_receipt))
        checks.append("policy_epoch_change_cancels_and_preserves_old_execution_identity")

        job = {**job, "j": str(uuid4()), "i": str(uuid4())}
        db.sql(ENQUEUE, **job)
        db.sql("SELECT pf_product.cancel_job(:'w',:'s',:'c',:'j');", **job)
        require(db.sql(CLAIM, "dispatcher", o=str(uuid4())) == "", "Cancelled job dispatched")
        require(json.loads(db.sql("SELECT pf_product.get_job(:'w',:'s',:'j');", **job))["state"]
                == "CANCELLED", "Pre-dispatch cancellation not durable")
        checks.append("cancel_before_dispatch_never_claims_worker")

        count = int(db.sql("SELECT count(*) FROM pf_product.jobs;", "admin"))
        for _ in range(16 - count):
            db.sql(ENQUEUE, **{**job, "j": str(uuid4()), "i": str(uuid4())})
        db.expect(ENQUEUE, "JOB_CAPACITY", **{**job, "j": str(uuid4()), "i": str(uuid4())})
        checks.append("fixed_global_job_capacity_includes_terminal_records")
    checks.append("owned_fixture_cleanup_confirmed")
    print(json.dumps({"scope": "disposable_postgres_synthetic_metadata_only", "passed": len(checks),
                      "checks": checks, "deployed_api_queue": "NOT_RUN"}))


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        print(error.stderr[:2000])
        raise SystemExit(1) from None
