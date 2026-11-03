"""Disposable real PostgreSQL identity/asset authorization tests, no cloud use.

Only trusted SQL runs. Test-only local trust authentication has no published
port/network/host mount or real credential; this is not a deployment auth claim.
"""

import hashlib
import json
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from scripts.check_budget_postgres import docker, require

IMAGE = "sha256:9ed8d24e2d804f04bd228a4619c9ed43c3a8d2f4a09fe947b44b112615eb010d"


def main():
    token = uuid.uuid4().hex
    name = "proofflow-product-test-" + token
    volume = name + "-data"
    label = "proofflow.product-test=" + token
    checks = []

    def sql(statement, role="api", database="proofflow_product", **params):
        user = {"api": "fixture_api", "provisioner": "fixture_provisioner",
                "admin": "postgres", "public": "fixture_public"}[role]
        bindings = []
        for key, value in params.items():
            require(key.isidentifier(), "Invalid fixture binding")
            bindings.extend(("--set", key + "=" + str(value)))
        return docker("exec", "-i", "--user", "70:70", name,
                      "psql", "-X", "-qAt", "-U", user, "-d", database,
                      "--set", "ON_ERROR_STOP=1", *bindings,
                      stdin="SET statement_timeout='5s'; SET lock_timeout='3s';\n" + statement)

    def expect(statement, code, role="api", **params):
        try:
            sql(statement, role, **params)
        except subprocess.CalledProcessError as error:
            require(code in error.stderr, "Unexpected fixed database diagnostic")
        else:
            raise RuntimeError("Expected rejection missing: " + code)

    def workspace(kind="operator"):
        identifier = str(uuid.uuid4())
        sql("SELECT pf_product.create_workspace(:'w',:'kind',"
            "clock_timestamp()+interval '23 hours');",
            "provisioner", w=identifier, kind=kind)
        session = hashlib.sha256((identifier + "session").encode()).hexdigest()
        csrf = hashlib.sha256((identifier + "csrf").encode()).hexdigest()
        sql("SELECT pf_product.create_session(:'w',:'s',:'c',"
            "clock_timestamp()+interval '50 minutes');",
            "provisioner", w=identifier, s=session, c=csrf)
        return {"w": identifier, "s": session, "c": csrf}

    register = "SELECT pf_product.register_asset(:'w',:'s',:'c',:'a',:'k',:'d',:'n');"
    get = "SELECT * FROM pf_product.get_asset(:'w',:'s',:'a');"

    def asset(context, *, identifier=None, size=1, kind="pipeline"):
        return {**context, "a": identifier or str(uuid.uuid4()), "k": kind,
                "d": hashlib.sha256(b"synthetic registry fixture").hexdigest(), "n": size}

    def wait_sleep():
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if sql("SELECT count(*) FROM pg_stat_activity WHERE wait_event='PgSleep' "
                   "AND datname='proofflow_product';", "admin") != "0":
                return
            time.sleep(0.02)
        raise RuntimeError("Fixture transaction failed to reach lock-holding point")

    try:
        docker("volume", "create", "--label", label, volume)
        docker("create", "--pull=never", "--name", name, "--label", label, "--network", "none",
               "--user", "70:70", "--cap-drop", "ALL", "--read-only", "--memory", "512m",
               "--memory-swap", "512m", "--cpus", "1", "--pids-limit", "128",
               "--security-opt", "no-new-privileges",
               "--tmpfs", "/var/run/postgresql:rw,noexec,nosuid,nodev,"
                          "uid=70,gid=70,mode=0770,size=1m",
               "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=16m",  # noqa: S108 - isolated tmpfs
               "--mount", f"type=volume,source={volume},target=/var/lib/postgresql",
               "-e", "POSTGRES_DB=proofflow_product", "-e", "POSTGRES_HOST_AUTH_METHOD=trust",
               IMAGE, "postgres", "-c", "listen_addresses=")
        docker("start", name)
        for _ in range(100):
            try:
                if sql("SELECT 1;", "admin") == "1":
                    break
            except subprocess.CalledProcessError:
                pass
            time.sleep(0.1)
        else:
            raise RuntimeError("Private test PostgreSQL did not start")
        config = json.loads(docker("inspect", name))[0]
        require(config["Image"] == IMAGE and config["HostConfig"]["NetworkMode"] == "none"
                and not config["HostConfig"]["PortBindings"] and config["Config"]["User"] == "70:70"
                and config["HostConfig"]["ReadonlyRootfs"]
                and all(mount["Type"] in ("volume", "tmpfs") for mount in config["Mounts"]),
                "Unexpected private fixture topology")
        require(sql("SHOW fsync; SHOW synchronous_commit;", "admin") == "on\non",
                "Fixture durability settings invalid")
        sql(Path("db/phase2/001_identity_assets.sql").read_text(encoding="utf-8"), "admin")
        sql("CREATE ROLE fixture_api LOGIN IN ROLE pf_product_api; "
            "CREATE ROLE fixture_provisioner LOGIN IN ROLE pf_product_provisioner; "
            "CREATE ROLE fixture_public LOGIN; "
            "GRANT CONNECT ON DATABASE proofflow_product "
            "TO fixture_api,fixture_provisioner,fixture_public;", "admin")
        checks.append("pinned_private_postgres_migration_durability")
        one, two = workspace(), workspace("guest")
        first = asset(one)
        require(sql(register, **first) == "t", "First registry insert missing")
        require(sql(register, **first) == "f", "Idempotent registration changed")
        expect(register, "ASSET_IDEMPOTENCY_CONFLICT", **{**first, "d": "f" * 64})
        require(sql(get, **first) == "pipeline|" + first["d"] + "|1", "Exact asset read failed")
        require(sql(get, **{**two, "a": first["a"]}) == "", "Cross-workspace asset leaked")
        expect(get, "ACCESS_DENIED", **{**first, "s": two["s"]})
        expect(register, "ACCESS_DENIED", **{**first, "c": two["c"]})
        expect(register.replace(":'c'", "NULL"), "ACCESS_DENIED", **first)
        expect(register, "ACCESS_DENIED", **{**first, "s": "0" * 64})
        require(sql("SELECT workspace_id,session_kind FROM pf_product.session_context(:'s');",
                    **one) == one["w"] + "|operator", "Session context mismatch")
        checks.append("scoped_immutable_registry_idempotency_and_csrf")
        for statement in ("SELECT * FROM pf_product.sessions;", "SELECT * FROM pf_product.assets;",
                          "UPDATE pf_product.assets SET byte_size=1;",
                          "SET ROLE pf_product_owner;",
                          "SELECT pf_product.require_transaction();",
                          "SELECT pf_product.authorize(NULL,NULL,NULL,false);",
                          "SELECT pf_product.create_workspace(NULL,NULL,NULL);",
                          "CREATE TEMP TABLE sessions(x int);"):
            expect(statement, "permission denied")
        expect("SELECT pf_product.session_context(NULL);", "permission denied", "public")
        expect("BEGIN ISOLATION LEVEL REPEATABLE READ; "
               "SELECT * FROM pf_product.session_context(:'s');",
               "PRODUCT_TRANSACTION_POLICY", **one)
        expect("SET synchronous_commit=off; SELECT * FROM pf_product.session_context(:'s');",
               "PRODUCT_TRANSACTION_POLICY", **one)
        expect("SELECT pf_product.create_session(:'w',:'s',:'c',"
               "clock_timestamp()+interval '2 hours');", "INVALID_SESSION", "provisioner",
               **{**two, "s": "d" * 64})
        checks.append("no_table_owner_provisioner_public_or_transaction_bypass")
        for size, kind in ((16385, "pipeline"), (32769, "contract"), (5242881, "customers"),
                           (0, "pipeline"), (1, "ledger")):
            expect(register, "INVALID_ASSET", **asset(one, size=size, kind=kind))
        for digest in ("a" * 64 + "\n", "A" * 64, "a" * 63, "../" + "a" * 61):
            expect(register, "INVALID_ASSET", **{**asset(one), "d": digest})
        checks.append("fixed_asset_kind_and_byte_bounds")
        # Fill to63 objects, then race eight independent connections for one slot.
        for _ in range(62):
            sql(register, **asset(one))

        def race_add(_):
            try:
                return sql(register, **asset(one))
            except subprocess.CalledProcessError as error:
                require("ASSET_QUOTA" in error.stderr, "Unexpected quota race failure")
                return "quota"

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(race_add, range(8)))
        require(results.count("t") == 1 and results.count("quota") == 7,
                "Concurrent quota admitted excess objects")
        require(sql(register, **first) == "f", "Exact retry failed at full quota")
        for _ in range(25):
            sql(register, **asset(two, size=5242880, kind="transactions"))
        expect(register, "ASSET_QUOTA", **asset(two, size=5242880, kind="transactions"))
        checks.append("atomic_count_and_byte_quota_concurrency")
        three = workspace()
        sql("SELECT pf_product.revoke_session(:'w',:'s',:'c');", **three)
        expect("SELECT * FROM pf_product.session_context(:'s');", "ACCESS_DENIED", **three)
        expect(register, "ACCESS_DENIED", **asset(three))
        four = workspace()
        sql("UPDATE pf_product.sessions SET created_at=clock_timestamp()-interval '2 hours',"
            "expires_at=clock_timestamp()-interval '1 hour' WHERE token_hash=:'s';",
            "admin", **four)
        expect(get, "ACCESS_DENIED", **asset(four))
        checks.append("session_revocation_and_expiry_fail_closed")
        five = workspace()
        with ThreadPoolExecutor(max_workers=2) as pool:
            writer = pool.submit(sql, "BEGIN; " + register + " SELECT pg_sleep(0.7); COMMIT;",
                                 **asset(five))
            wait_sleep()
            revoker = pool.submit(sql, "SELECT pf_product.revoke_workspace(:'w');",
                                  "provisioner", **five)
            writer.result(timeout=5)
            revoker.result(timeout=5)
        expect(get, "ACCESS_DENIED", **asset(five))
        six = workspace()
        with ThreadPoolExecutor(max_workers=2) as pool:
            revoker = pool.submit(sql, "BEGIN; SELECT pf_product.revoke_workspace(:'w'); "
                                 "SELECT pg_sleep(0.7); COMMIT;", "provisioner", **six)
            wait_sleep()
            expect(register, "ACCESS_DENIED", **asset(six))
            revoker.result(timeout=5)
        checks.append("workspace_revoke_serializes_with_both_race_orders")
        seven = workspace()
        sql("UPDATE pf_product.workspaces SET created_at=clock_timestamp()-interval '2 hours',"
            "expires_at=clock_timestamp()-interval '1 hour' WHERE id=:'w';", "admin", **seven)
        expect(get, "ACCESS_DENIED", **asset(seven))
        eight = workspace()
        expect("SELECT pf_product.create_workspace(:'w','guest',"
               "clock_timestamp()+interval '1 hour');", "WORKSPACE_CAPACITY", "provisioner",
               w=str(uuid.uuid4()))
        sql("SELECT pf_product.create_session(:'w',lpad(to_hex(i),64,'0'),repeat('e',64),"
            "clock_timestamp()+interval '50 minutes') FROM generate_series(1,31) AS i;",
            "provisioner", **eight)
        expect("SELECT pf_product.create_session(:'w',repeat('d',64),repeat('e',64),"
               "clock_timestamp()+interval '50 minutes');", "SESSION_CAPACITY", "provisioner",
               **eight)
        checks.append("workspace_expiry_and_fixed_workspace_session_capacity")
        # Same immutable registry and authorization survive real dump/restore.
        dump = docker("exec", "--user", "70:70", name, "pg_dump", "-U", "postgres",
                      "--no-comments", "proofflow_product")
        docker("exec", "--user", "70:70", name, "createdb", "-U", "postgres", "product_restore")
        sql(dump, "admin", database="product_restore")
        require(sql(get, database="product_restore", **first)
                == sql(get, **first), "Restored registry differs")
        expect("SELECT pf_product.register_asset(:'w',:'s',:'c',:'a',:'k',:'d',:'n');",
               "ACCESS_DENIED", database="product_restore", **asset(six))
        checks.append("dump_restore_preserves_ownership_and_revocation")
    finally:
        if docker("ps", "-aq", "--filter", "name=^/" + name + "$"):
            info = json.loads(docker("inspect", name))[0]
            require(info["Config"]["Labels"].get("proofflow.product-test") == token,
                    "Refusing to remove foreign container")
            docker("rm", "--force", name)
        if docker("volume", "ls", "-q", "--filter", "name=^" + volume + "$"):
            info = json.loads(docker("volume", "inspect", volume))[0]
            require(info["Labels"].get("proofflow.product-test") == token,
                    "Refusing to remove foreign volume")
            docker("volume", "rm", volume)
        require(not docker("ps", "-aq", "--filter", "name=^/" + name + "$")
                and not docker("volume", "ls", "-q", "--filter", "name=^" + volume + "$"),
                "Private test fixture cleanup failed")
    checks.append("owned_fixture_cleanup_confirmed")
    print(json.dumps({
        "scope": "local_trusted_postgres_only", "image": IMAGE,
        "checks": checks, "candidate_execution": False, "deployed_authentication": "NOT_RUN",
        "observed_at": datetime.now(UTC).isoformat(),
        "migration_sha256": hashlib.sha256(
            Path("db/phase2/001_identity_assets.sql").read_bytes()).hexdigest(),
    }, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as failure:
        # This helper creates only disposable synthetic fixture data; never use
        # this diagnostic behavior for the production DB client.
        print(failure.stderr[:2000])
        raise SystemExit(1) from None
