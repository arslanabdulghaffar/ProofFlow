"""One new nonempty scheduled-path capture and Windows-to-Linux inert recovery.

Ephemeral test password goes only over stdin and is never saved. This is not the
owner's offline custody step or permission to restore a compromised SQL dump.
"""

import base64
import hashlib
import json
import secrets
import subprocess
from datetime import UTC, datetime
from uuid import uuid4

from asset_backup_vault import recover
from product_live_session import PRIVATE, LiveSession, require
from recovery_clock import wait_for_observation
from scheduled_product_backup import run

from orchestrator.portable_backup import export_portable
from orchestrator.restore_guard import CURRENT_AUTHORITY_SQL
from worker.protocol import authority_id

PROBE = """
import base64,hashlib,json,sys
from datetime import UTC,datetime
from orchestrator.portable_backup import recover_portable
v=json.load(sys.stdin)
payload,plan,assets=recover_portable(base64.b64decode(v['package']),
 base64.b64decode(v['password']),v['current'],now=datetime.now(UTC))
print(json.dumps({'keep':len(plan['keep']),'assets':len(assets),
 'asset_hashes':[hashlib.sha256(a[2]).hexdigest() for a in assets],
 'quarantined':plan['mode']=='QUARANTINED_DATA_ONLY'}))
"""


def main():
    path = PRIVATE / "evidence/phase6-portable-cross-platform.json"
    require(not path.exists(), "RECONCILE_PORTABLE_DRILL_RECEIPT")
    workspace = str(authority_id())
    raw = b"inert synthetic portable recovery fixture; never executed"
    record = {"workspace":workspace,"completed":False,"provider_calls":0,
              "new_resources":0,"observed_at":datetime.now(UTC).isoformat()}

    def persist():
        path.write_text(json.dumps(record,indent=2,sort_keys=True),encoding="utf-8")

    def probe(current):
        wait_for_observation(current["observed_at"])
        response = subprocess.run(  # noqa: S603 - fixed trusted inert crypto check, no candidate
            ["C:/Windows/System32/wsl.exe","-d","Ubuntu-24.04","--",
             "/root/.proofflow-phase5-venv/bin/python","-c",PROBE],
            input=json.dumps({"package":base64.b64encode(package).decode(),
                "password":base64.b64encode(password).decode(),"current":current}).encode(),
            capture_output=True,timeout=30)
        require(response.returncode == 0, "CROSS_PLATFORM_RECOVERY_FAILED")
        return json.loads(response.stdout)

    persist()
    try:
        with LiveSession() as live:
            require(live.sql("SELECT count(*) FROM pf_product.workspaces;") == b"0",
                    "PORTABLE_DRILL_REQUIRES_EMPTY_PRODUCT")
            live.sql("SET ROLE pf_product_provisioner; SELECT pf_product.create_workspace('"
                     +workspace+"','operator',clock_timestamp()+interval '1 hour');")
            client = live.login(workspace,minutes=20)
            reply = client.post("/v1/assets/pipeline/"+str(uuid4()),content=raw)
            require(reply.status_code == 201,"PORTABLE_FIXTURE_UPLOAD_FAILED")
        captured = run(force=True)
        require(captured["asset_count"] == 1,"NONEMPTY_CAPTURE_FAILED")
        record["capture"] = captured
        persist()
        envelope,key = recover(captured["backup_id"])
        password = secrets.token_bytes(32)
        package = export_portable(envelope,key,password,now=datetime.now(UTC))
        with LiveSession() as live:
            record["before_deletion"] = probe(json.loads(live.sql(CURRENT_AUTHORITY_SQL)))
            require(record["before_deletion"] == {"keep":1,"assets":1,
                "asset_hashes":[hashlib.sha256(raw).hexdigest()],"quarantined":True},
                "CROSS_PLATFORM_ASSET_MISMATCH")
            client = live.login(workspace,minutes=10)
            require(client.post("/v1/workspace/delete",json={"workspace_id":workspace,
                "confirm":True}).status_code == 200,"PORTABLE_DELETE_FAILED")
            live.host("systemctl start proofflow-product-retention.service")
            record["after_deletion"] = probe(json.loads(live.sql(CURRENT_AUTHORITY_SQL)))
            require(record["after_deletion"]["assets"] == record["after_deletion"]["keep"] == 0,
                    "DELETED_PORTABLE_ASSET_REVIVED")
            record["credit"] = live.credit
            record["completed"] = True
    finally:
        with LiveSession() as live:
            if live.sql("SELECT count(*) FROM pf_product.workspaces WHERE id='"  # noqa: S608
                        +workspace+"';") != b"0":
                client = live.login(workspace,minutes=10)
                require(client.post("/v1/workspace/delete",json={"workspace_id":workspace,
                    "confirm":True}).status_code == 200,"PORTABLE_CLEANUP_FAILED")
                live.host("systemctl start proofflow-product-retention.service")
            record["cleanup_confirmed"] = live.sql(
                "SELECT count(*) FROM pf_product.workspaces;") == b"0"
            persist()
    require(record["cleanup_confirmed"],"PORTABLE_CLEANUP_UNCERTAIN")
    print(json.dumps({"completed":True,"nonempty_capture":True,"windows_to_linux":True,
                      "deleted_assets_recovered":0,"owner_offline_key_custody":"NOT_DONE"}))


if __name__ == "__main__":
    main()
