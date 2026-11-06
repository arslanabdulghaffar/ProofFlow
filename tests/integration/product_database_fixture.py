"""Disposable real PostgreSQL only. Synthetic credentials, no ports/network/host mounts."""

import hashlib
import json
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from scripts.check_budget_postgres import docker, require
from scripts.check_product_postgres import IMAGE


class Database:
    def __init__(self, name):
        self.name = name

    def sql(self, statement, role="api", **params):
        user = {"api": "fixture_api", "provisioner": "fixture_provisioner",
                "dispatcher": "fixture_dispatcher", "admin": "postgres"}[role]
        bindings = []
        for key, value in params.items():
            require(key.isidentifier(), "Invalid fixture binding")
            bindings.extend(("--set", key + "=" + str(value)))
        return docker("exec", "-i", "--user", "70:70", self.name,
                      "psql", "-X", "-qAt", "-U", user, "-d", "proofflow_product",
                      "--set", "ON_ERROR_STOP=1", *bindings,
                      stdin="SET statement_timeout='5s'; SET lock_timeout='3s';\n" + statement)

    def expect(self, statement, code, role="api", **params):
        try:
            self.sql(statement, role, **params)
        except subprocess.CalledProcessError as error:
            require(code in error.stderr, "Unexpected SQL diagnostic: " + error.stderr[:200])
        else:
            raise RuntimeError("Expected database rejection: " + code)

    def workspace(self):
        identifier = self.sql("SELECT uuidv7();", "admin")
        self.sql("SELECT pf_product.create_workspace(:'w','operator',"
                 "clock_timestamp()+interval '23 hours');", "provisioner", w=identifier)
        session = hashlib.sha256((identifier + "session").encode()).hexdigest()
        csrf = hashlib.sha256((identifier + "csrf").encode()).hexdigest()
        self.sql("SELECT pf_product.create_session(:'w',:'s',:'c',"
                 "clock_timestamp()+interval '50 minutes');", "provisioner",
                 w=identifier, s=session, c=csrf)
        return {"w": identifier, "s": session, "c": csrf}

    def asset(self, context, kind="pipeline", size=1):
        value = {**context, "a": str(uuid4()), "k": kind, "n": size,
                 "d": hashlib.sha256((kind + str(uuid4())).encode()).hexdigest()}
        self.sql("SELECT pf_product.reserve_upload(:'w',:'s',:'c',:'a',:'k',:'d',:'n');", **value)
        self.sql("SELECT pf_product.complete_upload(:'w',:'s',:'c',:'a',:'k',:'d',:'n');", **value)
        return value


@contextmanager
def database():
    token = uuid4().hex
    name = "proofflow-queue-test-" + token
    volume = name + "-data"
    label = "proofflow.queue-test=" + token
    db = Database(name)
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
                if db.sql("SELECT 1;", "admin") == "1":
                    break
            except subprocess.CalledProcessError:
                pass
            time.sleep(0.1)
        else:
            raise RuntimeError("PRIVATE_FIXTURE_START_FAILED")
        config = json.loads(docker("inspect", name))[0]
        require(config["Image"] == IMAGE and config["HostConfig"]["NetworkMode"] == "none"
                and not config["HostConfig"]["PortBindings"]
                and config["HostConfig"]["ReadonlyRootfs"]
                and all(m["Type"] in ("volume", "tmpfs") for m in config["Mounts"]),
                "Unexpected fixture topology")
        for path in sorted(Path("db/phase2").glob("*.sql")):
            db.sql(path.read_text(encoding="utf-8"), "admin")
        db.sql("CREATE ROLE fixture_api LOGIN IN ROLE pf_product_api; "
               "CREATE ROLE fixture_provisioner LOGIN IN ROLE pf_product_provisioner; "
               "CREATE ROLE fixture_dispatcher LOGIN IN ROLE pf_product_dispatcher;", "admin")
        yield db
    finally:
        if docker("ps", "-aq", "--filter", "name=^/" + name + "$"):
            config = json.loads(docker("inspect", name))[0]
            require(config["Config"]["Labels"].get("proofflow.queue-test") == token,
                    "Foreign fixture container")
            docker("rm", "--force", name)
        if docker("volume", "ls", "-q", "--filter", "name=^" + volume + "$"):
            config = json.loads(docker("volume", "inspect", volume))[0]
            require(config["Labels"].get("proofflow.queue-test") == token, "Foreign fixture volume")
            docker("volume", "rm", volume)
        require(not docker("ps", "-aq", "--filter", "name=^/" + name + "$")
                and not docker("volume", "ls", "-q", "--filter", "name=^" + volume + "$"),
                "Fixture cleanup failed")
