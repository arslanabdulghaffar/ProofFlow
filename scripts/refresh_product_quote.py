"""Read fresh official quote; closed/idle exact config update only. No model call."""

import hashlib
import json
from datetime import UTC, datetime

from install_provider_quote import validate
from prepare_repair_provider import main as prepare_quote
from product_live_session import LiveSession, require
from vultr_phase1 import PRIVATE, ROOT


def main():
    prepare_quote()
    new = json.loads((PRIVATE / "repair-provider.json").read_bytes())
    digest = hashlib.sha256(json.dumps(new, sort_keys=True).encode()).hexdigest()
    path = PRIVATE / ("evidence/product-quote-refresh-" + digest + ".json")
    require(not path.exists(), "QUOTE_UPDATE_ALREADY_STARTED_RECONCILE")
    with LiveSession() as live:
        require(
            live.sql(
                "SELECT count(*) FROM pf_product.jobs WHERE state NOT IN "
                "('NEEDS_REVIEW','FAILED_INFRA','CANCELLED');"
            )
            == b"0",
            "JOBS_NOT_IDLE",
        )
        require(
            live.sql(
                "SELECT count(*) FROM pf_product.pr_intents WHERE lease_owner IS NOT NULL "
                "OR state IN ('BRANCH_PENDING','COMMIT_PENDING','PR_PENDING');"
            )
            == b"0",
            "PR_NOT_IDLE",
        )
        require(
            live.sql("SELECT bool_and(blocked) FROM pf_budget.accounts;", "proofflow_budget")
            == b"t",
            "INFERENCE_NOT_CLOSED",
        )
        old_raw = live.host("cat /etc/proofflow-repair/config.json")
        validate(json.loads(old_raw), new, datetime.now(UTC))
        value = {"old_sha256": hashlib.sha256(old_raw).hexdigest(), "new": new}
        raw = (ROOT / "scripts/install_provider_quote.py").read_bytes()
        target = (
            "/var/lib/proofflow-product-setup/quote-update-"
            + hashlib.sha256(raw).hexdigest()
            + ".py"
        )
        live.host("umask 077; cat > " + target, raw)
        require(
            live.host("sha256sum " + target).decode().split()[0] == hashlib.sha256(raw).hexdigest(),
            "QUOTE_INSTALLER_CHANGED",
        )
        encoded = json.dumps(value).encode()
        live.host("/usr/bin/python3 -I -B " + target + " --check-only", encoded)
        record = {
            "started_at": datetime.now(UTC).isoformat(),
            "old_sha256": value["old_sha256"],
            "new_sha256": digest,
            "new_quote": new["quote"],
            "credit": live.credit,
            "completed": False,
        }
        path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        live.host("systemctl stop proofflow-product-dispatcher.service")
        live.host("/usr/bin/python3 -I -B " + target, encoded)
        require(
            live.host("sha256sum /etc/proofflow-repair/config.json").decode().split()[0] == digest,
            "QUOTE_READBACK_CHANGED",
        )
        record.update(completed=True, finished_at=datetime.now(UTC).isoformat())
        path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {
                    "quote_refreshed": True,
                    "inference_blocked": True,
                    "dispatcher": "stopped_until_product_service_install",
                    "quote_sha256": digest,
                }
            )
        )


if __name__ == "__main__":
    main()
