"""Linux trusted-admin SQL rehearsal in a fresh networkless, RAM-only PostgreSQL.

Input must be the authenticated scheduled backup from check_saved_database_recovery.
This is NOT an upload endpoint or a way to execute a compromised/untrusted SQL dump.
No source program is imported/executed and no recovered database is promoted.
"""

import base64
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from uuid import uuid4

from orchestrator.restore_guard import (
    AUTHORITY_TABLES,
    check_dump,
    plan_restore,
    quarantine_sql,
    revalidate_restore,
)
from scripts.check_budget_postgres import docker, require
from scripts.check_product_postgres import IMAGE

TMPFS = {
    "/var/lib/postgresql": "rw,noexec,nosuid,nodev,uid=70,gid=70,mode=0700,size=256m",
    "/var/run/postgresql": "rw,noexec,nosuid,nodev,uid=70,gid=70,mode=0770,size=1m",
    "/tmp": "rw,noexec,nosuid,nodev,size=16m",  # noqa: S108 - container tmpfs
}


def validate_container(config):
    host = config["HostConfig"]
    require(config["Image"] == IMAGE and host["NetworkMode"] == "none"
            and not host["PortBindings"] and host["ReadonlyRootfs"]
            and host["Memory"] == host["MemorySwap"] == 512*1024*1024
            and not config["Mounts"] and host["Tmpfs"] == TMPFS
            and config["Config"]["User"] == "70:70" and host["AutoRemove"] and host["Init"]
            and host["PidsLimit"] == 128 and host["NanoCpus"] == 1000000000
            and host["CapDrop"] == ["ALL"] and not host["CapAdd"] and not host["Privileged"]
            and host["SecurityOpt"] == ["no-new-privileges"], "SAVED_RESTORE_BOUNDARY_CHANGED")


def create_args(name, label):
    return ("create", "--rm", "--init", "--pull=never", "--name", name, "--label", label,
            "--network", "none", "--user", "70:70", "--cap-drop", "ALL", "--read-only",
            "--memory", "512m", "--memory-swap", "512m", "--cpus", "1", "--pids-limit", "128",
            "--security-opt", "no-new-privileges", "--ulimit", "core=0:0",
            "--tmpfs", "/var/lib/postgresql:rw,noexec,nosuid,nodev,"
            "uid=70,gid=70,mode=0700,size=256m",
            "--tmpfs", "/var/run/postgresql:rw,noexec,nosuid,nodev,uid=70,gid=70,mode=0770,size=1m",
            "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=16m",  # noqa: S108 - container tmpfs
            "-e", "POSTGRES_DB=proofflow_product", "-e", "POSTGRES_HOST_AUTH_METHOD=trust",
            "--entrypoint", "/usr/bin/timeout", IMAGE, "-s", "KILL", "90",
            "/usr/local/bin/docker-entrypoint.sh", "postgres", "-c", "listen_addresses=")


def rehearse(value):
    require(set(value) == {"database", "database_sha256", "snapshot", "current"},
            "SAVED_RESTORE_INPUT_INVALID")
    raw = base64.b64decode(value["database"], validate=True)
    check_dump(raw, value["database_sha256"])
    plan = plan_restore(value["snapshot"], value["current"], now=datetime.now(UTC))
    token = uuid4().hex
    name, clone = "proofflow-saved-restore-" + token, "proofflow_restore_" + token
    label = "proofflow.saved-restore=" + token
    started = time.monotonic()
    result = None
    stage = "create"

    def sql(statement, database="proofflow_product", role="postgres"):
        return docker("exec", "-i", "--user", "70:70", name, "timeout", "-s", "KILL", "25",
                      "psql", "-X", "-qAt", "-U", role, "-d", database,
                      "--set", "ON_ERROR_STOP=1", stdin=statement, timeout=30)

    try:
        docker(*create_args(name, label))
        docker("start", name)
        stage = "start"
        for _ in range(100):
            try:
                if sql("SELECT 1;") == "1":
                    break
            except subprocess.CalledProcessError:
                pass
            time.sleep(0.1)
        else:
            raise RuntimeError("SAVED_RESTORE_START_FAILED")
        stage = "boundary"
        config = json.loads(docker("inspect", name))[0]
        validate_container(config)
        require(docker("exec", "--user", "70:70", name, "stat", "-f", "-c", "%T",
                       "/var/lib/postgresql") == "tmpfs", "SAVED_RESTORE_NOT_RAM_STORAGE")
        stage = "prepare_clone"
        sql("CREATE ROLE pf_product_owner NOLOGIN; CREATE ROLE pf_product_api NOLOGIN; "
            "CREATE ROLE pf_product_provisioner NOLOGIN; "
            "CREATE ROLE pf_product_dispatcher NOLOGIN; "
            "CREATE ROLE fixture_restore_reader LOGIN; "
            "CREATE DATABASE " + clone + " TEMPLATE template0 CONNECTION LIMIT 0;")
        stage = "import"
        sql(raw.decode("utf-8"), clone)
        before = int(sql("SELECT count(*) FROM pf_product.workspaces;", clone))
        try:
            sql("SELECT 1;", clone, "fixture_restore_reader")
        except subprocess.CalledProcessError as error:
            require("too many connections" in error.stderr, "SAVED_RESTORE_WRONG_LOGIN_DENIAL")
        else:
            raise RuntimeError("SAVED_RESTORE_LOGIN_ALLOWED")
        stage = "quarantine"
        sql(quarantine_sql(clone, plan["keep"]), clone)
        for table in AUTHORITY_TABLES:
            require(sql("SELECT count(*) FROM pf_product." + table + ";", clone) == "0",  # noqa: S608
                    "SAVED_RESTORE_AUTHORITY_REMAINED")
        kept = json.loads(sql("SELECT coalesce(json_agg(id::text ORDER BY id),'[]'::json) "
                              "FROM pf_product.workspaces;", clone))
        require(kept == plan["keep"], "SAVED_RESTORE_SCOPE_CHANGED")
        require(sql("SELECT count(*) FROM pf_product.workspaces WHERE revoked_at IS NULL;", clone)
                == "0", "SAVED_RESTORE_WORKSPACE_ACCESS_REMAINED")
        revalidate_restore(value["snapshot"], plan, value["current"], now=datetime.now(UTC))
        result = {"database_bytes": len(raw), "snapshot_workspaces": before,
                  "kept_workspaces": len(kept), "excluded_workspaces": len(plan["exclude"]),
                  "cleared_authority_tables": len(AUTHORITY_TABLES),
                  "ordinary_login_denied": True, "database_connection_limit": 0,
                  "plan": plan, "database_image": IMAGE,
                  "storage": "tmpfs_only_no_volumes_or_host_binds", "network": "none",
                  "production_promotion": False}
    except Exception as error:
        # Fixed classifications only; never echo a SQL row, statement or tool stderr.
        code = "UNCLASSIFIED"
        if isinstance(error, RuntimeError) and str(error).startswith("SAVED_RESTORE_"):
            code = str(error)
        elif isinstance(error, subprocess.CalledProcessError):
            for token, label in (("does not exist", "MISSING_OBJECT"),
                                 ("Permission denied", "PERMISSION"),
                                 ("cannot run inside a transaction block", "TRANSACTION")):
                if token in (error.stderr or ""):
                    code = label
                    break
        print(json.dumps({"failed_stage": stage, "code": code}), file=sys.stderr)
        raise
    finally:
        if docker("ps", "-aq", "--filter", "name=^/" + name + "$"):
            config = json.loads(docker("inspect", name))[0]
            require(config["Config"]["Labels"].get("proofflow.saved-restore") == token,
                    "SAVED_RESTORE_FOREIGN_CONTAINER")
            docker("rm", "--force", name)
        require(not docker("ps", "-aq", "--filter", "name=^/" + name + "$"),
                "SAVED_RESTORE_CLEANUP_UNCONFIRMED")
    return {**result, "container_removed": True,
            "elapsed_seconds": round(time.monotonic()-started, 3)}


def main():
    raw = sys.stdin.buffer.read(24*1024*1024+1)
    require(len(raw) <= 24*1024*1024, "SAVED_RESTORE_INPUT_LIMIT")
    print(json.dumps(rehearse(json.loads(raw))))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # SQL diagnostics may contain restored values. Never send them to logs.
        print("SAVED_DATABASE_REHEARSAL_FAILED", file=sys.stderr)
        raise SystemExit(1) from None
