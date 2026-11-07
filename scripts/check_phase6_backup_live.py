"""One-shot current empty-product snapshot to encrypted off-VM vault.

No service stops, new resources, restoration, promotion or candidate execution.
The real nonempty concurrent-data restore is a separate disposable local test.
Do not replay this receipt or mistake this one capture for scheduled backups.
"""

import base64
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from asset_backup_vault import recover, save
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from product_live_session import PRIVATE, LiveSession, require
from recovery_clock import wait_for_observation

from orchestrator.asset_backup import open_backup, seal


def main():
    receipt = PRIVATE / "evidence/phase6-consistent-backup.json"
    require(not receipt.exists(), "RECONCILE_EXISTING_PHASE6_BACKUP")
    record = {"observed_at": datetime.now(UTC).isoformat(), "completed": False,
              "scope": "existing_empty_private_product_database_capture",
              "provider_calls": 0, "new_resources": 0, "asset_count": 0,
              "scheduled_backup": False, "portable_key_recovery": False}

    def persist():
        receipt.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")

    guard = Path("orchestrator/restore_guard.py").read_text(encoding="utf-8")
    capture = Path("scripts/consistent_product_backup.py").read_text(encoding="utf-8")
    import_line = ("from orchestrator.restore_guard import "
                   "CURRENT_AUTHORITY_SQL, check_dump, inventory")
    require(capture.count(import_line) == 1, "CAPTURE_SOURCE_CHANGED")
    program = guard + "\n" + capture.replace(import_line, "") + "\n" + """
import base64
with snapshot('proofflow-budget') as captured:
    if captured.inventory['workspaces'] or captured.assets:
        raise CaptureError('EMPTY_CAPTURE_PRECONDITION_CHANGED')
    raw = captured.dump()
    print(json.dumps({'snapshot':captured.inventory,'database':base64.b64encode(raw).decode()}))
"""
    with LiveSession() as live:
        record["credit"] = live.credit
        require(live.sql("SELECT count(*) FROM pf_product.workspaces;") == b"0",
                "CAPTURE_REQUIRES_EMPTY_PRIVATE_PRODUCT")
        require(live.sql("SELECT bool_and(blocked) FROM pf_budget.accounts;", "proofflow_budget")
                == b"t", "INFERENCE_MUST_REMAIN_CLOSED")
        persist()
        captured = json.loads(live.host("python3 -I -", program.encode()))
        raw = base64.b64decode(captured["database"], validate=True)
        key = AESGCM.generate_key(bit_length=256)
        now = wait_for_observation(captured["snapshot"]["observed_at"])
        envelope = seal(captured["snapshot"], [], raw, key, now=now)
        payload = open_backup(envelope, key, now=datetime.now(UTC))
        identifier = save(envelope, key, datetime.fromisoformat(payload["expires_at"]))
        record.update(backup_id=identifier, dump_bytes=len(raw),
                      snapshot_at=captured["snapshot"]["observed_at"],
                      expires_at=payload["expires_at"],
                      encrypted_sha256=hashlib.sha256(envelope).hexdigest())
        persist()
        recovered, recovered_key = recover(identifier)
        reopened = open_backup(recovered, recovered_key, now=datetime.now(UTC))
        require(base64.b64decode(reopened["database"], validate=True) == raw
                and recovered == envelope and not reopened["assets"], "VAULT_ROUNDTRIP_CHANGED")
        require(live.sql("SELECT count(*) FROM pg_stat_activity WHERE application_name='psql' "
                         "AND state='idle in transaction';") == b"0", "EXPORTER_LEAKED")
        require(live.sql("SELECT enabled FROM pf_product.execution_policy;") == b"f",
                "PRODUCT_ADMISSION_OPENED")
        services = live.host("systemctl is-active proofflow-product-api.service "
                             "proofflow-product-dispatcher.service "
                             "proofflow-product-retention.timer").decode().splitlines()
        require(services == ["active"] * 3, "SERVICE_HEALTH_CHANGED")
        record.update(completed=True, finished_at=datetime.now(UTC).isoformat(),
                      exporter_cleanup="confirmed", services=services,
                      product_admission="closed", inference_admission="closed",
                      checks=["one_exported_database_snapshot", "encrypted_offvm_dpapi_vault",
                              "authenticated_exact_database_recovery_in_memory",
                              "no_services_stopped_or_new_cloud_services"])
        persist()
    print(json.dumps({"completed": True, "dump_bytes": record["dump_bytes"],
                      "expires_at": record["expires_at"], "receipt": receipt.name}))


if __name__ == "__main__":
    main()
