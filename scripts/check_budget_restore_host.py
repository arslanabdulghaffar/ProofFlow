"""Trusted deployed dump/restart/restore probe with admission held closed throughout."""

import hashlib
import json
import subprocess
from uuid import uuid4

DOCKER = ["/usr/bin/docker", "--host=unix:///var/run/docker.sock"]
database = "proofflow_budget_restore_" + uuid4().hex


def command(args, data=None):
    result = subprocess.run(args, input=data, capture_output=True, check=False, timeout=60)  # noqa: S603
    if result.returncode:
        raise RuntimeError("DEPLOYED_RESTORE_CHECK_COMMAND_FAILED")
    return result.stdout


def sql(db, statement):
    return command(
        [
            *DOCKER,
            "exec",
            "-i",
            "--user=70:70",
            "proofflow-budget",
            "psql",
            "-X",
            "-qAt",
            "-h",
            "/run/proofflow-budget",
            "-U",
            "postgres",
            "-d",
            db,
            "--set",
            "ON_ERROR_STOP=1",
        ],
        statement.encode(),
    )


def snapshot(db):
    tables = ("accounts", "reservations", "probe_receipts")
    # Fixed trusted table list; all rows ordered by their canonical JSON string.
    return {
        table: hashlib.sha256(
            sql(
                db,
                "SELECT row_to_json(t)::text FROM pf_budget."  # noqa: S608
                + table
                + " t ORDER BY row_to_json(t)::text;",
            )
        ).hexdigest()
        for table in tables
    }


created = False
try:
    if sql("proofflow_budget", "SELECT bool_and(blocked) FROM pf_budget.accounts;").strip() != b"t":
        raise RuntimeError("RESTORE_REQUIRES_CLOSED_ADMISSION")
    before = snapshot("proofflow_budget")
    row_counts = {
        table: int(sql("proofflow_budget", "SELECT count(*) FROM pf_budget." + table + ";"))  # noqa: S608 - fixed names
        for table in ("accounts", "reservations", "probe_receipts")
    }
    backup = command(
        [
            *DOCKER,
            "exec",
            "--user=70:70",
            "proofflow-budget",
            "pg_dump",
            "-h",
            "/run/proofflow-budget",
            "-U",
            "postgres",
            "-Fc",
            "proofflow_budget",
        ]
    )
    if not 0 < len(backup) <= 8 * 1024 * 1024:
        raise RuntimeError("RESTORE_PROBE_BACKUP_LIMIT")
    command(["/usr/bin/systemctl", "restart", "proofflow-budget.service"])
    # pg_isready is a fixed bounded administrative readiness check.
    import time

    deadline = time.monotonic() + 10
    while True:
        try:
            after_restart = snapshot("proofflow_budget")
            break
        except RuntimeError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.2)
    if before != after_restart:
        raise RuntimeError("DURABLE_ROWS_CHANGED_AFTER_RESTART")
    command(
        [
            *DOCKER,
            "exec",
            "--user=70:70",
            "proofflow-budget",
            "createdb",
            "-h",
            "/run/proofflow-budget",
            "-U",
            "postgres",
            "-T",
            "template0",
            database,
        ]
    )
    created = True
    command(
        [
            *DOCKER,
            "exec",
            "-i",
            "--user=70:70",
            "proofflow-budget",
            "pg_restore",
            "-h",
            "/run/proofflow-budget",
            "-U",
            "postgres",
            "--exit-on-error",
            "-d",
            database,
        ],
        backup,
    )
    restored = snapshot(database)
    if (
        before != restored
        or sql(database, "SELECT bool_and(blocked) FROM pf_budget.accounts;").strip() != b"t"
    ):
        raise RuntimeError("RESTORE_CHANGED_ROWS_OR_OPENED_ADMISSION")
    report = {
        "scope": "actual_deployed_database_restore_no_provider_calls",
        "rowset_sha256": before,
        "restart": "same_rows",
        "restore": "same_rows",
        "restored_admission": "blocked",
        "backup_bytes": len(backup),
        "backup_sha256": hashlib.sha256(backup).hexdigest(),
        "row_counts": row_counts,
        "limitation": "Restores captured rows; provider billing settlement is separate",
    }
finally:
    if created:
        command(
            [
                *DOCKER,
                "exec",
                "--user=70:70",
                "proofflow-budget",
                "dropdb",
                "-h",
                "/run/proofflow-budget",
                "-U",
                "postgres",
                database,
            ]
        )
print(json.dumps(report))
