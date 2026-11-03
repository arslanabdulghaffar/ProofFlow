"""Trusted local PostgreSQL budget checks, no candidate execution or cloud use.

Creates and removes its own labeled container/volume. Requires Linux Docker and
the exact official image below. No ports/host mounts/network/secrets are used.
Local trust authentication is strictly a disposable test fixture, never deploy it.
"""

import argparse
import json
import re
import shutil
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

IMAGE = (
    "postgres:18.6-trixie@sha256:"
    "f4b419e350fd98d4a8429603295208976dea4c8fb8326d818d346d3e29f1db6f"
)
DIGEST = "a" * 64
EVIDENCE = "b" * 64


def docker(*args: str, stdin: str | None = None, timeout: int = 45) -> str:
    executable = shutil.which("docker")
    if executable is None:
        raise RuntimeError("Docker is required")
    return subprocess.run(  # noqa: S603 - fixed trusted Docker commands and generated IDs
        [executable, *args], input=stdin, check=True, capture_output=True,
        text=True, timeout=timeout,
    ).stdout.strip()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-image",
                        help="Reviewed trusted client image ID; never a candidate")
    arguments = parser.parse_args()
    if arguments.client_image and not re.fullmatch(r"sha256:[a-f0-9]{64}", arguments.client_image):
        raise ValueError("Exact trusted client image ID required")
    token = uuid.uuid4().hex
    name = "proofflow-budget-test-" + token
    client_name = name + "-client"
    volume = name + "-data"
    label = "proofflow.budget-test=" + token
    receipt = {"scope": "local_trusted_postgres_only", "image": IMAGE, "checks": []}
    request_deadlines = {}

    def sql(statement: str, role: str | None = "pf_budget_dispatcher", **params) -> str:
        require(role in (None, "pf_budget_dispatcher", "pf_budget_reconciler", "pf_budget_public"),
                "Unapproved test role")
        user = {None: "postgres", "pf_budget_dispatcher": "pf_budget_test_dispatch",
                "pf_budget_reconciler": "pf_budget_test_reconcile",
                "pf_budget_public": "pf_budget_public"}[role]
        bindings = []
        for key, value in params.items():
            require(key.isidentifier(), "Invalid test variable name")
            bindings.extend(("--set", key + "=" + str(value)))
        return docker("exec", "-i", name, "psql", "-X", "-qAt", "-U", user,
                      "-d", "postgres", "--set", "ON_ERROR_STOP=1", *bindings, stdin=statement)

    def expect_error(statement: str, code: str, role: str | None = "pf_budget_dispatcher"):
        try:
            sql(statement, role)
        except subprocess.CalledProcessError as error:
            require(code in error.stderr, "Unexpected database rejection")
        else:
            raise RuntimeError("Expected rejection: " + code)

    def account(project=100, inference=80, probe=20, expired=False):
        identifier = str(uuid.uuid4())
        age = "-1 hour" if expired else "1 hour"
        sql("INSERT INTO pf_budget.accounts VALUES (:'identifier', :'project'::bigint, "
            ":'inference'::bigint, :'probe'::bigint, clock_timestamp() + :'age'::interval, false);",
            None, identifier=identifier, project=project, inference=inference, probe=probe, age=age)
        return identifier

    def reserve(a, request, amount=1, category="probe", digest=DIGEST):
        deadline = request_deadlines.setdefault(
            request, (datetime.now(UTC) + timedelta(minutes=10)).isoformat(),
        )
        return (f"SELECT pf_budget.reserve('{a}','{request}','{digest}',"
                f"'{category}',{amount},'{deadline}');")

    def claim(a, request):
        return f"SELECT pf_budget.claim('{a}','{request}','{DIGEST}');"

    def settle(a, request, amount, evidence=EVIDENCE):
        return f"SELECT pf_budget.settle('{a}','{request}',{amount},'{evidence}');"

    def ready():
        deadline = time.monotonic() + 40
        while True:
            try:
                if (docker("exec", name, "cat", "/proc/1/comm") == "postgres"
                        and sql("SELECT 1;", None) == "1"):
                    return
            except subprocess.CalledProcessError:
                pass
            if time.monotonic() >= deadline:
                raise RuntimeError("Local test database did not become ready")
            time.sleep(0.25)

    def passed(check):
        receipt["checks"].append(check)

    try:
        docker("image", "inspect", IMAGE)  # No implicit pull or unpinned fallback.
        docker("volume", "create", "--label", label, volume)
        docker("create", "--name", name, "--label", label, "--network", "none",
               "--memory", "512m", "--cpus", "1", "--pids-limit", "128",
               "--security-opt", "no-new-privileges",
               "--mount", f"type=volume,source={volume},target=/var/lib/postgresql",
               "-e", "POSTGRES_HOST_AUTH_METHOD=trust", IMAGE,
               "postgres", "-c", "listen_addresses=", "-c",
               "unix_socket_directories=/var/run/postgresql,/var/lib/postgresql")
        docker("start", name)
        ready()
        config = json.loads(docker("inspect", name))[0]
        require(config["HostConfig"]["NetworkMode"] == "none"
                and not config["HostConfig"]["PortBindings"]
                and len(config["Mounts"]) == 1
                and config["Mounts"][0]["Type"] == "volume"
                and config["Mounts"][0]["Name"] == volume, "Unexpected test topology")
        receipt["server_version"] = sql("SHOW server_version;", None)
        require(sql("SHOW fsync; SHOW synchronous_commit;", None) == "on\non",
                "Durability settings disabled")
        migration = Path(__file__).resolve().parent.parent / "db/phase1/001_budget.sql"
        sql(migration.read_text(encoding="utf-8"), None)
        sql("CREATE ROLE pf_budget_public LOGIN; "
            "CREATE ROLE pf_budget_test_dispatch LOGIN IN ROLE pf_budget_dispatcher; "
            "CREATE ROLE pf_budget_test_reconcile LOGIN IN ROLE pf_budget_reconciler;", None)
        passed("pinned_server_private_topology_and_migration")

        a = account()
        r = str(uuid.uuid4())
        require(sql(reserve(a, r, 20)) == "t", "Initial reservation missing")
        require(sql(reserve(a, r, 20)) == "f", "Duplicate charged twice")
        expect_error(reserve(a, r, 19), "RESERVATION_CONFLICT")
        expect_error(reserve(a, r, 20, digest="c" * 64), "RESERVATION_CONFLICT")
        expect_error(reserve(a, str(uuid.uuid4())), "BUDGET_EXHAUSTED")
        passed("probe_cap_and_exact_intent_idempotency")

        require(sql(reserve(a, str(uuid.uuid4()), 60, "inference")) == "t", "Inference cap")
        expect_error(reserve(a, str(uuid.uuid4()), 1, "inference"), "BUDGET_EXHAUSTED")
        require(sql(reserve(a, str(uuid.uuid4()), 20, "compute")) == "t", "Project cap")
        expect_error(reserve(a, str(uuid.uuid4()), 1, "other"), "BUDGET_EXHAUSTED")
        passed("probe_inference_project_caps_share_accounting")

        a_race = account(10, 10, 10)
        def compete(_):
            try:
                return sql(reserve(a_race, str(uuid.uuid4())))
            except subprocess.CalledProcessError as error:
                require("BUDGET_EXHAUSTED" in error.stderr, "Unexpected race failure")
                return "rejected"
        with ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(pool.map(compete, range(20)))
        require(outcomes.count("t") == 10 and outcomes.count("rejected") == 10,
                "Concurrent reservations exceeded or lost budget")
        passed("20_concurrent_reservations_exactly_10_admitted")

        with ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(pool.map(lambda _: sql(claim(a, r)), range(12)))
        require(outcomes.count("t") == 1 and outcomes.count("f") == 11,
                "Intent claimed more than once")
        passed("12_concurrent_claims_exactly_one_dispatch_authorization")

        # Crash our disposable database AFTER durable claim, before settlement.
        docker("kill", "--signal", "KILL", name)
        docker("start", name)
        ready()
        require(sql(claim(a, r)) == "f", "Crash replayed uncertain dispatch")
        expect_error(reserve(a, str(uuid.uuid4())), "BUDGET_EXHAUSTED")
        require(sql("SELECT state FROM pf_budget.reservations WHERE id=:'identifier';",
                    None, identifier=r)
                == "uncertain", "Unknown charge was released")
        passed("uncertain_reservation_survives_database_crash_restart")

        require(sql(settle(a, r, 5), "pf_budget_reconciler") == "t", "Settlement failed")
        require(sql(settle(a, r, 5), "pf_budget_reconciler") == "f", "Settlement replayed")
        expect_error(settle(a, r, 4), "SETTLEMENT_CONFLICT", "pf_budget_reconciler")
        require(sql(reserve(a, str(uuid.uuid4()), 15)) == "t", "Confirmed credit not released")
        passed("settlement_idempotency_conflict_and_confirmed_release")

        a_over = account()
        r_over, r_wait = str(uuid.uuid4()), str(uuid.uuid4())
        sql(reserve(a_over, r_over))
        sql(reserve(a_over, r_wait))
        sql(claim(a_over, r_over))
        sql(settle(a_over, r_over, 3), "pf_budget_reconciler")
        require(sql("SELECT charged_micro FROM pf_budget.reservations WHERE id=:'identifier';",
                    None, identifier=r_over) == "3", "Overrun hidden")
        expect_error(reserve(a_over, str(uuid.uuid4())), "BUDGET_ADMISSION_CLOSED")
        expect_error(claim(a_over, r_wait), "BUDGET_ADMISSION_CLOSED")
        passed("overrun_recorded_and_future_reserve_claim_blocked")

        expect_error("UPDATE pf_budget.accounts SET blocked=false;", "permission denied")
        expect_error("SELECT * FROM pf_budget.reservations;", "permission denied")
        expect_error(settle(a, r, 5), "permission denied")
        expect_error(reserve(a, str(uuid.uuid4())), "permission denied", "pf_budget_reconciler")
        expect_error(reserve(a, str(uuid.uuid4())), "permission denied", "pf_budget_public")
        expect_error("SET ROLE pf_budget_owner;", "permission denied", "pf_budget_dispatcher")
        passed("dispatcher_reconciler_public_role_boundaries")

        a_expired = account(expired=True)
        expect_error(reserve(a_expired, str(uuid.uuid4())), "BUDGET_ADMISSION_CLOSED")
        a_expire_claim = account()
        r_expire = str(uuid.uuid4())
        sql(reserve(a_expire_claim, r_expire))
        sql("UPDATE pf_budget.accounts SET expires_at=clock_timestamp()-interval '1 second' "
            "WHERE id=:'identifier';", None, identifier=a_expire_claim)
        expect_error(claim(a_expire_claim, r_expire), "BUDGET_ADMISSION_CLOSED")
        passed("expiry_rechecked_at_reservation_and_dispatch")

        a_short = account()
        r_short = str(uuid.uuid4())
        sql(reserve(a_short, r_short))
        sql("UPDATE pf_budget.reservations SET valid_until=clock_timestamp()-interval '1 second' "
            "WHERE id=:'identifier';", None, identifier=r_short)
        expect_error(claim(a_short, r_short), "RESERVATION_EXPIRED")
        r_bad_deadline = str(uuid.uuid4())
        request_deadlines[r_bad_deadline] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
        expect_error(reserve(a_short, r_bad_deadline), "INVALID_RESERVATION_DEADLINE")
        passed("request_quote_deadline_enforced_independently_of_account_expiry")

        a_invalid = account()
        for amount in (0, -1, 150000001):
            expect_error(reserve(a_invalid, str(uuid.uuid4()), amount), "INVALID_RESERVATION")
        expect_error(reserve(a_invalid, str(uuid.uuid4()), digest="z" * 64), "INVALID_RESERVATION")
        expect_error(reserve(a_invalid, str(uuid.uuid4()), category="gpu"), "INVALID_RESERVATION")
        r_unclaimed = str(uuid.uuid4())
        sql(reserve(a_invalid, r_unclaimed))
        expect_error(settle(a_invalid, r_unclaimed, 0), "RESERVATION_NOT_CLAIMED",
                     "pf_budget_reconciler")
        passed("invalid_amount_digest_purpose_and_unclaimed_settlement_rejected")

        r_rollback = str(uuid.uuid4())
        sql("BEGIN; " + reserve(a_invalid, r_rollback) + " ROLLBACK;")
        require(sql("SELECT count(*) FROM pf_budget.reservations WHERE id=:'identifier';",
                    None, identifier=r_rollback) == "0", "Rollback leaked reservation")
        passed("transaction_rollback_is_not_a_committed_reservation")

        for isolation in ("REPEATABLE READ", "SERIALIZABLE", "READ UNCOMMITTED"):
            for statement, role in ((reserve(a_invalid, str(uuid.uuid4())), None),
                                    (claim(a_invalid, r_unclaimed), None),
                                    (settle(a, r, 5), "pf_budget_reconciler")):
                expect_error("BEGIN ISOLATION LEVEL " + isolation + "; " + statement,
                             "BUDGET_REQUIRES_READ_COMMITTED",
                             role or "pf_budget_dispatcher")
        expect_error("SET synchronous_commit=off; " + reserve(a_invalid, str(uuid.uuid4())),
                     "BUDGET_REQUIRES_DURABLE_COMMIT")
        passed("stale_snapshot_isolation_and_nondurable_commit_settings_rejected")
        if arguments.client_image:
            docker("image", "inspect", arguments.client_image)
            client_account = account(150000000, 25000000, 2000000)
            docker("create", "--name", client_name, "--label", label,
                   "--network", "none", "--read-only", "--user", "10001:10001",
                   "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                   "--memory", "256m", "--cpus", "1", "--pids-limit", "32",
                   "--mount", f"type=volume,source={volume},target=/budgetdb,readonly",
                   arguments.client_image, "python3", "/app/budget_client_check.py", client_account)
            client = json.loads(docker("inspect", client_name))[0]
            host = client["HostConfig"]
            require(host["NetworkMode"] == "none" and not host["PortBindings"]
                    and host["ReadonlyRootfs"] and host["CapDrop"] == ["ALL"]
                    and host["Memory"] == 256 * 1024 * 1024
                    and host["NanoCpus"] == 1000000000 and host["PidsLimit"] == 32
                    and "no-new-privileges" in host["SecurityOpt"]
                    and client["Config"]["User"] == "10001:10001"
                    and len(client["Mounts"]) == 1
                    and client["Mounts"][0]["Name"] == volume
                    and client["Mounts"][0]["RW"] is False, "Unsafe client test configuration")
            result = docker("start", "--attach", client_name)
            state = json.loads(docker("inspect", client_name))[0]["State"]
            require(state["ExitCode"] == 0 and not state["Running"], "Client check failed")
            receipt["python_client"] = json.loads(result)
    finally:
        # Only remove generated test objects whose exact private label matches.
        if docker("ps", "-aq", "--filter", "name=^/" + client_name + "$"):
            item = json.loads(docker("inspect", client_name))[0]
            require(item["Config"]["Labels"].get("proofflow.budget-test") == token,
                    "Refusing unrelated client cleanup")
            docker("rm", "--force", client_name)
        found = docker("ps", "-aq", "--filter", "name=^/" + name + "$")
        if found:
            item = json.loads(docker("inspect", name))[0]
            require(item["Config"]["Labels"].get("proofflow.budget-test") == token,
                    "Refusing unrelated container cleanup")
            docker("rm", "--force", name)
        volumes = docker("volume", "ls", "--quiet", "--filter", "name=^" + volume + "$")
        if volumes:
            item = json.loads(docker("volume", "inspect", volume))[0]
            require(item["Labels"].get("proofflow.budget-test") == token,
                    "Refusing unrelated volume cleanup")
            docker("volume", "rm", volume)
        require(not docker("ps", "-aq", "--filter", "name=^/" + name + "$")
                and not docker("ps", "-aq", "--filter", "name=^/" + client_name + "$")
                and not docker("volume", "ls", "--quiet", "--filter", "name=^" + volume + "$")
                , "Test cleanup incomplete")
        receipt["cleanup"] = "container_and_volume_confirmed_absent"
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
