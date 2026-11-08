"""Private desktop backup job: bounded consistent DB + immutable asset bytes.

Runs only under the operator's existing DPAPI identity. Closed/idle deployment is
required; a busy run fails visibly and the hourly trigger retries later. No paid
resource, admission change, candidate execution or restored runtime authority.
"""

import base64
import hashlib
import json
import os
import shlex
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from asset_backup_vault import expire, recover, save
from check_product_image import IMAGE
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from export_portable_backup import checked_backup
from product_live_session import PRIVATE, LiveSession, require
from recovery_clock import wait_for_observation

from orchestrator.asset_backup import open_backup, seal
from orchestrator.restore_guard import CURRENT_AUTHORITY_SQL, plan_restore

LATEST = PRIVATE / "scheduled-backup-latest.json"
ASSETS = """
import base64,json,os,sys
from uuid import UUID
sys.path.insert(0,'/app')
from api.app.workspace_assets import WorkspaceAssets
rows=json.loads(sys.stdin.buffer.read(131073))
assert isinstance(rows,list) and len(rows)<=256
fd=os.open('/var/lib/proofflow-product/assets',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
try:
 store=WorkspaceAssets(fd); result=[]; seen=set(); total=0
 for row in rows:
  w=UUID(row['workspace_id']); digest=row['sha256']; identity=(str(w),digest)
  if identity in seen: continue
  seen.add(identity)
  raw=store.read(w,digest)
  assert len(raw)==row['byte_size']
  total+=len(raw)
  assert total<=16*1024*1024
  result.append({'workspace':str(w),'sha256':digest,'created_at':row['created_at'],
                 'bytes':base64.b64encode(raw).decode()})
 print(json.dumps(result))
finally: os.close(fd)
"""


def due(previous, now):
    if previous is None:
        return True
    captured = datetime.fromisoformat(previous["snapshot_at"])
    expiry = datetime.fromisoformat(previous["expires_at"])
    require(captured.tzinfo is not None and expiry.tzinfo is not None and captured <= now,
            "BACKUP_CLOCK_OR_RECEIPT_INVALID")
    return now >= min(captured + timedelta(hours=12), expiry - timedelta(hours=2))


def unique_registry(rows):
    require(type(rows) is list and len(rows) <= 256, "BACKUP_REGISTRY_LIMIT")
    unique = {}
    for row in rows:
        identity = (str(UUID(row["workspace_id"])), row["sha256"])
        prior = unique.get(identity)
        if prior:
            require(prior["byte_size"] == row["byte_size"], "BACKUP_REGISTRY_CONFLICT")
        if prior is None or datetime.fromisoformat(row["created_at"]) < datetime.fromisoformat(
            prior["created_at"]
        ):
            unique[identity] = row
    return list(unique.values())


def capture(live):
    require(live.host("docker inspect --format '{{.Image}}' proofflow-product-api")
            == ("sha256:"+IMAGE).encode(), "BACKUP_ASSET_READER_IMAGE_CHANGED")
    guard = Path("orchestrator/restore_guard.py").read_text(encoding="utf-8")
    source = Path("scripts/consistent_product_backup.py").read_text(encoding="utf-8")
    imported = ("from orchestrator.restore_guard import "
                "CURRENT_AUTHORITY_SQL, check_dump, inventory")
    require(source.count(imported) == 1, "CAPTURE_SOURCE_CHANGED")
    program = guard + "\n" + source.replace(imported, "") + "\n" + """
import base64
with snapshot('proofflow-budget') as captured:
 raw=captured.dump()
 print(json.dumps({'snapshot':captured.inventory,'registry':captured.assets,
                   'database':base64.b64encode(raw).decode()}))
"""
    result = json.loads(live.host("python3 -I -", program.encode()))
    # This fixed trusted reader runs in the network-denied API container, as its
    # existing nonroot identity. Uploaded source is read as inert bytes only.
    command = ("docker exec -i --user=10003:10003 proofflow-product-api "
               "timeout -s KILL 25 python -I -c " + shlex.quote(ASSETS))
    registry = unique_registry(result["registry"])
    assets = json.loads(live.host(command, json.dumps(registry).encode()))
    for asset in assets:
        asset["bytes"] = base64.b64decode(asset["bytes"], validate=True)
    current = json.loads(live.sql(CURRENT_AUTHORITY_SQL))
    now = wait_for_observation(current["observed_at"])
    plan = plan_restore(result["snapshot"], current, now=now)
    require(not plan["exclude"], "BACKUP_SOURCE_REVOKED_DURING_CAPTURE")
    return result["snapshot"], assets, base64.b64decode(result["database"], validate=True)


def run(*, force=False):
    expire()  # Enforce expiry even when a cloud/busy check subsequently fails.
    require(not LATEST.with_suffix(".pending").exists(), "BACKUP_RECEIPT_RECONCILE_REQUIRED")
    previous = json.loads(LATEST.read_bytes()) if LATEST.exists() else None
    if not force and not due(previous, datetime.now(UTC)):
        # A recent timestamp alone does not establish that the key/envelope still
        # exists and authenticates. Fail visibly rather than report healthy coverage.
        envelope, key = recover(previous["backup_id"])
        checked_backup(previous, envelope, key, now=datetime.now(UTC))
        return {"scheduled_backup": "not_due", "expires_at": previous["expires_at"]}
    # Consistent capture is read-only with respect to product authority. A live
    # judging window need not be closed; existing active-job/repair checks stay.
    with LiveSession(observation_only=True) as live:
        require(live.sql("SELECT count(*) FROM pf_product.jobs WHERE state NOT IN "
                         "('NEEDS_REVIEW','FAILED_INFRA','CANCELLED');") == b"0",
                "BACKUP_RETRY_WHEN_IDLE")
        snapshot, assets, database = capture(live)
        key = AESGCM.generate_key(bit_length=256)
        now = wait_for_observation(snapshot["observed_at"])
        envelope = seal(snapshot, assets, database, key, now=now)
        payload = open_backup(envelope, key, now=datetime.now(UTC))
        identifier = save(envelope, key, datetime.fromisoformat(payload["expires_at"]))
        returned, returned_key = recover(identifier)
        require(returned == envelope and returned_key == key, "BACKUP_VAULT_READBACK_FAILED")
        record = {"scheduled_backup": "captured", "backup_id": identifier,
                  "snapshot_at": snapshot["observed_at"], "expires_at": payload["expires_at"],
                  "database_bytes": len(database), "asset_count": len(assets),
                  "encrypted_sha256": hashlib.sha256(envelope).hexdigest(),
                  "credit": live.credit, "provider_calls": 0, "new_resources": 0,
                  "workspace_count": len(snapshot["workspaces"])}
        pending = LATEST.with_suffix(".pending")
        with pending.open("x", encoding="utf-8") as output:
            json.dump(record, output, sort_keys=True)
            output.flush()
            os.fsync(output.fileno())
        pending.replace(LATEST)
        return record


if __name__ == "__main__":
    print(json.dumps(run()))
