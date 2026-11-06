"""Bind expiry to the accepted deployed UUIDv7 worker; no clock edits or forced pruning."""

import hashlib
import json
from datetime import UTC, datetime

from product_live_session import LiveSession, require
from vultr_phase1 import PRIVATE, ROOT


def main():
    path = PRIVATE / "evidence/phase5-authority-retention-enabled.json"
    require(not path.exists(), "RETENTION_ENABLE_ALREADY_STARTED_RECONCILE")
    update = json.loads((PRIVATE / "evidence/phase5-worker-authority-expiry.json").read_bytes())
    require(update["completed"], "EXPIRING_WORKER_UPDATE_INCOMPLETE")
    for name, digest in update["new_sources"].items():
        require(
            hashlib.sha256((ROOT / "worker" / name).read_bytes()).hexdigest() == digest,
            "EXPIRING_WORKER_SOURCE_CHANGED",
        )
    recovery = json.loads((PRIVATE / "evidence/phase5-encrypted-asset-recovery.json").read_bytes())
    require(recovery["completed"] and recovery["workspaces_retired"], "ASSET_RECOVERY_INCOMPLETE")
    security = json.loads(
        (
            PRIVATE / "evidence/phase5-security-91b59bd6e9354a4081ec53fc2b04db31" / "summary.json"
        ).read_bytes()
    )
    require(security["passed"] and len(security["probes"]) == 16, "SANDBOX_GATE_NOT_PASSED")
    record = {
        "started_at": datetime.now(UTC).isoformat(),
        "completed": False,
        "runtime": update["new_runtime"],
        "clock_edits": False,
    }

    def persist():
        path.write_bytes(json.dumps(record, sort_keys=True, indent=2).encode())

    with LiveSession() as live:
        require(live.policy["runtime_sha256"] == update["new_runtime"], "RUNTIME_CHANGED")
        require(
            live.sql("SELECT count(*) FROM pf_product.workspaces;") == b"0", "WORKSPACES_NOT_IDLE"
        )
        record["credit"] = live.credit
        persist()
        live.sql(
            "SET ROLE pf_product_provisioner; SELECT pf_product.enable_retention_expiry('"
            + update["new_runtime"]
            + "');"
        )
        require(
            live.sql("SET ROLE pf_product_provisioner; SELECT pf_product.retention_expiry_ready();")
            == b"t",
            "RETENTION_EXPIRY_NOT_BOUND",
        )
        record["completed"] = True
        record["finished_at"] = datetime.now(UTC).isoformat()
        persist()
        print(
            json.dumps(
                {
                    "expiry_enabled_for_current_runtime": True,
                    "admission": "closed",
                    "provider_calls": 0,
                    "new_resources": 0,
                }
            )
        )


if __name__ == "__main__":
    main()
