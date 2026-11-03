"""Encrypted off-VM Phase 1 backup with actual disposable-database restore.

Windows CurrentUser DPAPI requires this user's profile for recovery. This is a
private development backup, not the later portable restic/object-storage design.
"""

import base64
import hashlib
import json
import os
import subprocess
from uuid import uuid4

from vultr_phase1 import PRIVATE, Admin


def crypt(raw, *, decrypt=False):
    operation = "Unprotect" if decrypt else "Protect"
    program = (
        "$ErrorActionPreference='Stop'; Add-Type -AssemblyName System.Security; "
        "$payload=[Convert]::FromBase64String([Console]::In.ReadToEnd()); "
        "$entropy=[Text.Encoding]::UTF8.GetBytes('ProofFlow-Phase1-Budget-Backup-v1'); "
        "$result=[Security.Cryptography.ProtectedData]::" + operation + "($payload,$entropy,"
        "[Security.Cryptography.DataProtectionScope]::CurrentUser); "
        "[Console]::Out.Write([Convert]::ToBase64String($result))"
    )
    result = subprocess.run(  # noqa: S603 - fixed OS cryptography, plaintext only on stdin
        [
            "C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-EncodedCommand",
            base64.b64encode(program.encode("utf-16le")).decode(),
        ],
        input=base64.b64encode(raw),
        capture_output=True,
        timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if result.returncode:
        raise RuntimeError("OFFVM_BACKUP_CRYPTO_FAILED")
    return base64.b64decode(result.stdout, validate=True)


admin = Admin()
database = "proofflow_offvm_restore_" + uuid4().hex
created = False
try:

    def host(command, data=None):
        result = admin.host("control", command, stdin=data)
        if result.returncode:
            raise RuntimeError("OFFVM_BACKUP_RESTORE_COMMAND_FAILED")
        return result.stdout

    def sql(db, statement):
        return host(
            "docker exec -i --user=70:70 proofflow-budget psql -X -qAt "
            "-h /run/proofflow-budget -U postgres --set ON_ERROR_STOP=1 -d " + db,
            statement.encode(),
        )

    def snapshot(db):
        return {
            table: hashlib.sha256(
                sql(
                    db,
                    "SELECT row_to_json(t)::text FROM pf_budget."  # noqa: S608
                    + table
                    + " t ORDER BY row_to_json(t)::text;",
                )
            ).hexdigest()
            for table in ("accounts", "reservations", "probe_receipts")
        }

    if sql("proofflow_budget", "SELECT bool_and(blocked) FROM pf_budget.accounts;").strip() != b"t":
        raise RuntimeError("BACKUP_REQUIRES_CLOSED_ADMISSION")
    before = snapshot("proofflow_budget")
    raw = host(
        "docker exec --user=70:70 proofflow-budget pg_dump -h /run/proofflow-budget "
        "-U postgres -Fc proofflow_budget"
    )
    if not 0 < len(raw) <= 8 * 1024 * 1024:
        raise RuntimeError("OFFVM_BACKUP_LIMIT")
    digest = hashlib.sha256(raw).hexdigest()
    path = PRIVATE / ("budget-" + digest + ".dump.dpapi")
    with path.open("xb") as file:
        file.write(crypt(raw))
        file.flush()
        os.fsync(file.fileno())
    restored = crypt(path.read_bytes(), decrypt=True)
    if restored != raw:
        raise RuntimeError("OFFVM_BACKUP_ROUNDTRIP_CHANGED")
    host(
        "docker exec --user=70:70 proofflow-budget createdb -h /run/proofflow-budget "
        "-U postgres -T template0 " + database
    )
    created = True
    host(
        "docker exec -i --user=70:70 proofflow-budget pg_restore -h /run/proofflow-budget "
        "-U postgres --exit-on-error -d " + database,
        restored,
    )
    if snapshot(database) != before:
        raise RuntimeError("OFFVM_RESTORE_ROWS_CHANGED")
    report = {
        "off_vm": True,
        "encrypted": "Windows_CurrentUser_DPAPI_with_project_entropy",
        "plaintext_bytes": len(raw),
        "plaintext_sha256": digest,
        "encrypted_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "actual_restore": "all_three_table_hashes_match",
        "rows": before,
        "limitation": "Requires original Windows user profile; portable restic backup deferred",
    }
    (PRIVATE / "evidence/budget-offvm-backup.json").write_bytes(json.dumps(report).encode())
    print(json.dumps(report))
finally:
    try:
        if created:
            host(
                "docker exec --user=70:70 proofflow-budget dropdb -h /run/proofflow-budget "
                "-U postgres " + database
            )
    finally:
        admin.close()
