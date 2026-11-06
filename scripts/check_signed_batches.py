"""Real PostgreSQL delivery/replay races with inert fixtures. No worker or HTTP call."""

import json
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

from scripts.check_budget_postgres import require
from scripts.check_product_queue import APPROVE
from scripts.check_versions_batches import ACTIVATE, preview, verified_fixture
from tests.integration.product_database_fixture import database

ACCEPT = (
    "SELECT pf_product.accept_batch_event(:'connection',:'event',:'stamp',:'digest',:'t',:'u');"
)


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
        db.sql(ACTIVATE, **preview(db, first))
        values = {
            **first,
            "connection": str(uuid4()),
            "event": str(uuid4()),
            "stamp": int(time.time()),
            "digest": "a" * 64,
            "t": assets["transactions"]["a"],
            "u": assets["customers"]["a"],
        }
        provision = ("SELECT pf_product.provision_batch_connection(:'w',:'s',:'pipeline',"
                     ":'connection',clock_timestamp()+interval '30 minutes');")
        db.expect(provision, "permission denied", **values)
        db.expect(provision, "ACCESS_DENIED", "provisioner", **{**values, "s": foreign["s"]})
        db.sql(provision, "provisioner", **values)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(db.sql, ACCEPT, **values) for _ in range(2)]
            responses = [json.loads(f.result()) for f in futures]
        require(
            len({r["batch_id"] for r in responses}) == 1
            and sorted(r["already_accepted"] for r in responses) == [False, True],
            "Concurrent duplicate delivery did not share one batch",
        )
        checks.append("concurrent_signed_delivery_atomic_receipt_and_single_batch")
        batch = responses[0]["batch_id"]
        batch_identity = UUID(batch)
        require(batch_identity.version == 7
                and abs((batch_identity.int >> 80) / 1000 - time.time()) < 60,
                "Signed batch did not receive a fresh time-bound worker identity")
        db.expect(ACCEPT, "BATCH_DELIVERY_CONFLICT", **{**values, "digest": "b" * 64})
        db.expect(ACCEPT, "BATCH_DELIVERY_INVALID", **{**values, "stamp": int(time.time()) - 301})
        db.expect(
            ACCEPT,
            "JOB_ASSETS_INVALID",
            **{**values, "event": str(uuid4()), "t": db.asset(foreign, "transactions")["a"]},
        )
        checks.append("changed_body_stale_timestamp_and_foreign_assets_denied")
        second = verified_fixture(db, owner, assets, "second inert source")
        db.sql(ACTIVATE, **preview(db, second))
        replay = json.loads(db.sql(ACCEPT, **values))
        require(
            replay["batch_id"] == batch and replay["already_accepted"], "Activation rebound retry"
        )
        newer = json.loads(db.sql(ACCEPT, **{**values, "event": str(uuid4())}))
        require(
            db.sql(
                "SELECT version_id FROM pf_product.batches WHERE id=:'batch';", "admin", batch=batch
            )
            == first["r"],
            "Prior batch version changed",
        )
        require(
            db.sql(
                "SELECT version_id FROM pf_product.batches WHERE id=:'batch';",
                "admin",
                batch=newer["batch_id"],
            )
            == second["r"],
            "Fresh event did not bind current approved version",
        )
        checks.append("activation_preserves_old_delivery_assignment_new_event_binds_current")
        db.sql("SELECT pf_product.revoke_batch_connection(:'w',:'s',:'c',:'connection');", **values)
        db.expect(ACCEPT, "BATCH_CONNECTION_UNAVAILABLE", **values)
        require(
            db.sql(
                "SELECT bool_and(j.cancel_requested) FROM pf_product.jobs j "
                "JOIN pf_product.batch_deliveries d "
                "ON d.workspace_id=j.workspace_id AND d.batch_id=j.id;",
                "admin",
            )
            == "t",
            "Revocation left queued work active",
        )
        db.sql(
            "SELECT pf_product.claim_original(:'controller');",
            "dispatcher",
            controller=str(uuid4()),
        )
        # The queue visits one job per workspace per polling tick.
        db.sql("SELECT pf_product.claim_original(:'controller');",
               "dispatcher", controller=str(uuid4()))
        require(
            db.sql(
                "SELECT bool_and(j.state='CANCELLED') FROM pf_product.jobs j "
                "JOIN pf_product.batch_deliveries d "
                "ON d.workspace_id=j.workspace_id AND d.batch_id=j.id;",
                "admin",
            )
            == "t",
            "Revoked queued delivery executed",
        )
        checks.append("connection_revocation_stops_new_events_and_cancels_queued_batches")
    print(
        json.dumps(
            {
                "status": "passed",
                "checks": checks,
                "worker_provider_calls": 0,
                "fixture": "real_sql_inert_source",
            }
        )
    )


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        raise RuntimeError(error.stderr) from None
