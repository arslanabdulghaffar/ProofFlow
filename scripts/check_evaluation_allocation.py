"""Disposable PostgreSQL checks: shared pilot allocation, cap, replay and concurrency."""

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from scripts.check_budget_postgres import require
from tests.integration.product_database_fixture import database


def main():
    with database() as db:
        query = "SELECT pf_product.reserve_evaluation(:'id',:'digest',:'amount');"
        value = {"id": str(uuid4()), "digest": "a" * 64, "amount": 1200000}
        db.expect(query, "permission denied", **value)
        db.expect(query, "permission denied", "dispatcher", **value)
        db.expect("SELECT * FROM pf_product.evaluation_allocations;", "permission denied",
                  "provisioner")
        require(db.sql(query, "provisioner", **value) == "t", "FIRST_ALLOCATION")
        require(db.sql(query, "provisioner", **value) == "f", "REPLAY_NOT_IDEMPOTENT")
        db.expect(query, "EVALUATION_ALLOCATION_CONFLICT", "provisioner",
                  **{**value, "digest": "b" * 64})
        db.expect(query, "EVALUATION_ALLOCATION_INVALID", "provisioner",
                  **{**value, "amount": 1200001})
        # Three concurrent full allocations fit; a fourth cannot cross $5.
        def allocate(_):
            try:
                return db.sql(query, "provisioner", **{**value, "id": str(uuid4())})
            except subprocess.CalledProcessError as error:
                require("REPAIR_DEVELOPMENT_ALLOCATION" in error.stderr, "UNEXPECTED_FAILURE")
                return "cap"

        with ThreadPoolExecutor(max_workers=4) as pool:
            outcomes = list(pool.map(allocate, range(4)))
        require(sorted(outcomes) == ["cap", "t", "t", "t"], "CONCURRENT_CAP_FAILED")
        require(db.sql("SELECT reserved_micro FROM pf_product.repair_allocation;", "admin")
                == "4800000", "SHARED_ALLOCATION_CHANGED")
        # A prior product allocation participates in the same unchanged envelope.
        db.sql(query, "provisioner", **{**value, "id": str(uuid4()), "amount": 200000})
        db.expect(query, "REPAIR_DEVELOPMENT_ALLOCATION", "provisioner",
                  **{**value, "id": str(uuid4()), "amount": 1})
        require(db.sql(query, "provisioner", **value) == "f", "FULL_CAP_REPLAY_FAILED")
    print(json.dumps({"evaluation_allocation_checks": 11, "disposable_database_cleanup": True}))


if __name__ == "__main__":
    main()
