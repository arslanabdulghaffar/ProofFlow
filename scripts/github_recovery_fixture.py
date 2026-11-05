"""Disposable recovery scenario, never production state. JSON-lines stdin/stdout only.

The seed models a lost acknowledgement using an already confirmed real PR receipt.
It is NOT evidence that the original GitHub creation response was lost. After seed,
only unchanged product functions advance state; leases expire naturally.
"""

import json
import signal
import sys
from uuid import UUID

from scripts.check_budget_postgres import docker, require
from scripts.check_github_outbox import BEGIN, READBACK
from scripts.check_product_queue import APPROVE
from scripts.check_versions_batches import verified_fixture
from tests.integration.product_database_fixture import database

CALLS = {
    "pr_claim": ("SELECT pf_product.claim_pr(:'p0');", 1),
    "pr_readback": (
        "SELECT pf_product.record_pr_readback(:'p0',:'p1',:'p2',:'p3',:'p4',:'p5');", 6),
    "pr_defer": (
        "SELECT pf_product.defer_pr(:'p0',:'p1',:'p2',:'p3',:'p4',:'p5');", 6),
}


def seed(db, snapshot):
    prior, writes = snapshot["intent"], snapshot["writes"]
    require(prior["state"] == "COMPLETE" and len(writes) == 3
            and {w["stage"] for w in writes} == {"branch", "commit", "pr"}
            and all(w["confirmed_at"] is not None for w in writes), "CONFIRMED_SEED_REQUIRED")
    owner = db.workspace()
    assets = {k: db.asset(owner, k) for k in ("pipeline", "transactions", "customers", "contract")}
    db.sql(APPROVE, **assets["contract"])
    db.sql("SELECT pf_product.configure_execution(repeat('b',64),repeat('c',64),true);",
           "provisioner")
    version = verified_fixture(db, owner, assets, prior["preview"]["candidate_source"])
    db.sql("SELECT pf_product.configure_github(:'cfg',false);", "provisioner",
           cfg=json.dumps(prior["preview"]["configuration"]))
    # Explicit fixture initialization, with synthetic upstream proof/actor. Never
    # copy login credentials or activate this historical approval for writes.
    pending = {**prior, "workspace_id": owner["w"], "version_id": version["r"],
               "actor": owner["s"], "state": "PR_PENDING", "result": None,
               "lease_owner": None, "lease_until": None, "attempts": 0,
               "diagnostic": None}
    db.sql("INSERT INTO pf_product.pr_intents SELECT * FROM "
           "jsonb_populate_record(NULL::pf_product.pr_intents,:'row'::jsonb);",
           "admin", row=json.dumps(pending))
    for write in writes:
        value = {**write, "workspace_id": owner["w"]}
        if write["stage"] == "pr":
            value.update(confirmed_at=None, readback=None)
        db.sql("INSERT INTO pf_product.pr_writes SELECT * FROM "
               "jsonb_populate_record(NULL::pf_product.pr_writes,:'row'::jsonb);",
               "admin", row=json.dumps(value))
    return str(UUID(prior["id"]))


def snapshot(db, identity):
    return json.loads(db.sql(
        "SELECT jsonb_build_object('intent',to_jsonb(p),'writes',(SELECT jsonb_agg(to_jsonb(w) "
        "ORDER BY stage) FROM pf_product.pr_writes w WHERE w.intent_id=p.id)) "
        "FROM pf_product.pr_intents p WHERE p.id=:'id';", "admin", id=identity))


def serve(db):
    identity = None
    while line := sys.stdin.readline(1048577):
        require(len(line) <= 1048576 and line.endswith("\n"), "FIXTURE_FRAME_LIMIT")
        request = json.loads(line)
        operation = request["operation"]
        if operation == "close":
            return
        if operation == "seed":
            require(identity is None, "FIXTURE_ALREADY_SEEDED")
            identity = seed(db, request["snapshot"])
            result = snapshot(db, identity)
        else:
            require(identity is not None, "FIXTURE_SEED_REQUIRED")
            if operation == "call":
                name, args = request["name"], request["args"]
                require(name in CALLS, "READBACK_ONLY_OPERATION_REQUIRED")
                statement, count = CALLS[name]
                require(len(args) == count, "FIXTURE_CALL_ARITY")
                params = {"p" + str(i): json.dumps(v) if type(v) is dict else str(v)
                          for i, v in enumerate(args)}
                value = db.sql(statement, "dispatcher", **params)
                result = [json.loads(value) if value else None]
            elif operation == "snapshot":
                result = snapshot(db, identity)
            elif operation == "restart":
                docker("restart", db.name)
                result = {"restarted": True}
            elif operation in ("stale", "deny_write"):
                binding = request["binding"]
                require(str(UUID(binding["intent"])) == identity, "FIXTURE_INTENT_CHANGED")
                if operation == "stale":
                    db.expect(READBACK, "STALE_PR_LEASE", "dispatcher", **binding,
                              stage="pr", receipt=json.dumps(request["receipt"]))
                else:
                    db.expect(BEGIN, "PR_AUTHORITY_REVOKED", "dispatcher", **binding, stage="pr")
                result = {"rejected": True}
            else:
                raise RuntimeError("FIXTURE_OPERATION_NOT_ALLOWED")
        print(json.dumps({"result": result}), flush=True)


def main():
    def deadline(*_):
        raise RuntimeError("FIXTURE_DEADLINE")

    signal.signal(signal.SIGALRM, deadline)
    signal.alarm(900)
    with database() as db:
        print(json.dumps({"ready": True, "network": "none", "fixture": db.name}), flush=True)
        serve(db)
    print(json.dumps({"cleanup": "confirmed"}), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("DISPOSABLE_RECOVERY_FIXTURE_FAILED") from None
