"""Real disposable SQL checks. Synthetic receipts here are NOT worker evidence."""

import hashlib
import json
import subprocess
from uuid import uuid4

from scripts.check_budget_postgres import require
from scripts.check_product_queue import APPROVE, ENQUEUE
from tests.integration.product_database_fixture import database

PREPARE = "SELECT pf_product.prepare_version(:'w',:'s',:'c',:'r',:'a');"
PREVIEW = "SELECT pf_product.preview_version(:'w',:'s',:'c',:'r',:'intent');"
ACTIVATE = "SELECT pf_product.approve_version(:'w',:'s',:'c',:'r',:'intent',:'digest');"
BATCH = "SELECT pf_product.enqueue_batch(:'w',:'s',:'c',:'pipeline',:'r',:'j',:'i',:'t',:'u');"


def verified_fixture(db, owner, assets, source="inert fixture bytes"):
    parent = {
        **owner,
        "j": str(uuid4()),
        "i": str(uuid4()),
        "p": assets["pipeline"]["a"],
        "t": assets["transactions"]["a"],
        "u": assets["customers"]["a"],
        "a": assets["contract"]["a"],
    }
    db.sql(ENQUEUE, **parent)
    db.sql(
        "UPDATE pf_product.jobs SET state='NEEDS_REVIEW',outcome='match',"
        "report='{"
        '"semantic"'
        ": {"
        '"report"'
        ": {"
        '"result"'
        ": {"
        '"blocking_occurrences"'
        ":0}}}}'"
        " WHERE id=:'j';",
        "admin",
        **parent,
    )
    result = {**owner, "r": str(uuid4()), "pipeline": assets["pipeline"]["a"]}
    db.sql(
        "SELECT pf_product.enqueue_repair(:'w',:'s',:'c',:'r',:'i',:'j');",
        **{**parent, **result, "i": str(uuid4())},
    )
    db.sql(
        "UPDATE pf_product.repairs SET state='AWAITING_APPROVAL',outcome='candidate_passed' "
        "WHERE id=:'r'; INSERT INTO pf_product.repair_candidates VALUES"
        "(:'w',:'r',0,:'source','original');",
        "admin",
        **result,
        source=source,
    )
    for n, purpose in enumerate(("candidate", "canary_ownership", "canary_quarantine"), 1):
        db.sql(
            "INSERT INTO pf_product.repair_executions VALUES(:'w',:'r',:'n',0,:'e',:'purpose',"
            "'{}',:'result');",
            "admin",
            **result,
            n=n,
            e=str(uuid4()),
            purpose=purpose,
            result=json.dumps(
                {
                    "worker": {"cleanup": "confirmed"},
                    "semantic": {"report": {"result": {"comparison": "match"}}},
                }
            ),
        )
    asset = {
        **owner,
        "a": str(uuid4()),
        "d": hashlib.sha256(source.encode()).hexdigest(),
        "n": len(source.encode()),
        "k": "pipeline",
    }
    db.sql("SELECT pf_product.reserve_upload(:'w',:'s',:'c',:'a',:'k',:'d',:'n');", **asset)
    db.sql("SELECT pf_product.complete_upload(:'w',:'s',:'c',:'a',:'k',:'d',:'n');", **asset)
    result["a"] = asset["a"]
    db.sql(PREPARE, **result)
    return result


def preview(db, v):
    v = {**v, "intent": str(uuid4())}
    value = json.loads(db.sql(PREVIEW, **v))
    return {**v, "digest": value["bundle_sha256"]}


def main():
    checks = []
    with database() as db:
        owner, foreign = db.workspace(), db.workspace()
        assets = {
            k: db.asset(owner, k) for k in ("pipeline", "transactions", "customers", "contract")
        }
        db.sql(APPROVE, **assets["contract"])
        db.sql(
            "SELECT pf_product.configure_execution(repeat('b',64),repeat('c',64),true);",
            "provisioner",
        )
        first = verified_fixture(db, owner, assets)
        second = verified_fixture(db, owner, assets, "different inert fixture")
        a, b = preview(db, first), preview(db, second)
        db.expect(ACTIVATE, "ACCESS_DENIED", **{**a, "s": foreign["s"]})
        db.expect(ACTIVATE, "EXACT_VERSION_APPROVAL_REQUIRED", **{**a, "digest": "0" * 64})
        require(not json.loads(db.sql(ACTIVATE, **a))["already_applied"], "Initial approval absent")
        require(json.loads(db.sql(ACTIVATE, **a))["already_applied"], "Duplicate approval replayed")
        db.expect(ACTIVATE, "VERSION_CONFLICT", **b)
        db.expect("UPDATE pf_product.versions SET revoked_at=NULL;", "permission denied")
        db.expect(
            "SELECT pf_product.version_bundle(:'w',:'s',:'r',:'intent',clock_timestamp());",
            "permission denied",
            **a,
        )
        checks.append("exact_actor_digest_intent_CAS_and_role_boundaries")
        batch = {
            **first,
            "j": str(uuid4()),
            "i": str(uuid4()),
            "t": assets["transactions"]["a"],
            "u": assets["customers"]["a"],
        }
        require(db.sql(BATCH, **batch) == batch["j"], "Batch missing")
        fresh_b = preview(db, second)
        db.sql(ACTIVATE, **fresh_b)
        require(db.sql(BATCH, **batch) == batch["j"], "Retry rebound to new active version")
        db.expect(BATCH, "JOB_IDEMPOTENCY_CONFLICT", **{**batch, "r": second["r"]})
        db.expect(BATCH, "VERSION_NOT_ELIGIBLE", **{**batch, "i": str(uuid4()), "j": str(uuid4())})
        current = json.loads(db.sql("SELECT pf_product.get_batch(:'w',:'s',:'j');", **batch))
        require(
            current["version_id"] == first["r"] and current["state"] == "QUEUED", "Binding changed"
        )
        require(
            db.sql("SELECT pf_product.get_batch(:'w',:'s',:'j');", **{**batch, **foreign}) == "",
            "Foreign batch disclosed",
        )
        checks.append("fresh_batch_fixed_version_retry_after_activation_no_rebinding")
        controller = str(uuid4())
        claim = json.loads(
            db.sql("SELECT pf_product.claim_original(:'o');", "dispatcher", o=controller)
        )
        require(claim["id"] == batch["j"], "Wrong job claimed")
        version = json.loads(db.sql("SELECT pf_product.get_version(:'w',:'s',:'r');", **first))
        db.sql(
            "SELECT pf_product.revoke_version(:'w',:'s',:'c',:'r',:'revision');",
            **first,
            revision=version["pipeline_revision"],
        )
        db.expect(
            "SELECT pf_product.heartbeat_original(:'w',:'j',:'o',:'g');",
            "JOB_AUTHORITY_REVOKED",
            "dispatcher",
            **batch,
            o=controller,
            g=claim["generation"],
        )
        db.expect(PREVIEW, "VERSION_NOT_ELIGIBLE", **{**a, "intent": str(uuid4())})
        db.sql(
            "SELECT pf_product.fail_original(:'w',:'j',:'o',:'g','{\"not_dispatched\":true}');",
            "dispatcher",
            **batch,
            o=controller,
            g=claim["generation"],
        )
        require(
            json.loads(db.sql("SELECT pf_product.get_batch(:'w',:'s',:'j');", **batch))["state"]
            == "CANCELLED",
            "Revoked batch not cancelled",
        )
        checks.append("revocation_blocks_running_publication_preserves_binding_cleanup")
        db.sql(
            "SELECT pf_product.configure_execution(repeat('d',64),repeat('c',64),true);",
            "provisioner",
        )
        db.sql(
            "SELECT pf_product.configure_execution(repeat('b',64),repeat('c',64),true);",
            "provisioner",
        )
        db.expect(PREVIEW, "VERSION_NOT_ELIGIBLE", **{**fresh_b, "intent": str(uuid4())})
        db.expect(PREPARE, "VERSION_NOT_ELIGIBLE", **second)
        checks.append("global_runtime_roundtrip_does_not_revive_verification_or_approval")
    print(
        json.dumps(
            {
                "scope": "disposable_SQL_synthetic_evidence",
                "passed": len(checks),
                "checks": checks,
                "provider_worker_calls": 0,
            }
        )
    )


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        print(error.stderr[:2000])
        raise SystemExit(1) from None
