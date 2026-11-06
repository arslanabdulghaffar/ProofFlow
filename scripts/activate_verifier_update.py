"""Closed/idle repin of existing verifier helper. No candidates or provider calls."""

import base64
import hashlib
import json
import re
from datetime import UTC, datetime

from install_product_services import verifier_unit
from product_live_session import LiveSession, require
from vultr_phase1 import PRIVATE, ROOT


def main():
    path = PRIVATE / "evidence/phase5-source-verifier-update.json"
    require(not path.exists(), "VERIFIER_UPDATE_ALREADY_STARTED_RECONCILE")
    previous = json.loads((PRIVATE / "evidence/product-service-install.json").read_bytes())
    old = previous["verifier"]["verifier_deployment"]
    current = json.loads((PRIVATE / "evidence/verifier-deployment.json").read_bytes())
    new = current["deployment"]
    require(
        all(re.fullmatch("[a-f0-9]{64}", v) for v in (old, new, current["rootfs_sha256"]))
        and old != new,
        "VERIFIER_REVISION_INVALID",
    )
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
        worker_path = "/etc/proofflow-product-dispatcher/worker/worker.json"
        worker_raw = live.host("cat " + worker_path)
        config = json.loads(worker_raw)
        require(
            config["verifier_sha256"] == live.policy["verifier_sha256"]
            and config["runtime_sha256"] == live.policy["runtime_sha256"],
            "OLD_PIN_CHANGED",
        )
        unit_path = "/etc/systemd/system/proofflow-verifier-helper.service"
        # LiveSession strips outer whitespace; helper byte check uses actual readback below.
        old_unit = verifier_unit("/opt/proofflow-verifier/" + old)
        payload = {
            worker_path: {
                "old": worker_raw,
                "new": json.dumps(
                    {**config, "verifier_sha256": current["rootfs_sha256"]}, sort_keys=True
                ).encode(),
            },
            unit_path: {"old": old_unit, "new": verifier_unit("/opt/proofflow-verifier/" + new)},
        }
        encoded = json.dumps(
            {
                p: {k: base64.b64encode(v).decode() for k, v in values.items()}
                for p, values in payload.items()
            }
        ).encode()
        raw = (ROOT / "scripts/install_verifier_update.py").read_bytes()
        target = (
            "/var/lib/proofflow-product-setup/verifier-update-"
            + hashlib.sha256(raw).hexdigest()
            + ".py"
        )
        live.host("umask 077; cat > " + target, raw)
        require(
            live.host("sha256sum " + target).decode().split()[0] == hashlib.sha256(raw).hexdigest(),
            "INSTALLER_SOURCE_CHANGED",
        )
        live.host("/usr/bin/python3 -I -B " + target + " --check-only", encoded)
        record = {
            "started_at": datetime.now(UTC).isoformat(),
            "old_deployment": old,
            "new_deployment": new,
            "old_policy": live.policy,
            "credit": live.credit,
            "installer_sha256": hashlib.sha256(raw).hexdigest(),
            "completed": False,
        }
        path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        live.host(
            "systemctl stop proofflow-product-dispatcher.service "
            "proofflow-verifier-helper.socket proofflow-verifier-helper.service"
        )
        live.host("/usr/bin/python3 -I -B " + target, encoded)
        live.host("systemctl daemon-reload")
        live.sql(
            "SET ROLE pf_product_provisioner; SELECT pf_product.configure_execution('"
            + live.policy["runtime_sha256"]
            + "','"
            + current["rootfs_sha256"]
            + "',false);"
        )
        record["new_policy"] = json.loads(
            live.sql("SELECT row_to_json(p) FROM pf_product.execution_policy p;")
        )
        require(
            record["new_policy"]["verification_epoch"] == live.policy["verification_epoch"] + 1
            and not record["new_policy"]["enabled"],
            "VERIFIER_EPOCH_CHANGED",
        )
        live.host("systemctl start proofflow-verifier-helper.socket")
        record.update(completed=True, finished_at=datetime.now(UTC).isoformat())
        path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {
                    "verifier_repinned": True,
                    "admission": False,
                    "dispatcher": "stopped_until_product_image_install",
                    "rootfs_sha256": current["rootfs_sha256"],
                }
            )
        )


if __name__ == "__main__":
    main()
