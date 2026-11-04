"""Real disposable PostgreSQL; synthetic upstream receipts, no GitHub requests."""

import hashlib
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from scripts.check_budget_postgres import require
from scripts.check_product_queue import APPROVE
from scripts.check_versions_batches import ACTIVATE, preview, verified_fixture
from tests.integration.product_database_fixture import database

REQUEST = "SELECT pf_product.request_pr_preview(:'w',:'s',:'c',:'r',:'intent');"
CLAIM = "SELECT pf_product.claim_pr(:'controller');"
RECORD = "SELECT pf_product.record_pr_preview(:'w',:'intent',:'controller',:'fence',:'inspection');"
APPROVE_PR = "SELECT pf_product.approve_pr(:'w',:'s',:'c',:'intent',:'digest');"
BEGIN = "SELECT pf_product.begin_pr_write(:'w',:'intent',:'controller',:'fence',:'stage');"
READBACK = (
    "SELECT pf_product.record_pr_readback("
    ":'w',:'intent',:'controller',:'fence',:'stage',:'receipt');"
)


def claim(db, values):
    result = json.loads(db.sql(CLAIM, "dispatcher", **values))
    require(result["id"] == values["intent"], "Unexpected outbox identity")
    return {**values, "fence": result["generation"]}, result


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
        version = verified_fixture(db, owner, assets)
        db.sql(ACTIVATE, **preview(db, version))
        config = json.dumps(
            {
                "client_id": "Iv1.fixture",
                "installation_id": 12,
                "repository_id": 34,
                "owner": "arslanabdulghaffar",
                "repository": "ProofFlow-Demo",
                "base": "main",
                "path": "pipeline.py",
            }
        )
        v = {**version, "intent": str(uuid4()), "controller": str(uuid4())}
        db.expect(REQUEST, "GITHUB_NOT_CONFIGURED", **v)
        db.expect(
            "SELECT pf_product.configure_github(:'config',true);",
            "permission denied",
            config=config,
        )
        db.sql("SELECT pf_product.configure_github(:'config',true);", "provisioner", config=config)
        require(db.sql(REQUEST, **v) == v["intent"], "Preview intent missing")
        require(db.sql(REQUEST, **v) == v["intent"], "Preview retry duplicated")
        db.expect(REQUEST, "ACCESS_DENIED", **{**v, "s": foreign["s"]})
        db.expect("UPDATE pf_product.pr_intents SET state='COMPLETE';", "permission denied")
        v, _ = claim(db, v)
        db.expect(BEGIN, "PR_AUTHORITY_REVOKED", "dispatcher", **v, stage="branch")
        inspection = json.dumps(
            {
                "base_sha": "a" * 40,
                "base_tree_sha": "b" * 40,
                "prior_blob": None,
                "original_sha256": hashlib.sha256(b"").hexdigest(),
                "diff": "inert fixture diff",
            }
        )
        digest = db.sql(RECORD, "dispatcher", **v, inspection=inspection)
        db.expect(APPROVE_PR, "EXACT_PR_APPROVAL_REQUIRED", **v, digest="0" * 64)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(db.sql, APPROVE_PR, **v, digest=digest) for _ in range(2)]
            require(
                sorted(f.result() for f in futures) == ["f", "t"], "Concurrent approval duplicated"
            )
        checks.append("operator_exact_preview_approval_idempotency_and_privilege_boundary")

        v, _ = claim(db, v)
        payload = json.loads(db.sql(BEGIN, "dispatcher", **v, stage="branch"))
        require(
            payload["payload"]["sha"] == "a" * 40 and payload["path"].endswith("/git/refs"),
            "Wrong request",
        )
        db.expect(BEGIN, "PR_WRITE_ALREADY_PREPARED", "dispatcher", **v, stage="branch")
        # Model controller death AFTER a committed dispatch. Only a readback can advance it.
        old = dict(v)
        db.sql(
            "UPDATE pf_product.pr_intents SET lease_until=clock_timestamp()-interval '1 second' "
            "WHERE id=:'intent';",
            "admin",
            **v,
        )
        v, state = claim(db, {**v, "controller": str(uuid4())})
        require(
            state["state"] == "BRANCH_PENDING" and v["fence"] > old["fence"],
            "Lost write not reconciled",
        )
        receipt = json.dumps({"head_sha": "a" * 40, "base_sha": "a" * 40})
        db.expect(READBACK, "STALE_PR_LEASE", "dispatcher", **old, stage="branch", receipt=receipt)
        db.expect(BEGIN, "PR_WRITE_ALREADY_PREPARED", "dispatcher", **v, stage="branch")
        db.sql(READBACK, "dispatcher", **v, stage="branch", receipt=receipt)
        checks.append("committed_uncertain_write_never_reissued_and_old_controller_fenced")

        v, _ = claim(db, v)
        commit = json.loads(db.sql(BEGIN, "dispatcher", **v, stage="commit"))
        require(
            commit["path"].endswith("/contents/pipeline.py") and "sha" not in commit["payload"],
            "Commit scope changed",
        )
        db.sql(
            READBACK,
            "dispatcher",
            **v,
            stage="commit",
            receipt=json.dumps({"head_sha": "c" * 40, "base_sha": "a" * 40}),
        )
        v, _ = claim(db, v)
        pr = json.loads(db.sql(BEGIN, "dispatcher", **v, stage="pr"))
        require(
            pr["payload"]["draft"] is True and pr["payload"]["base"] == "main", "PR scope changed"
        )
        # A later revocation cannot undo an authorized external write. Confirm and expose history.
        db.sql("SELECT pf_product.revoke_version(:'w',:'s',:'c',:'r',1);", **v)
        db.sql(
            READBACK,
            "dispatcher",
            **v,
            stage="pr",
            receipt=json.dumps(
                {
                    "head_sha": "c" * 40,
                    "base_sha": "a" * 40,
                    "repository_id": 34,
                    "draft": True,
                    "number": 1,
                    "url": "https://github.com/arslanabdulghaffar/ProofFlow-Demo/pull/1",
                }
            ),
        )
        final = json.loads(db.sql("SELECT pf_product.get_pr_intent(:'w',:'s',:'intent');", **v))
        require(
            final["state"] == "COMPLETE"
            and final["currently_authorized"] is False
            and len(final["writes"]) == 3,
            "Historical write was concealed by revocation",
        )
        checks.append("single_path_draft_only_steps_and_post_dispatch_revocation_history")

        second = verified_fixture(db, owner, assets, "second inert candidate")
        db.sql(ACTIVATE, **preview(db, second))
        pending = {**second, "intent": str(uuid4()), "controller": str(uuid4())}
        db.sql(REQUEST, **pending)
        pending, _ = claim(db, pending)
        digest = db.sql(RECORD, "dispatcher", **pending, inspection=inspection)
        db.sql(APPROVE_PR, **pending, digest=digest)
        pending, _ = claim(db, pending)
        db.sql(BEGIN, "dispatcher", **pending, stage="branch")
        db.sql(READBACK, "dispatcher", **pending, stage="branch", receipt=receipt)
        pending, _ = claim(db, pending)
        db.sql("SELECT pf_product.revoke_session(:'w',:'s',:'c');", **pending)
        db.expect(BEGIN, "PR_AUTHORITY_REVOKED", "dispatcher", **pending, stage="commit")
        checks.append("session_revocation_between_steps_denies_next_write")
        # Revoke workspace and release the ready stage; this intent has no uncertain mutation.
        db.sql(
            "SELECT pf_product.defer_pr(:'w',:'intent',:'controller',:'fence',"
            "'PR_AUTHORITY_REVOKED',true);",
            "dispatcher",
            **pending,
        )
        db.sql(
            "SELECT pf_product.revoke_workspace(:'w'); "
            "INSERT INTO pf_product.deletions(workspace_id,reason) VALUES(:'w','owner');",
            "admin",
            **owner,
        )
        plans = json.loads(db.sql("SELECT pf_product.retention_plan();", "provisioner"))
        require(len(plans) == 1, "Confirmed external state blocked retirement")
        # SQL fixture has no bytes; actual physical retirement is separately tested on deployment.
        db.sql(
            "SELECT pf_product.complete_deletion(:'w',:'digest');",
            "provisioner",
            **owner,
            digest=plans[0]["manifest_sha256"],
        )
        require(
            db.sql("SELECT count(*) FROM pf_product.pr_intents;", "admin") == "0",
            "Outbox raw metadata retained",
        )
        checks.append("confirmed_outbox_retirement_and_no_privilege_bypass")
        # Another fixture proves unknown external state blocks byte retirement.
        assets = {
            k: db.asset(foreign, k) for k in ("pipeline", "transactions", "customers", "contract")
        }
        db.sql(APPROVE, **assets["contract"])
        third = verified_fixture(db, foreign, assets)
        db.sql(ACTIVATE, **preview(db, third))
        u = {**third, "intent": str(uuid4()), "controller": str(uuid4())}
        db.sql(REQUEST, **u)
        u, _ = claim(db, u)
        digest = db.sql(RECORD, "dispatcher", **u, inspection=inspection)
        db.sql(APPROVE_PR, **u, digest=digest)
        u, _ = claim(db, u)
        db.sql(BEGIN, "dispatcher", **u, stage="branch")
        db.sql(
            "SELECT pf_product.defer_pr(:'w',:'intent',:'controller',:'fence',"
            "'GITHUB_BRANCH_CHANGED',true);",
            "dispatcher",
            **u,
        )
        db.sql("SELECT pf_product.request_deletion(:'w',:'s',:'c');", **u)
        require(
            json.loads(db.sql("SELECT pf_product.retention_plan();", "provisioner")) == [],
            "Uncertain external action lost its reconciliation evidence",
        )
        db.expect("SELECT pf_product.resume_pr_readback(:'w',:'intent');", "permission denied", **u)
        db.sql("SELECT pf_product.resume_pr_readback(:'w',:'intent');", "provisioner", **u)
        u, _ = claim(db, u)
        db.expect(BEGIN, "PR_AUTHORITY_REVOKED", "dispatcher", **u, stage="branch")
        db.sql(READBACK, "dispatcher", **u, stage="branch", receipt=receipt)
        require(db.sql(CLAIM, "dispatcher", **u) == "", "Revoked readback resumed writes")
        require(
            len(json.loads(db.sql("SELECT pf_product.retention_plan();", "provisioner"))) == 1,
            "Confirmed readback did not release retirement",
        )
        checks.append("uncertain_write_blocks_retirement_administrative_resume_is_read_only")
    print(
        json.dumps(
            {
                "status": "passed",
                "checks": checks,
                "github_calls": 0,
                "fixture": "synthetic_receipts_real_sql",
            }
        )
    )


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        raise RuntimeError(error.stderr) from None
