"""Real disposable SQL tests for expiry without workspace identity resurrection."""

import json
from uuid import uuid4

from scripts.check_budget_postgres import require
from tests.integration.product_database_fixture import database


def main():
    with database() as db:
        db.expect("SELECT pf_product.prune_deletion_metadata();",
                  "RETENTION_EXPIRY_NOT_ENABLED", "provisioner")
        db.sql("SELECT pf_product.configure_execution(:'runtime',:'verifier',false); "
               "SELECT pf_product.enable_retention_expiry(:'runtime');", "provisioner",
               runtime="a" * 64, verifier="b" * 64)
        item, pending = db.workspace(), db.workspace()
        db.sql("SELECT pf_product.request_deletion(:'w',:'s',:'c');", **item)
        plan = json.loads(db.sql("SELECT pf_product.retention_plan();", "provisioner"))[0]
        db.sql("SELECT pf_product.complete_deletion(:'w',:'d');", "provisioner", **item,
               d=plan["manifest_sha256"])
        db.sql("SELECT pf_product.request_deletion(:'w',:'s',:'c');", **pending)
        db.expect("SELECT pf_product.prune_deletion_metadata();", "permission denied")
        require(db.sql("SELECT pf_product.prune_deletion_metadata();", "provisioner") == "0",
                "Early deletion record expiry")
        legacy = str(uuid4())
        # Labeled historical metadata and simulated future time, only in this fixture.
        db.sql("INSERT INTO pf_product.deletions(workspace_id,reason,completed_at) "
               "VALUES(:'w','owner',clock_timestamp()-interval '8 days');", "admin", w=legacy)
        require(db.sql("SELECT pf_product.prune_deletion_metadata();", "provisioner") == "1",
                "Legacy tombstone not retired")
        db.expect("SELECT pf_product.create_workspace(:'w','operator',"
                  "clock_timestamp()+interval '1 hour');", "FRESH_WORKSPACE_ID_REQUIRED",
                  "provisioner", w=legacy)
        db.sql("UPDATE pf_product.retention_clock "
               "SET observed_at=clock_timestamp()+interval '8 days';",
               "admin")
        require(db.sql("SELECT pf_product.prune_deletion_metadata();", "provisioner") == "1",
                "Expired completed deletion not retired")
        db.expect("SELECT pf_product.create_workspace(:'w','operator',"
                  "clock_timestamp()+interval '1 hour');", "FRESH_WORKSPACE_ID_REQUIRED",
                  "provisioner", **item)
        require(db.sql("SELECT count(*) FROM pf_product.deletions WHERE workspace_id=:'w';",
                       "admin", **pending) == "1", "Pending deletion was pruned")
        require(db.sql("SELECT pf_product.prune_deletion_metadata();", "provisioner") == "0",
                "Expiry replay changed result")
        db.expect("SELECT pf_product.create_workspace(uuidv7(),'operator',"
                  "clock_timestamp()+interval '1 hour');", "FRESH_WORKSPACE_ID_REQUIRED",
                  "provisioner")  # Clock rollback cannot make old time current again.
    print(json.dumps({"deletion_expiry_groups": 7, "scope": "disposable_real_postgres",
                      "cleanup": "confirmed", "cloud_calls": 0}))


if __name__ == "__main__":
    main()
