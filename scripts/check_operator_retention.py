"""Disposable SQL fixture: operator expiry, scope and durable deletion tombstone."""

import json

from scripts.check_budget_postgres import require
from tests.integration.product_database_fixture import database


def main():
    with database() as db:
        expired, live = db.workspace(), db.workspace()
        # Simulated time boundary in disposable test metadata only, never production.
        db.sql("UPDATE pf_product.workspaces SET created_at=clock_timestamp()-interval '2 hours', "
               "expires_at=clock_timestamp()-interval '1 second' "
               "WHERE id=:'w';", "admin", **expired)
        db.expect("SELECT pf_product.retention_plan();", "permission denied")
        db.expect("SELECT pf_product.retention_plan_before_operator_expiry();",
                  "permission denied", "provisioner")
        plans = json.loads(db.sql("SELECT pf_product.retention_plan();", "provisioner"))
        require(len(plans) == 1 and plans[0]["workspace"] == expired["w"], "EXPIRY_SCOPE")
        db.expect("SELECT * FROM pf_product.session_context(:'s');", "ACCESS_DENIED", **expired)
        require(live["w"] in db.sql("SELECT * FROM pf_product.session_context(:'s');", **live),
                "UNEXPIRED_WORKSPACE_REVOKED")
        require(json.loads(db.sql("SELECT pf_product.retention_plan();", "provisioner")) == plans,
                "PLAN_REPLAY_CHANGED")
        db.sql("SELECT pf_product.complete_deletion(:'w',:'d');", "provisioner", **expired,
               d=plans[0]["manifest_sha256"])
        db.expect("SELECT pf_product.create_workspace(:'w','operator',"
                  "clock_timestamp()+interval '1 hour');", "WORKSPACE_DELETED", "provisioner",
                  **expired)
        require(json.loads(db.sql("SELECT pf_product.retention_plan();", "provisioner")) == [],
                "COMPLETED_DELETION_REOFFERED")
    print(json.dumps({"operator_expiry_checks": 7, "disposable_database_cleanup": True}))


if __name__ == "__main__":
    main()
