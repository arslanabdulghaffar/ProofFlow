"""Private deployed SCRAM/privilege checks and closed-admission backup/restart/restore."""

import base64
import hashlib
import json
import os
import shlex
import subprocess
import time
from datetime import UTC, datetime
from uuid import uuid4

from vultr_credit_guard import run as credit_guard
from vultr_phase1 import PRIVATE, Admin

TABLES = ("workspaces", "sessions", "assets", "uploads", "execution_policy",
          "contract_approvals", "jobs", "job_events", "deletions")
AUTH_PROBE = """
import json,sys,psycopg
from api.app.product_store import ProductConnection
from orchestrator.product_setup import database_password
role=sys.stdin.read().strip()
params=ProductConnection(database_password(),role).parameters()
with psycopg.connect(**params,autocommit=True) as c:
    assert c.execute('SELECT current_user').fetchone()[0]=='pf_product_'+role+'_login'
    for q in ('SELECT * FROM pf_product.jobs','SET ROLE pf_product_owner',
              'CREATE TABLE public.forbidden(id integer)'):
        try: c.execute(q)
        except psycopg.Error as e: assert e.sqlstate=='42501'
        else: raise RuntimeError('PRODUCT_PRIVILEGE_ESCALATION')
try: psycopg.connect(**{**params,'password':'x'*64},connect_timeout=3)
except psycopg.OperationalError as e:
    assert e.sqlstate=='28P01' or 'password authentication failed' in str(e)
else: raise RuntimeError('PRODUCT_WRONG_PASSWORD_ACCEPTED')
print(json.dumps({'role':role,'scram':'passed','table_owner_schema_denied':True}))
"""


def crypt(raw, decrypt=False):
    operation = "Unprotect" if decrypt else "Protect"
    script = ("$ErrorActionPreference='Stop'; Add-Type -AssemblyName System.Security; "
        "$payload=[Convert]::FromBase64String([Console]::In.ReadToEnd()); "
        "$entropy=[Text.Encoding]::UTF8.GetBytes('ProofFlow-Phase2-Product-Backup-v1'); "
        "$result=[Security.Cryptography.ProtectedData]::" + operation + "($payload,$entropy,"
        "[Security.Cryptography.DataProtectionScope]::CurrentUser); "
        "[Console]::Out.Write([Convert]::ToBase64String($result))")
    result = subprocess.run(  # noqa: S603 - fixed OS encryption, secret-free argv
        ["C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe", "-NoProfile",
         "-NonInteractive", "-EncodedCommand",
         base64.b64encode(script.encode("utf-16le")).decode()],
        input=base64.b64encode(raw), capture_output=True, timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise RuntimeError("PRODUCT_BACKUP_CRYPTO_FAILED")
    return base64.b64decode(result.stdout, validate=True)


def main():
    admin, clone, created = Admin(), "proofflow_product_restore_" + uuid4().hex, False
    stopped = False
    try:
        budget = credit_guard(admin, datetime.now(UTC))
        if budget.get("credit_guard") != "within_early_cutoff":
            raise RuntimeError("CREDIT_GUARD_NOT_ADMITTING")
        def host(command, raw=None, timeout=60):
            response = admin.host("control", command, stdin=raw, timeout=timeout)
            if response.returncode:
                raise RuntimeError("PRODUCT_INTEGRITY_CHECK_FAILED")
            return response.stdout
        if host("cat /etc/machine-id").decode().strip() != admin.state["control_machine_id"]:
            raise RuntimeError("DESIGNATED_CONTROL_CHANGED")
        def sql(statement, database="proofflow_product"):
            return host("docker exec -i --user=70:70 proofflow-budget psql -X -qAt "
                "-h /run/proofflow-budget -U postgres --set ON_ERROR_STOP=1 -d " + database,
                statement.encode()).strip()
        def snapshot(database="proofflow_product", schema="pf_product", tables=TABLES):
            return {t: hashlib.sha256(sql("SELECT row_to_json(t)::text FROM "  # noqa: S608
                + schema + "." + t + " t ORDER BY row_to_json(t)::text;", database)).hexdigest()
                    for t in tables}
        auth = []
        for role in ("api", "dispatcher"):
            auth.append(json.loads(host("docker exec -i proofflow-product-" + role
                + " python -c " + shlex.quote(AUTH_PROBE), role.encode())))
        if sql("SELECT count(*) FROM pf_product.jobs WHERE state NOT IN "
               "('NEEDS_REVIEW','FAILED_INFRA','CANCELLED');") != b"0":
            raise RuntimeError("PRODUCT_JOBS_STILL_ACTIVE")
        policy = json.loads(sql("SELECT row_to_json(p) FROM pf_product.execution_policy p;"))
        if policy["enabled"]:
            sql("SET ROLE pf_product_provisioner; SELECT pf_product.configure_execution('"
                + policy["runtime_sha256"] + "','" + policy["verifier_sha256"] + "',false);")
        host("systemctl stop proofflow-product-api.service proofflow-product-dispatcher.service")
        stopped = True
        if sql("SELECT (SELECT count(*) FROM pf_product.workspaces WHERE kind='guest') + "
               "(SELECT count(*) FROM pf_product.deletions);") != b"0":
            raise RuntimeError("GUEST_OR_DELETION_BACKUP_REQUIRES_RETENTION_AWARE_RESTORE")
        before = snapshot()
        counts = {t: int(sql("SELECT count(*) FROM pf_product." + t + ";")) for t in TABLES}  # noqa: S608
        old_budget = snapshot("proofflow_budget", "pf_budget", ("accounts", "reservations",
                                                                "probe_receipts"))
        if sql("SELECT bool_and(blocked) FROM pf_budget.accounts;", "proofflow_budget") != b"t":
            raise RuntimeError("PROVIDER_ADMISSION_OPEN")
        raw = host("docker exec --user=70:70 proofflow-budget pg_dump -h /run/proofflow-budget "
                   "-U postgres -Fc proofflow_product")
        if not 0 < len(raw) <= 16 * 1024 * 1024:
            raise RuntimeError("PRODUCT_BACKUP_LIMIT")
        backup = PRIVATE / ("product-" + hashlib.sha256(raw).hexdigest() + ".dump.dpapi")
        with backup.open("xb") as file:
            file.write(crypt(raw))
            file.flush()
            os.fsync(file.fileno())
        restored = crypt(backup.read_bytes(), True)
        if restored != raw:
            raise RuntimeError("PRODUCT_BACKUP_ROUNDTRIP_CHANGED")
        host("systemctl restart proofflow-budget.service")
        deadline = time.monotonic() + 15
        while True:
            try:
                after = snapshot()
                break
            except RuntimeError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.2)
        if before != after:
            raise RuntimeError("PRODUCT_RESTART_CHANGED_ROWS")
        host("docker exec --user=70:70 proofflow-budget createdb -h /run/proofflow-budget "
             "-U postgres -T template0 " + clone)
        created = True
        host("docker exec -i --user=70:70 proofflow-budget pg_restore -h /run/proofflow-budget "
             "-U postgres --exit-on-error -d " + clone, restored)
        if before != snapshot(clone):
            raise RuntimeError("PRODUCT_RESTORE_CHANGED_ROWS")
        if old_budget != snapshot("proofflow_budget", "pf_budget", ("accounts", "reservations",
                                                                   "probe_receipts")):
            raise RuntimeError("BUDGET_ROWS_CHANGED")
        report = {"observed_at": datetime.now(UTC).isoformat(), "auth": auth,
                  "rowset_sha256": before, "row_counts": counts, "restart": "same_rows",
                  "offvm_restore": "same_rows", "backup_sha256": hashlib.sha256(raw).hexdigest(),
                  "backup_bytes": len(raw), "budget_rows_unchanged": True,
                  "product_admission": "closed", "credit_guard": budget,
                  "limitation": "Windows-profile DPAPI; database only, not asset/journal backup"}
        (PRIVATE / "evidence/product-integrity-latest.json").write_bytes(
            json.dumps(report).encode())
        print(json.dumps({"scram_roles": len(auth), "restart": "passed", "restore": "passed",
                          "budget_unchanged": True,
                          "remaining_credit": budget["remaining_credit"]}))
    finally:
        try:
            if created:
                host("docker exec --user=70:70 proofflow-budget dropdb -h /run/proofflow-budget "
                     "-U postgres " + clone)
            if stopped:
                host("systemctl start proofflow-product-api.service "
                     "proofflow-product-dispatcher.service")
        finally:
            admin.close()


if __name__ == "__main__":
    main()
