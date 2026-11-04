"""Disposable SQL security tests; synthetic metadata is NOT execution/model evidence."""

import hashlib
import json
import subprocess
from uuid import uuid4

from scripts.check_budget_postgres import require
from scripts.check_product_queue import APPROVE, ENQUEUE
from tests.integration.product_database_fixture import database

ENQUEUE_REPAIR = "SELECT pf_product.enqueue_repair(:'w',:'s',:'c',:'r',:'i',:'j');"
CLAIM = "SELECT pf_product.claim_repair(:'o');"
PREPARE = (
    "SELECT pf_product.prepare_repair_call(:'w',:'r',:'o',:'g',:'q',repeat('a',64),"
    "convert_to('{}','UTF8'),convert_to('{}','UTF8'),:'amount');"
)
RESPONSE = (
    "SELECT pf_product.record_repair_call(:'w',:'r',:'o',:'g',:'q',repeat('a',64),"
    "'PARSED_RESPONSE',convert_to('{}','UTF8'),200,1);"
)
PROPOSAL = "SELECT pf_product.repair_proposal(:'w',:'r',:'o',:'g',:'attempt',:'proposal');"
BEGIN = "SELECT pf_product.begin_repair_execution(:'w',:'r',:'o',:'g',:'attempt',:'e',:'intent');"
RESULT = "SELECT pf_product.record_repair_execution(:'w',:'r',:'o',:'g',:'e',:'result');"
FINISH = "SELECT pf_product.finish_repair(:'w',:'r',:'o',:'g',:'result_code');"


def main():
    checks = []
    with database() as db:
        one, other = db.workspace(), db.workspace()
        assets = {
            k: db.asset(one, k) for k in ("pipeline", "transactions", "customers", "contract")
        }
        db.sql(APPROVE, **assets["contract"])
        db.sql(
            "SELECT pf_product.configure_execution(repeat('b',64),repeat('c',64),true);",
            "provisioner",
        )
        parent = {
            **one,
            "j": str(uuid4()),
            "i": str(uuid4()),
            "p": assets["pipeline"]["a"],
            "t": assets["transactions"]["a"],
            "u": assets["customers"]["a"],
            "a": assets["contract"]["a"],
        }
        db.sql(ENQUEUE, **parent)
        repair = {**one, "j": parent["j"], "r": str(uuid4()), "i": str(uuid4())}
        db.expect(ENQUEUE_REPAIR, "REPAIR_PARENT_INVALID", **repair)
        # Explicit fixture state setup only in this disposable database. Live
        # acceptance must use the worker/verifier, never this metadata shortcut.
        db.sql(
            "UPDATE pf_product.jobs SET state='NEEDS_REVIEW',outcome='mismatch',"
            "report=:'report'::jsonb WHERE id=:'j';",
            "admin",
            **parent,
            report=json.dumps({"semantic": {"report": {"result": {"blocking_occurrences": 0}}}}),
        )
        require(db.sql(ENQUEUE_REPAIR, **repair) == repair["r"], "Missing repair")
        require(db.sql(ENQUEUE_REPAIR, **repair) == repair["r"], "Idempotency lost")
        db.expect(ENQUEUE_REPAIR, "ACCESS_DENIED", **{**repair, "s": other["s"]})
        db.expect(ENQUEUE_REPAIR, "JOB_IDEMPOTENCY_CONFLICT", **{**repair, "j": str(uuid4())})
        require(
            db.sql("SELECT pf_product.get_repair(:'w',:'s',:'r');", **{**repair, **other}) == "",
            "Foreign repair exposed",
        )
        db.expect("SELECT * FROM pf_product.repair_calls;", "permission denied")
        db.expect(CLAIM, "permission denied", o=str(uuid4()))
        db.expect(
            "SELECT pf_product.claim_original_without_repair(:'o');",
            "permission denied",
            "dispatcher",
            o=str(uuid4()),
        )
        checks.append("owned_parent_exact_idempotency_role_and_workspace_separation")

        owner = str(uuid4())
        claimed = json.loads(db.sql(CLAIM, "dispatcher", o=owner))
        lease = {
            **repair,
            "o": owner,
            "g": claimed["generation"],
            "q": str(uuid4()),
            "amount": 200000,
        }
        require(db.sql(CLAIM, "dispatcher", o=str(uuid4())) == "", "Double repair claim")
        require(
            db.sql("SELECT pf_product.claim_original(:'o');", "dispatcher", o=str(uuid4())) == "",
            "Original bypassed repair lease",
        )
        db.expect(PREPARE, "STALE_JOB_LEASE", "dispatcher", **{**lease, "o": str(uuid4())})
        db.sql(PREPARE, "dispatcher", **lease)
        db.expect(PREPARE, "REPAIR_CALL_ALREADY_PREPARED", "dispatcher", **lease)
        db.expect(PREPARE, "REPAIR_OUTCOME_UNCERTAIN", "dispatcher", **{**lease, "q": str(uuid4())})
        db.sql(RESPONSE, "dispatcher", **lease)
        db.expect(RESPONSE, "REPAIR_RECEIPT_CONFLICT", "dispatcher", **lease)
        proposal = {"kind": "propose_patch", "candidate_source": "inert fixture source"}
        db.sql(PROPOSAL, "dispatcher", **lease, attempt=1, proposal=json.dumps(proposal))
        db.expect(
            PROPOSAL,
            "REPAIR_RECEIPT_CONFLICT",
            "dispatcher",
            **lease,
            attempt=1,
            proposal=json.dumps(proposal),
        )
        db.expect(
            FINISH, "REPAIR_PROOF_INCOMPLETE", "dispatcher", **lease, result_code="candidate_passed"
        )
        checks.append("single_worker_stale_fencing_single_use_call_immutable_response_no_fake_pass")

        intent = {
            "execution": uuid4().hex,
            "job": repair["r"].replace("-", ""),
            "generation": 1,
            "purpose": "candidate",
            "pipeline_sha256": hashlib.sha256(proposal["candidate_source"].encode()).hexdigest(),
            "manifest_sha256": "d" * 64,
        }
        intent.update(
            runtime_sha256="b" * 64,
            verifier_rootfs="c" * 64,
            contract_raw_sha256=assets["contract"]["d"],
            transactions_sha256=assets["transactions"]["d"],
            customers_sha256=assets["customers"]["d"],
        )
        execution = {**lease, "attempt": 1, "e": str(uuid4()), "intent": json.dumps(intent)}
        db.expect(BEGIN, "EXECUTION_INTENT_CONFLICT", "dispatcher", **execution)
        execution["e"] = str(uuid4())
        intent["execution"] = execution["e"].replace("-", "")
        execution["intent"] = json.dumps(intent)
        db.sql(BEGIN, "dispatcher", **execution)
        db.expect(
            FINISH, "CLEANUP_REQUIRED", "dispatcher", **lease, result_code="infrastructure_failed"
        )
        result = {
            "intent": intent,
            "worker": {
                "execution": intent["execution"],
                "job": intent["job"],
                "generation": 1,
                "manifest": "d" * 64,
                "cleanup": "confirmed",
            },
            "semantic": None,
        }
        db.sql(RESULT, "dispatcher", **execution, result=json.dumps(result))
        db.expect(RESULT, "CLEANUP_REQUIRED", "dispatcher", **execution, result=json.dumps(result))
        db.sql(PREPARE, "dispatcher", **{**lease, "q": str(uuid4())})
        db.expect(PREPARE, "REPAIR_BUDGET_EXHAUSTED", "dispatcher", **{**lease, "q": str(uuid4())})
        checks.append("exact_execution_cleanup_required_and_per_job_money_bound")

        db.sql(
            "UPDATE pf_product.repairs SET lease_until=clock_timestamp()-interval '1 second' "
            "WHERE id=:'r';",
            "admin",
            **repair,
        )
        require(
            db.sql("SELECT pf_product.claim_original(:'o');", "dispatcher", o=str(uuid4())) == "",
            "Uncertain repair released worker",
        )
        fresh = str(uuid4())
        recovered = json.loads(db.sql(CLAIM, "dispatcher", o=fresh))
        require(
            recovered["state"] == "RECONCILING" and recovered["calls"] == 2,
            "Recovery lost calls or resumed productive repair",
        )
        recovery = {**lease, "o": fresh, "g": recovered["generation"]}
        db.expect(PREPARE, "JOB_AUTHORITY_REVOKED", "dispatcher", **{**recovery, "q": str(uuid4())})
        db.sql("SELECT pf_product.request_deletion(:'w',:'s',:'c');", **one)
        plans = json.loads(db.sql("SELECT pf_product.retention_plan();", "provisioner"))
        require(not plans, "Deletion ignored active repair")
        db.sql(FINISH, "dispatcher", **recovery, result_code="infrastructure_failed")
        plans = json.loads(db.sql("SELECT pf_product.retention_plan();", "provisioner"))
        require(set(plans[0]["jobs"]) == {parent["j"], repair["r"]}, "Repair journals omitted")
        before = db.sql("SELECT reserved_micro FROM pf_product.repair_allocation;", "admin")
        db.sql(
            "SELECT pf_product.complete_deletion(:'w',:'d');",
            "provisioner",
            **one,
            d=plans[0]["manifest_sha256"],
        )
        require(
            db.sql("SELECT count(*) FROM pf_product.repair_calls;", "admin") == "0",
            "Raw provider content retained",
        )
        require(
            db.sql("SELECT reserved_micro FROM pf_product.repair_allocation;", "admin") == before,
            "Deletion reset development spending",
        )
        checks.append("expired_lease_cleanup_only_retention_includes_repair_no_budget_reset")

        # A second, explicitly synthetic parent exercises all positive proof gates
        # and output tampering; it is not counted as a real repaired pipeline.
        one = db.workspace()
        assets = {
            k: db.asset(one, k) for k in ("pipeline", "transactions", "customers", "contract")
        }
        db.sql(APPROVE, **assets["contract"])
        parent = {
            **one,
            "j": str(uuid4()),
            "i": str(uuid4()),
            "p": assets["pipeline"]["a"],
            "t": assets["transactions"]["a"],
            "u": assets["customers"]["a"],
            "a": assets["contract"]["a"],
        }
        db.sql(ENQUEUE, **parent)
        db.sql(
            "UPDATE pf_product.jobs SET state='NEEDS_REVIEW',outcome='mismatch',"
            "report=:'report'::jsonb WHERE id=:'j';",
            "admin",
            **parent,
            report=json.dumps({"semantic": {"report": {"result": {"blocking_occurrences": 0}}}}),
        )
        repair = {**one, "j": parent["j"], "r": str(uuid4()), "i": str(uuid4())}
        db.sql(ENQUEUE_REPAIR, **repair)
        owner = str(uuid4())
        claimed = json.loads(db.sql(CLAIM, "dispatcher", o=owner))
        lease = {**repair, "o": owner, "g": claimed["generation"], "q": str(uuid4()), "amount": 1}
        db.sql(PREPARE, "dispatcher", **lease)
        db.sql(RESPONSE, "dispatcher", **lease)
        db.sql(PROPOSAL, "dispatcher", **lease, attempt=1, proposal=json.dumps(proposal))
        require(
            db.sql("SELECT pf_product.export_repair(:'w',:'s',:'r');", **repair) == "",
            "Unverified candidate exported",
        )
        for generation, purpose in enumerate(
            ("candidate", "canary_ownership", "canary_quarantine"), 1
        ):
            execution_id = str(uuid4())
            intent = {
                "execution": execution_id.replace("-", ""),
                "job": repair["r"].replace("-", ""),
                "generation": generation,
                "purpose": purpose,
                "manifest_sha256": "d" * 64,
                "pipeline_sha256": hashlib.sha256(
                    proposal["candidate_source"].encode()
                ).hexdigest(),
                "runtime_sha256": "b" * 64,
                "verifier_rootfs": "c" * 64,
                "contract_raw_sha256": assets["contract"]["d"],
                "contract_sha256": "e" * 64,
                "transactions_sha256": assets["transactions"]["d"],
                "customers_sha256": assets["customers"]["d"],
            }
            execution = {**lease, "attempt": 1, "e": execution_id, "intent": json.dumps(intent)}
            db.sql(BEGIN, "dispatcher", **execution)
            outputs = {"ledger.jsonl": "1" * 64, "unresolved.jsonl": "2" * 64}
            result = {
                "intent": intent,
                "worker": {
                    "execution": intent["execution"],
                    "job": intent["job"],
                    "generation": generation,
                    "manifest": "d" * 64,
                    "cleanup": "confirmed",
                    "collected": True,
                    "runtime_client_exit_code": 0,
                    "unit_result": "success",
                    "files": [{"name": k, "sha256": v} for k, v in outputs.items()],
                },
                "semantic": {
                    "cleanup_confirmed": True,
                    "rootfs_sha256": "c" * 64,
                    "report": {
                        "version": "proofflow-verifier-v1",
                        "status": "processed",
                        "result": {
                            "operation": "verify",
                            "comparison": "match",
                            "finding_count": 0,
                            "findings": [],
                            "blocking_occurrences": 2 if purpose == "canary_quarantine" else 0,
                            "output_hashes": outputs,
                            **{
                                key: intent[key]
                                for key in (
                                    "contract_sha256",
                                    "transactions_sha256",
                                    "customers_sha256",
                                )
                            },
                        },
                    },
                },
            }
            bad = json.loads(json.dumps(result))
            bad["semantic"]["report"]["result"]["output_hashes"]["ledger.jsonl"] = "0" * 64
            db.expect(
                RESULT, "REPAIR_PROOF_INCOMPLETE", "dispatcher", **execution, result=json.dumps(bad)
            )
            db.sql(RESULT, "dispatcher", **execution, result=json.dumps(result))
            if generation < 3:
                db.expect(
                    FINISH,
                    "REPAIR_PROOF_INCOMPLETE",
                    "dispatcher",
                    **lease,
                    result_code="candidate_passed",
                )
        db.sql(FINISH, "dispatcher", **lease, result_code="candidate_passed")
        exported = json.loads(db.sql("SELECT pf_product.export_repair(:'w',:'s',:'r');", **repair))
        require(
            exported["candidate_source"] == proposal["candidate_source"], "Candidate bytes changed"
        )
        require(
            json.loads(db.sql("SELECT pf_product.get_repair(:'w',:'s',:'r');", **repair))["state"]
            == "AWAITING_APPROVAL",
            "Repair activated automatically",
        )
        db.sql("SELECT pf_product.revoke_contract(:'w',:'s',:'c',:'a');", **parent)
        require(
            db.sql("SELECT pf_product.export_repair(:'w',:'s',:'r');", **repair) == "",
            "Export ignored contract revocation",
        )
        summary = json.loads(db.sql("SELECT pf_product.get_repair(:'w',:'s',:'r');", **repair))
        require(
            [e["sequence"] for e in summary["events"]]
            == list(range(1, len(summary["events"]) + 1)),
            "Repair event sequence lost",
        )
        require(
            {e["event"] for e in summary["events"]}
            >= {
                "provider_request_committed",
                "provider_response_recorded",
                "proposal_recorded",
                "execution_intent_committed",
                "execution_result_recorded",
                "state_awaiting_approval",
            },
            "Repair event history incomplete",
        )
        bundle = json.loads(db.sql("SELECT pf_product.repair_bundle(:'w',:'s',:'r');", **repair))
        require(
            len(bundle["executions"]) == 3 and len(bundle["candidates"]) == 1,
            "Owned bundle evidence missing",
        )
        db.expect("SELECT * FROM pf_product.repair_events;", "permission denied")
        checks.append("three_fresh_exact_proofs_export_only_no_activation_revocation_checked")
    print(
        json.dumps(
            {
                "scope": "disposable_postgres_synthetic_metadata_only",
                "passed": len(checks),
                "checks": checks,
                "model_and_worker_calls": 0,
            }
        )
    )


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        print(error.stderr[:2000])
        raise SystemExit(1) from None
