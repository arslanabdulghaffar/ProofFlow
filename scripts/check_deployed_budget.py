"""Trusted deployed SCRAM/privilege checks, no provider request or candidate code."""

import json
import os
from pathlib import Path

import psycopg

from orchestrator.budget_store import BudgetConnection

if os.getuid() != 10001:
    raise SystemExit("CONTROL_SERVICE_UID_REQUIRED")
secret = Path("/etc/proofflow/credentials/budget-password")
if secret.stat().st_uid != 10001 or secret.stat().st_mode & 0o077:
    raise SystemExit("UNSAFE_BUDGET_SECRET")
connection = BudgetConnection(secret.read_text().strip())
checks = []
with psycopg.connect(**connection.parameters(), autocommit=True) as db:
    row = db.execute("SELECT current_user,current_setting('fsync'),"
                     "current_setting('full_page_writes'),current_setting('synchronous_commit'),"
                     "current_setting('listen_addresses')").fetchone()
    if row != ("pf_budget_login", "on", "on", "on", ""):
        raise SystemExit("DB_IDENTITY_DURABILITY_OR_NETWORK_MISMATCH")
    checks.append("scram_authenticated_socket_and_durable_no_tcp")
    for statement in ("SELECT * FROM pf_budget.accounts", "SET ROLE pf_budget_owner",
                      "UPDATE pf_budget.accounts SET blocked=false"):
        try:
            db.execute(statement)
        except psycopg.errors.InsufficientPrivilege:
            pass
        else:
            raise SystemExit("DISPATCHER_PRIVILEGE_ESCALATION")
    checks.append("table_read_mutation_and_owner_escalation_denied")
for changes in ({"password": "x" * 64}, {"password": ""}, {"user": "postgres"}):
    try:
        with psycopg.connect(**(connection.parameters() | changes), connect_timeout=3):
            pass
    except psycopg.OperationalError:
        pass
    else:
        raise SystemExit("WRONG_CREDENTIAL_OR_PEER_ADMIN_ACCEPTED")
checks.append("wrong_missing_password_and_peer_admin_denied")
print(json.dumps({"scope": "actual_deployed_database_no_provider_call", "checks": checks}))
