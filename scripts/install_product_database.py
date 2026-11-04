"""Additive administrator migration of a separate product DB in the existing cluster.

No budget-table changes, new cloud service or credential output. Migration receipts
commit atomically with the reviewed SQL so an interrupted install is reconcilable.
"""

import hashlib
import json
import os
import re
import secrets
import stat
import subprocess
from pathlib import Path

SETUP = Path(__file__).resolve().parent
STATE = Path("/var/lib/proofflow-product-setup")
DOCKER = ["/usr/bin/docker", "--host=unix:///var/run/docker.sock"]


def command(args, data=None):
    result = subprocess.run(args, input=data, capture_output=True, timeout=60,  # noqa: S603
                            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C"})
    if result.returncode or len(result.stdout) > 65536:
        raise RuntimeError("PRODUCT_DATABASE_ADMIN_FAILED")
    return result.stdout.decode().strip()


def sql(text, database="proofflow_product"):
    return command([*DOCKER, "exec", "-i", "--user=70:70", "proofflow-budget", "psql",
                    "-X", "-qAt", "-h", "/run/proofflow-budget", "-U", "postgres", "-d", database,
                    "--set", "ON_ERROR_STOP=1"], text.encode())


def write(path, raw, *, uid=0, mode=0o600):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        with os.fdopen(fd, "wb", closefd=False) as file:
            file.write(raw)
            file.flush()
            os.fchmod(fd, mode)
            os.fchown(fd, uid, uid)
            os.fsync(fd)
    finally:
        os.close(fd)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def main():
    if os.geteuid() != 0:
        raise RuntimeError("ADMINISTRATOR_REQUIRED")
    os.umask(0o077)
    info = SETUP.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != 0
            or stat.S_IMODE(info.st_mode) != 0o700):
        raise RuntimeError("PRODUCT_SETUP_DIRECTORY_UNSAFE")
    config = json.loads((SETUP / "manifest.json").read_bytes())
    exists = sql("SELECT count(*) FROM pg_database WHERE datname='proofflow_product';", "postgres")
    intent = STATE / "database-intent"
    if exists == "0":
        if not intent.exists():
            write(intent, b"create separate proofflow_product database\n")
        command([*DOCKER, "exec", "--user=70:70", "proofflow-budget", "createdb",
                 "-h", "/run/proofflow-budget", "-U", "postgres", "proofflow_product"])
    elif exists != "1" or not intent.is_file():
        raise RuntimeError("UNRECOGNIZED_EXISTING_PRODUCT_DATABASE")
    sql("CREATE TABLE IF NOT EXISTS public.proofflow_migrations "
        "(name text PRIMARY KEY,digest text NOT NULL,"
        "applied_at timestamptz DEFAULT clock_timestamp());"
        "REVOKE ALL ON public.proofflow_migrations FROM PUBLIC;")
    names = ("001_identity_assets.sql", "002_upload_reservations.sql", "003_original_queue.sql",
             "004_termination_evidence.sql", "005_job_event_replay.sql",
             "006_browser_session.sql", "007_workspace_retention.sql")
    for name in names:
        raw = (SETUP / name).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != config["migrations"][name]:
            raise RuntimeError("MIGRATION_SOURCE_CHANGED")
        old = sql(
            "SELECT digest FROM public.proofflow_migrations WHERE name='" + name + "';")  # noqa: S608
        if old:
            if old != digest:
                raise RuntimeError("APPLIED_MIGRATION_CHANGED")
            continue
        text = raw.decode().strip()
        if not text.endswith("COMMIT;"):
            raise RuntimeError("MIGRATION_TRANSACTION_REQUIRED")
        # Fixed migration name and locally computed digest; no request SQL.
        receipt = ("RESET ROLE; INSERT INTO public.proofflow_migrations(name,digest) VALUES ('"  # noqa: S608
                   + name + "','" + digest + "'); COMMIT;")
        sql(text[:-len("COMMIT;")] + receipt)
    for role, limit in (("api", 8), ("dispatcher", 2)):
        parent = Path("/etc/proofflow-product-" + role)
        parent.mkdir(mode=0o700, exist_ok=True)
        info = parent.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != 0
                or stat.S_IMODE(info.st_mode) != 0o700):
            raise RuntimeError("PRODUCT_SECRET_PARENT_UNSAFE")
        directory = parent / "credentials"
        try:
            directory.mkdir(mode=0o700)
            os.chown(directory, 10003, 10003)
        except FileExistsError:
            info = directory.lstat()
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid != 10003
                    or stat.S_IMODE(info.st_mode) != 0o700):
                raise RuntimeError("PRODUCT_SECRET_DIRECTORY_UNSAFE") from None
        path = directory / "database-password"
        if not path.exists():
            write(path, secrets.token_urlsafe(48).encode(), uid=10003, mode=0o400)
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 10003 or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != 0o400):
            raise RuntimeError("PRODUCT_CREDENTIAL_UNSAFE")
        password = path.read_text()
        if not re.fullmatch(r"[A-Za-z0-9_-]{64}", password):
            raise RuntimeError("PRODUCT_CREDENTIAL_INVALID")
        login = "pf_product_" + role + "_login"
        exists = sql("SELECT count(*) FROM pg_roles WHERE rolname='" + login + "';")  # noqa: S608
        if exists == "0":
            sql("CREATE ROLE " + login + " LOGIN IN ROLE pf_product_" + role
                + " CONNECTION LIMIT " + str(limit) + " PASSWORD '" + password + "';")
        else:
            # Do not overwrite an existing password or widen role privileges.
            check = sql("SELECT rolcanlogin AND NOT rolsuper AND NOT rolcreatedb "  # noqa: S608
                        "AND NOT rolcreaterole "
                        "AND NOT rolreplication AND NOT rolbypassrls AND rolconnlimit=" + str(limit)
                        + " FROM pg_roles WHERE rolname='" + login + "';")
            if check != "t":
                raise RuntimeError("PRODUCT_ROLE_CONFIGURATION_CHANGED")
        sql("ALTER ROLE " + login + " SET statement_timeout='5s'; ALTER ROLE " + login
            + " SET idle_in_transaction_session_timeout='5s';")
        if sql("SELECT rolpassword LIKE 'SCRAM-SHA-256$%' FROM pg_authid WHERE rolname='"  # noqa: S608
               + login + "';") != "t":
            raise RuntimeError("PRODUCT_SCRAM_REQUIRED")
    hba = Path("/etc/proofflow-budget/pg_hba.conf")
    original = (SETUP / "original-pg_hba.conf").read_bytes()
    added = (b"local proofflow_product pf_product_api_login scram-sha-256\n"
             b"local proofflow_product pf_product_dispatcher_login scram-sha-256\n")
    desired = original.replace(b"local all all reject", added + b"local all all reject")
    if hba.read_bytes() not in (original, desired):
        raise RuntimeError("DATABASE_HBA_CHANGED")
    if hba.read_bytes() != desired:
        pending = hba.with_suffix(".product-pending")
        write(pending, desired, mode=0o644)
        os.replace(pending, hba)
        directory = os.open(hba.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    if sql("SELECT pg_reload_conf();") != "t":
        raise RuntimeError("DATABASE_HBA_RELOAD_FAILED")
    if sql("SELECT count(*) FROM pg_hba_file_rules WHERE error IS NOT NULL;") != "0":
        raise RuntimeError("DATABASE_HBA_INVALID")
    # Admission remains closed until the operator integration check establishes
    # real worker/verifier bindings. There is no model or request-selected policy.
    print(json.dumps({"product_database": "migrated", "migrations": len(names), "scram_roles": 2,
                      "budget_tables_changed": False, "execution_admission": "not_enabled_here"}))


if __name__ == "__main__":
    main()
