"""Disposable PostgreSQL retention/auth tests, labeled synthetic metadata only."""

import json
from uuid import uuid4

from scripts.check_budget_postgres import require
from scripts.check_product_queue import APPROVE, BEGIN, CLAIM, ENQUEUE, FAIL
from tests.integration.product_database_fixture import database


def main():
    checks = []
    with database() as db:
        one, other = db.workspace(), db.workspace()
        for key in ("s", "c"):
            db.expect(
                "SELECT * FROM pf_product.browser_session(:'s',:'c');",
                "ACCESS_DENIED",
                **{**one, key: other[key]},
            )
        require(
            one["w"] in db.sql("SELECT * FROM pf_product.browser_session(:'s',:'c');", **one),
            "Valid browser import rejected",
        )
        checks.append("exact_preprovisioned_browser_pair_only")
        assets = {
            k: db.asset(one, k) for k in ("pipeline", "transactions", "customers", "contract")
        }
        db.sql(APPROVE, **assets["contract"])
        db.sql(
            "SELECT pf_product.configure_execution(repeat('b',64),repeat('c',64),true);",
            "provisioner",
        )
        job = {
            **one,
            "j": str(uuid4()),
            "i": str(uuid4()),
            "p": assets["pipeline"]["a"],
            "t": assets["transactions"]["a"],
            "u": assets["customers"]["a"],
            "a": assets["contract"]["a"],
        }
        db.sql(ENQUEUE, **job)
        owner = str(uuid4())
        row = json.loads(db.sql(CLAIM, "dispatcher", o=owner))
        lease = {**job, "o": owner, "g": row["generation"], "e": str(uuid4()), "m": "d" * 64}
        db.sql(BEGIN, "dispatcher", **lease)
        db.sql("SELECT pf_product.request_deletion(:'w',:'s',:'c');", **one)
        db.expect("SELECT * FROM pf_product.session_context(:'s');", "ACCESS_DENIED", **one)
        require(
            json.loads(db.sql("SELECT pf_product.retention_plan();", "provisioner")) == [],
            "Running execution permitted byte deletion",
        )
        db.expect("SELECT pf_product.retention_plan();", "permission denied")
        checks.append("revocation_first_running_cleanup_gate_api_denied_maintenance")
        receipt = {
            "execution": lease["e"].replace("-", ""),
            "job": job["j"].replace("-", ""),
            "generation": lease["g"],
            "manifest": lease["m"],
            "cleanup": "confirmed",
        }
        db.sql(FAIL, "dispatcher", **lease, termination=json.dumps(receipt))
        plans = json.loads(db.sql("SELECT pf_product.retention_plan();", "provisioner"))
        require(len(plans) == 1 and plans[0]["jobs"] == [job["j"]], "Wrong deletion manifest")
        db.expect(
            "SELECT pf_product.complete_deletion(:'w',repeat('a',64));",
            "RETENTION_MANIFEST_MISMATCH",
            "provisioner",
            **one,
        )
        db.sql(
            "SELECT pf_product.complete_deletion(:'w',:'d');",
            "provisioner",
            **one,
            d=plans[0]["manifest_sha256"],
        )
        require(
            db.sql("SELECT count(*) FROM pf_product.workspaces WHERE id=:'w';", "admin", **one)
            == "0",
            "Raw registry retained after acknowledged cleanup",
        )
        db.expect(
            "SELECT pf_product.create_workspace(:'w','operator',"
            "clock_timestamp()+interval '1 hour');",
            "WORKSPACE_DELETED",
            "provisioner",
            **one,
        )
        require(
            other["w"] in db.sql("SELECT * FROM pf_product.session_context(:'s');", **other),
            "Unrelated workspace deleted",
        )
        checks.append("manifest_bound_metadata_erasure_tombstone_and_foreign_preservation")
        guest = str(uuid4())
        db.sql(
            "SELECT pf_product.create_workspace(:'w','guest',"
            "clock_timestamp()+interval '2 minutes');",
            "provisioner",
            w=guest,
        )
        plans = json.loads(db.sql("SELECT pf_product.retention_plan();", "provisioner"))
        require(len(plans) == 1 and plans[0]["workspace"] == guest, "Guest expiry not scheduled")
        checks.append("guest_expiry_margin_operator_evidence_preserved")
    print(
        json.dumps({"passed": len(checks), "checks": checks, "scope": "disposable_metadata_only"})
    )


if __name__ == "__main__":
    main()
