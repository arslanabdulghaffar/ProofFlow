"""One-shot real private upload/worker/backup/delete/isolated restore acceptance.

No model call, PR, activation, new cloud resource or production restore. Only two
new labeled synthetic workspaces are retired; failures are preserved for recovery.
"""

import argparse
import base64
import hashlib
import json
import re
import sys
import time
from datetime import UTC, datetime
from uuid import UUID, uuid4

from asset_backup_vault import recover, retire, save
from asset_recovery_container import run as run_asset_recovery
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from product_live_session import LiveSession, require
from recovery_clock import wait_for_observation
from vultr_phase1 import PRIVATE, ROOT

sys.path.insert(0, str(ROOT))
from orchestrator.asset_backup import open_backup, seal  # noqa: E402
from orchestrator.restore_guard import (  # noqa: E402
    AUTHORITY_TABLES,
    CURRENT_AUTHORITY_SQL,
    plan_restore,
    quarantine_sql,
    revalidate_restore,
)
from worker.protocol import authority_id  # noqa: E402


def current_authority(live):
    current = json.loads(live.sql(CURRENT_AUTHORITY_SQL))
    wait_for_observation(current["observed_at"])
    return current


def clone_sql(live, statement, clone):
    require(re.fullmatch(r"proofflow_restore_[a-f0-9]{32}", clone), "RESTORE_TARGET_FORBIDDEN")
    return live.host("docker exec -i --user=70:70 proofflow-budget psql -X -qAt "
                     "-h /run/proofflow-budget -U postgres --set ON_ERROR_STOP=1 -d " + clone,
                     statement.encode())


def resume_assets(live, record):
    workspaces = [str(UUID(w)) for w in record["fixture_workspaces"]]
    actual = json.loads(
        live.sql("SELECT json_agg(id::text ORDER BY id) FROM pf_product.workspaces;")
    )
    require(sorted(actual) == sorted(workspaces), "BACKUP_RESUME_WORKSPACES_CHANGED")
    job = str(UUID(record["job"]))
    require(
        live.sql(
            "SELECT count(*) FROM pf_product.jobs WHERE id='"  # noqa: S608 - canonical UUID
            + job
            + "' AND state='NEEDS_REVIEW' AND outcome='execution_failed' "
            "AND worker_receipt->>'cleanup'='confirmed';"
        )
        == b"1",
        "BACKUP_RESUME_JOB_CHANGED",
    )
    assets = []
    for workspace in workspaces:
        client = live.login(workspace)
        rows = json.loads(
            live.sql(
                "SELECT json_agg(json_build_object('id',id,'sha256',sha256,"  # noqa: S608
                "'created_at',created_at) ORDER BY id) FROM pf_product.assets "
                "WHERE workspace_id='" + workspace + "';"
            )
        )
        require(len(rows) == (4 if workspace == workspaces[0] else 1), "BACKUP_RESUME_ASSET_COUNT")
        for row in rows:
            response = client.get("/v1/assets/" + str(UUID(row["id"])) + "/download")
            require(
                response.status_code == 200
                and hashlib.sha256(response.content).hexdigest() == row["sha256"],
                "BACKUP_RESUME_ASSET_CHANGED",
            )
            assets.append(
                {
                    "workspace": workspace,
                    "sha256": row["sha256"],
                    "created_at": row["created_at"],
                    "bytes": response.content,
                }
            )
    return assets


def main():
    path = PRIVATE / "evidence/phase5-encrypted-asset-recovery.json"
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume-backup", action="store_true")
    resume = parser.parse_args().resume_backup
    require(
        path.exists() if resume else not path.exists(), "RECOVERY_PROBE_ALREADY_STARTED_RECONCILE"
    )
    record = {
        "started_at": datetime.now(UTC).isoformat(),
        "completed": False,
        "fixture_workspaces": [],
        "provider_calls": 0,
        "new_resources": 0,
    }
    if resume:
        record = json.loads(path.read_bytes())
        require(
            not record["completed"]
            and "backup_id" not in record
            and len(record["fixture_workspaces"]) == 2
            and record["job_result"]["state"] == "NEEDS_REVIEW"
            and record["job_result"]["outcome"] == "execution_failed",
            "BACKUP_RESUME_SCOPE_MISMATCH",
        )
        preserved = path.with_name("phase5-encrypted-asset-recovery-initial.json")
        with preserved.open("xb") as output:
            output.write(path.read_bytes())
        record["preserved_failure"] = (
            "BACKUP_EXPIRED_OR_CLOCK_INVALID; DB clock observed 1.5s ahead"
        )
        record["resume_backup_only"] = True
    clone, created = "proofflow_restore_" + uuid4().hex, False
    backup_id = None

    def persist():
        path.write_bytes(json.dumps(record, sort_keys=True, indent=2).encode())

    with LiveSession() as live:
        record["credit"] = live.credit
        require(
            live.sql("SELECT count(*) FROM pf_product.workspaces;") == (b"2" if resume else b"0"),
            "RESTORE_FIXTURE_REQUIRES_EMPTY_PRIVATE_PRODUCT",
        )
        require(
            live.sql("SELECT bool_and(blocked) FROM pf_budget.accounts;", "proofflow_budget")
            == b"t",
            "INFERENCE_MUST_BE_CLOSED",
        )
        persist()
        contract = (ROOT / "contracts/examples/synthetic-v1.1.json").read_bytes()
        data = {
            "pipeline": b"# synthetic backup/expiry fixture: no output\n",
            "transactions": b"merchant_id,transaction_id,customer_id,amount,currency,occurred_at\n"
            b"A,t1,c1,1.23,USD,2026-11-01T00:00:00Z\n",
            "customers": b"merchant_id,customer_id,canonical_customer_id\nA,c1,owner-A\n",
            "contract": contract,
        }
        assets, primary_ids = [], {}
        try:
            if resume:
                assets = resume_assets(live, record)
                primary, deleted = record["fixture_workspaces"]
            else:
                for index in range(2):
                    workspace = str(authority_id())
                    record["fixture_workspaces"].append(workspace)
                    persist()
                    live.sql(
                        "SET ROLE pf_product_provisioner; SELECT pf_product.create_workspace('"
                        + workspace
                        + "','operator',clock_timestamp()+interval '1 hour');"
                    )
                    client = live.login(workspace)
                    for kind, raw in (
                        data if index == 0 else {"pipeline": b"# deleted backup fixture\n"}
                    ).items():
                        asset = str(uuid4())
                        response = client.post("/v1/assets/" + kind + "/" + asset, content=raw)
                        require(response.status_code == 201, "RECOVERY_FIXTURE_UPLOAD_FAILED")
                        digest = hashlib.sha256(raw).hexdigest()
                        require(response.json()["sha256"] == digest, "RECOVERY_UPLOAD_CHANGED")
                        downloaded = client.get("/v1/assets/" + asset + "/download")
                        require(
                            downloaded.status_code == 200 and downloaded.content == raw,
                            "RECOVERY_AUTHORIZED_ASSET_READ_FAILED",
                        )
                        created_at = live.sql(
                            "SELECT created_at FROM pf_product.assets WHERE workspace_id='"  # noqa: S608 - generated UUIDs
                            + workspace
                            + "' AND id='"
                            + asset
                            + "';"
                        ).decode()
                        assets.append(
                            {
                                "workspace": workspace,
                                "sha256": digest,
                                "created_at": created_at,
                                "bytes": downloaded.content,
                            }
                        )
                        if index == 0:
                            primary_ids[kind] = asset
                primary, deleted = record["fixture_workspaces"]
                client = live.login(primary)
                response = client.post(
                    "/v1/contracts/" + primary_ids["contract"] + "/approve",
                    json={"expected_sha256": hashlib.sha256(contract).hexdigest(), "confirm": True},
                )
                require(response.status_code == 200, "FIXTURE_CONTRACT_APPROVAL_FAILED")
                live.opened = True
                live.admission(True)
                response = client.post(
                    "/v1/jobs",
                    json={
                        **{k + "_id": v for k, v in primary_ids.items()},
                        "idempotency_key": str(uuid4()),
                    },
                )
                require(response.status_code == 202, "EXPIRING_JOB_ENQUEUE_FAILED")
                job = response.json()["job_id"]
                record["job"] = job
                persist()
                require(UUID(job).version == 7, "JOB_ID_NOT_TIME_BOUND")
                deadline = time.monotonic() + 90
                while True:
                    reply = client.get("/v1/jobs/" + job)
                    require(reply.status_code == 200, "EXPIRING_JOB_READ_FAILED")
                    result = reply.json()
                    if result["state"] in ("NEEDS_REVIEW", "FAILED_INFRA", "CANCELLED"):
                        break
                    require(time.monotonic() < deadline, "EXPIRING_JOB_TIMEOUT")
                    time.sleep(1)
                record["job_result"] = result
                persist()
                require(
                    result["state"] == "NEEDS_REVIEW"
                    and result["outcome"] == "execution_failed"
                    and result["report"]["worker"]["cleanup"] == "confirmed",
                    "EXPIRING_WORKER_INTEGRATION_FAILED",
                )
                live.admission(False)
            # Quiesce all product writers while capturing this fixture DB. The
            # only workspaces are the two just created; no outside data is included.
            live.host(
                "systemctl stop proofflow-product-api.service proofflow-product-dispatcher.service"
            )
            try:
                snapshot = json.loads(live.sql(CURRENT_AUTHORITY_SQL))
                dump = live.host(
                    "docker exec --user=70:70 proofflow-budget pg_dump "
                    "-h /run/proofflow-budget -U postgres --no-owner --no-privileges "
                    "proofflow_product"
                )
            finally:
                live.host(
                    "systemctl start proofflow-product-api.service "
                    "proofflow-product-dispatcher.service"
                )
            key = AESGCM.generate_key(bit_length=256)
            now = wait_for_observation(snapshot["observed_at"])
            envelope = seal(snapshot, assets, dump, key, now=now)
            payload = open_backup(envelope, key, now=datetime.now(UTC))
            backup_id = save(envelope, key, datetime.fromisoformat(payload["expires_at"]))
            record["backup_id"] = backup_id
            record["encrypted_sha256"] = hashlib.sha256(envelope).hexdigest()
            persist()
            recovered, restored_key = recover(backup_id)
            require(recovered == envelope and restored_key == key, "OFFVM_BACKUP_ROUNDTRIP_CHANGED")
            client = live.login(deleted)
            require(
                client.post(
                    "/v1/workspace/delete", json={"workspace_id": deleted, "confirm": True}
                ).status_code
                == 200,
                "DELETION_REQUEST_FAILED",
            )
            live.host("systemctl start proofflow-product-retention.service")
            require(
                live.sql(
                    "SELECT count(*) FROM pf_product.workspaces WHERE id='"  # noqa: S608 - generated UUID
                    + deleted
                    + "';"
                )
                == b"0",
                "DELETED_WORKSPACE_NOT_RETIRED",
            )
            current = current_authority(live)
            plan = plan_restore(snapshot, current, now=datetime.now(UTC))
            require(plan["keep"] == [primary], "RESTORE_RESURRECTED_DELETED_WORKSPACE")
            live.sql("CREATE DATABASE " + clone + " TEMPLATE template0 CONNECTION LIMIT 0;")
            created = True
            clone_sql(live, base64.b64decode(payload["database"], validate=True).decode(), clone)
            clone_sql(live, quarantine_sql(clone, plan["keep"]), clone)
            require(
                clone_sql(live, "SELECT count(*) FROM pf_product.assets;", clone) == b"4",
                "RESTORED_REGISTRY_SCOPE_CHANGED",
            )
            for table in AUTHORITY_TABLES:
                count_query = "SELECT count(*) FROM pf_product." + table + ";"  # noqa: S608
                require(
                    clone_sql(live, count_query, clone) == b"0",
                    "RESTORED_AUTHORITY_PRESENT",
                )
            current = current_authority(live)
            receipt = run_asset_recovery(json.dumps({
                "envelope": base64.b64encode(recovered).decode(),
                "key": base64.b64encode(restored_key).decode(),
                "current": current,
            }).encode())
            require(
                len(receipt["assets"]) == 4
                and all(a["workspace"] == primary for a in receipt["assets"]),
                "OFFVM_ASSET_SCOPE_CHANGED",
            )
            revalidate_restore(
                snapshot, plan, current_authority(live), now=datetime.now(UTC)
            )
            record["asset_recovery"] = receipt
            live.sql("DROP DATABASE " + clone + ";")
            created = False
            client = live.login(primary)
            require(
                client.post(
                    "/v1/workspace/delete", json={"workspace_id": primary, "confirm": True}
                ).status_code
                == 200,
                "PRIMARY_FIXTURE_RETIREMENT_FAILED",
            )
            live.host("systemctl start proofflow-product-retention.service")
            require(
                live.sql("SELECT count(*) FROM pf_product.workspaces;") == b"0",
                "FIXTURE_WORKSPACE_REMAINS",
            )
            retire(backup_id)
            record.update(
                completed=True,
                backup_key_and_ciphertext_retired=True,
                clone_removed=True,
                workspaces_retired=True,
                finished_at=datetime.now(UTC).isoformat(),
            )
            persist()
            print(
                json.dumps(
                    {
                        "encrypted_offvm_recovery": "passed",
                        "assets_recovered": 4,
                        "deleted_workspace_excluded": True,
                        "time_bound_job": "passed",
                        "runtime_authority_restored": False,
                        "cleanup": "confirmed",
                    }
                )
            )
        finally:
            if created:
                live.sql("DROP DATABASE " + clone + ";")
            live.admission(False)
            persist()


if __name__ == "__main__":
    main()
