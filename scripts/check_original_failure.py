"""Real disposable PostgreSQL gates; synthetic receipts, no candidate/provider execution."""

import copy
import json
from uuid import uuid4

from scripts.check_budget_postgres import require
from scripts.check_product_queue import APPROVE, BEGIN, CLAIM, ENQUEUE
from tests.integration.product_database_fixture import database

REVIEW = "SELECT pf_product.review_original_failure(:'w',:'j',:'o',:'g',:'result');"
REPAIR = "SELECT pf_product.enqueue_repair(:'w',:'s',:'c',:'r',:'i',:'j');"


def main():
    checks = []
    with database() as db:
        context = db.workspace()
        db.sql(
            "SELECT pf_product.configure_execution(repeat('b',64),repeat('c',64),true);",
            "provisioner",
        )
        assets = {
            kind: db.asset(context, kind)
            for kind in ("pipeline", "transactions", "customers", "contract")
        }
        db.sql(APPROVE, **assets["contract"])

        def start():
            job = {
                **context,
                "j": str(uuid4()),
                "i": str(uuid4()),
                "p": assets["pipeline"]["a"],
                "t": assets["transactions"]["a"],
                "u": assets["customers"]["a"],
                "a": assets["contract"]["a"],
                "o": str(uuid4()),
                "e": str(uuid4()),
                "m": "d" * 64,
            }
            db.sql(ENQUEUE, **job)
            job["g"] = json.loads(db.sql(CLAIM, "dispatcher", **job))["generation"]
            db.sql(BEGIN, "dispatcher", **job)
            intent = {
                "execution": job["e"].replace("-", ""),
                "job": job["j"].replace("-", ""),
                "generation": job["g"],
                "purpose": "original",
                "manifest_sha256": job["m"],
                "runtime_sha256": "b" * 64,
                "verifier_rootfs": "c" * 64,
                "contract_sha256": "a" * 64,
            }
            for kind, asset in assets.items():
                intent["contract_raw_sha256" if kind == "contract" else kind + "_sha256"] = asset[
                    "d"
                ]
            worker = {
                "execution": intent["execution"],
                "job": intent["job"],
                "generation": job["g"],
                "manifest": job["m"],
                "cleanup": "confirmed",
                "runtime": {"fixture": True},
                "outcome": "output_rejected",
                "runtime_exit_kind": "1",
                "resource_observation": {
                    "source": "host_cgroup_v2",
                    "samples": 1,
                    "limits": {
                        "cpu_cores": 1,
                        "memory_bytes": 805306368,
                        "swap_bytes": 0,
                        "host_tasks": 128,
                    },
                },
                "unit_result": "exit-code",
                "runtime_exit_code": "1",
                "runtime_client_exit_code": 1,
                "collected": False,
            }
            source = {
                "operation": "source",
                "blocking_occurrences": 0,
                **{
                    k: intent[k]
                    for k in ("contract_sha256", "transactions_sha256", "customers_sha256")
                },
            }
            result = {
                "intent": intent,
                "worker": worker,
                "semantic": None,
                "source": {
                    "cleanup_confirmed": True,
                    "rootfs_sha256": "c" * 64,
                    "report": {
                        "status": "processed",
                        "version": "proofflow-verifier-v1",
                        "result": source,
                    },
                },
            }
            return job, result

        job, result = start()
        db.expect(REVIEW, "permission denied", **job, result=json.dumps(result))
        db.expect(
            REVIEW,
            "STALE_JOB_LEASE",
            "dispatcher",
            **{**job, "g": job["g"] + 1},
            result=json.dumps(result),
        )
        checks.append("api_cannot_record_failure_and_stale_controller_rejected")
        mutations = [
            (("worker", "cleanup"), "uncertain"),
            (("worker", "job"), uuid4().hex),
            (("worker", "generation"), True),
            (("worker", "manifest"), "x" * 64),
            (("worker", "outcome"), "infrastructure_failure"),
            (("worker", "outcome"), "timeout"),
            (("worker", "unit_result"), "oom-kill"),
            (("worker", "unit_result"), None),
            (("worker", "runtime_exit_kind"), "2"),
            (("worker", "runtime_client_exit_code"), True),
            (("worker", "runtime_client_exit_code"), 127),
            (("worker", "runtime_exit_code"), "2"),
            (("intent", "runtime_sha256"), "e" * 64),
            (("intent", "purpose"), "candidate"),
            (("source", "cleanup_confirmed"), False),
            (("source", "rootfs_sha256"), "f" * 64),
            (("source", "report", "status"), "rejected"),
            (("source", "report", "version"), "foreign"),
            (("source", "report", "result", "operation"), "verify"),
            (("source", "report", "result", "comparison"), "match"),
            (("source", "report", "result", "blocking_occurrences"), True),
            (("source", "report", "result", "blocking_occurrences"), 10001),
            (("source", "report", "result", "blocking_occurrences"), None),
        ]
        for keys, value in mutations:
            changed = copy.deepcopy(result)
            node = changed
            for key in keys[:-1]:
                node = node[key]
            node[keys[-1]] = value
            db.expect(
                REVIEW,
                "ORIGINAL_REPORT_BINDING_MISMATCH",
                "dispatcher",
                **job,
                result=json.dumps(changed),
            )
        for key in (
            "pipeline_sha256",
            "contract_raw_sha256",
            "transactions_sha256",
            "customers_sha256",
        ):
            changed = copy.deepcopy(result)
            changed["intent"][key] = "9" * 64
            db.expect(
                REVIEW,
                "ORIGINAL_SOURCE_HASH_MISMATCH",
                "dispatcher",
                **job,
                result=json.dumps(changed),
            )
        for key in ("transactions_sha256", "customers_sha256"):
            changed = copy.deepcopy(result)
            changed["source"]["report"]["result"][key] = "9" * 64
            db.expect(
                REVIEW,
                "ORIGINAL_SOURCE_HASH_MISMATCH",
                "dispatcher",
                **job,
                result=json.dumps(changed),
            )
        checks.append("23_receipt_faults_and_six_source_substitutions_rejected")
        db.sql(REVIEW, "dispatcher", **job, result=json.dumps(result))
        require(
            db.sql("SELECT state||':'||outcome FROM pf_product.jobs WHERE id=:'j';", "admin", **job)
            == "NEEDS_REVIEW:execution_failed",
            "Failure mislabeled",
        )
        require(
            db.sql(
                "SELECT worker_receipt=:'receipt'::jsonb AND worker_receipt_sha256="
                "encode(sha256(convert_to(worker_receipt::text,'UTF8')),'hex') "
                "AND report->'semantic'='null'::jsonb FROM pf_product.jobs WHERE id=:'j';",
                "admin",
                **job,
                receipt=json.dumps(result["worker"]),
            )
            == "t",
            "Evidence changed",
        )
        db.expect(REVIEW, "STALE_JOB_LEASE", "dispatcher", **job, result=json.dumps(result))
        repair = {**job, "r": str(uuid4()), "i": str(uuid4())}
        require(db.sql(REPAIR, **repair) == repair["r"], "Safe failure not repairable")
        require(
            db.sql(REPAIR, **{**repair, "r": str(uuid4())}) == repair["r"], "Retry changed repair"
        )
        db.expect(
            "SELECT pf_product.prepare_version(:'w',:'s',:'c',:'v',:'r');",
            "VERSION_NOT_ELIGIBLE",
            **repair,
            v=str(uuid4()),
        )
        # Retire queued fixture repair normally so the next original can lease the sole worker.
        db.sql("SELECT pf_product.cancel_repair(:'w',:'s',:'c',:'r');", **repair)
        checks.append("truthful_failure_no_output_proof_idempotent_repair_no_activation")
        job, result = start()
        result["source"]["report"]["result"]["blocking_occurrences"] = 2
        db.sql(REVIEW, "dispatcher", **job, result=json.dumps(result))
        require(
            db.sql("SELECT outcome FROM pf_product.jobs WHERE id=:'j';", "admin", **job) == "held",
            "Invalid sources not held",
        )
        db.expect(REPAIR, "REPAIR_PARENT_INVALID", **job, r=str(uuid4()))
        checks.append("invalid_source_remains_held_and_cannot_enter_repair")
        job, result = start()
        result["worker"].update(
            runtime_client_exit_code=0,
            runtime_exit_code="0",
            runtime_exit_kind="0",
            unit_result="success",
        )
        for mutate in ("missing_metrics", "zero_samples", "wrong_limits", "signal", "raw_preview"):
            changed = copy.deepcopy(result)
            if mutate == "missing_metrics":
                del changed["worker"]["resource_observation"]
            elif mutate == "zero_samples":
                changed["worker"]["resource_observation"]["samples"] = 0
            elif mutate == "wrong_limits":
                changed["worker"]["resource_observation"]["limits"]["swap_bytes"] = 1
            elif mutate == "signal":
                changed["worker"]["runtime_exit_kind"] = "2"
            else:
                changed["worker"]["failure_log_preview"] = {"stderr": "private"}
            db.expect(
                REVIEW,
                "ORIGINAL_REPORT_BINDING_MISMATCH",
                "dispatcher",
                **job,
                result=json.dumps(changed),
            )
        db.sql(REVIEW, "dispatcher", **job, result=json.dumps(result))
        require(
            db.sql("SELECT outcome FROM pf_product.jobs WHERE id=:'j';", "admin", **job)
            == "execution_failed",
            "Successful process with no outputs not repairable",
        )
        checks.append("zero_status_requires_observed_startup_limits_no_signal_or_raw_log")
        job, result = start()
        db.sql("SELECT pf_product.cancel_job(:'w',:'s',:'c',:'j');", **job)
        db.expect(REVIEW, "JOB_AUTHORITY_REVOKED", "dispatcher", **job, result=json.dumps(result))
        checks.append("cancellation_prevents_failure_promotion")
    print(json.dumps({"checks": checks, "passed": len(checks), "cloud_calls": 0}))


if __name__ == "__main__":
    main()
