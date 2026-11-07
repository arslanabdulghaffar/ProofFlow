"""One-shot private API-container rebuild; NOT a compromised-host recovery claim.

Closed admissions, fresh credit guard, empty/idle product, pinned installer/image.
Archive the stopped predecessor; rebuild fixed service, compare durable authority,
test revoked session and intact bytes, then retire only this new synthetic workspace.
Failure leaves evidence for reconciliation and never blindly repeats the rebuild.
"""

import hashlib
import json
import os
import re
import shlex
import ssl
from datetime import UTC, datetime
from uuid import uuid4

import httpx
from check_product_image import IMAGE, PROBE
from install_product_services import validate_container
from product_live_session import ORIGIN, LiveSession, require
from vultr_phase1 import PRIVATE, ROOT

from worker.protocol import authority_id

AUTHORITY = """SELECT json_build_object(
 'workspaces',(SELECT json_agg(row_to_json(t) ORDER BY id) FROM pf_product.workspaces t),
 'sessions',(SELECT json_agg(x ORDER BY x::text) FROM
             (SELECT row_to_json(t) x FROM pf_product.sessions t) s),
 'assets',(SELECT json_agg(x ORDER BY x::text) FROM
           (SELECT row_to_json(t) x FROM pf_product.assets t) a),
 'jobs',(SELECT count(*) FROM pf_product.jobs),
 'repairs',(SELECT count(*) FROM pf_product.repairs),
 'versions',(SELECT count(*) FROM pf_product.versions),
 'pr_intents',(SELECT count(*) FROM pf_product.pr_intents));"""


def main():
    path = PRIVATE / "evidence/phase5-incident-api-rebuild.json"
    require(not path.exists(), "INCIDENT_REBUILD_ALREADY_STARTED_RECONCILE")
    installed = json.loads((PRIVATE / "evidence/product-service-install.json").read_bytes())
    revision = installed["revision"]
    require(re.fullmatch("[0-9a-f]{64}", revision) is not None, "INSTALLER_REVISION_INVALID")
    require(installed["sources"]["install_product_services.py"] == hashlib.sha256(
        (ROOT / "scripts/install_product_services.py").read_bytes()).hexdigest(),
        "INSTALLER_SOURCE_NOT_DEPLOYED")
    installer = "/var/lib/proofflow-product-setup/revisions/" + revision
    record = {"started_at": datetime.now(UTC).isoformat(), "completed": False,
              "scope": "real_private_API_container_rebuild_same_trusted_host",
              "image": IMAGE, "installer_revision": revision, "new_resources": 0,
              "provider_calls": 0, "host_reimage": False, "checks": []}

    def persist(stage):
        record["stage"] = stage
        pending = path.with_suffix(".pending")
        with pending.open("xb") as output:
            output.write(json.dumps(record, indent=2).encode())
            output.flush()
            os.fsync(output.fileno())
        os.replace(pending, path)

    with LiveSession() as live:
        record["credit"] = live.credit
        require(live.sql("SELECT count(*) FROM pf_product.workspaces;") == b"0",
                "INCIDENT_FIXTURE_REQUIRES_EMPTY_PRODUCT")
        require(live.sql("SELECT count(*) FROM pf_product.jobs WHERE state NOT IN "
                         "('NEEDS_REVIEW','FAILED_INFRA','CANCELLED');") == b"0", "JOBS_NOT_IDLE")
        require(live.sql("SELECT bool_and(blocked) FROM pf_budget.accounts;",
                         "proofflow_budget") == b"t", "INFERENCE_MUST_STAY_CLOSED")
        require(live.sql("SELECT count(*) FROM pf_product.pr_intents WHERE lease_owner IS NOT NULL "
                         "OR state IN ('BRANCH_PENDING','COMMIT_PENDING','PR_PENDING');") == b"0",
                "EXTERNAL_WRITES_NOT_IDLE")
        image = json.loads(live.host("docker image inspect sha256:" + IMAGE))[0]
        before = json.loads(live.host("docker inspect proofflow-product-api"))[0]
        validate_container(before, "api", image["Config"]["Env"])
        for name, digest in installed["sources"].items():
            require(name in ("settings.json", "install_product_services.py"), "INSTALLER_MANIFEST")
            require(live.host("sha256sum " + installer + "/" + name).decode().split()[0] == digest,
                    "INSTALLER_BYTES_CHANGED")
        workspace = str(authority_id())
        record.update(workspace=workspace, before_container=before["Id"],
                      archived_container="proofflow-product-api-incident-" + uuid4().hex)
        persist("fixture_creation_pending")
        live.sql("SET ROLE pf_product_provisioner; SELECT pf_product.create_workspace('"
                 + workspace + "','operator',clock_timestamp()+interval '1 hour');")
        client = live.login(workspace)
        asset = str(uuid4())
        raw = b"# inert incident-rebuild fixture; never execute\n"
        require(client.post("/v1/assets/pipeline/" + asset, content=raw).status_code == 201,
                "INCIDENT_FIXTURE_UPLOAD_FAILED")
        revoked_headers = dict(client.headers)
        require(client.post("/v1/logout").status_code == 204, "INCIDENT_REVOCATION_FAILED")
        require(client.get("/v1/session").status_code == 403, "REVOCATION_NOT_OBSERVED")
        authority_before = hashlib.sha256(live.sql(AUTHORITY)).hexdigest()
        record["authority_before_sha256"] = authority_before
        record["checks"].append("session_revoked_before_rebuild")
        persist("stop_pending")
        live.host("systemctl stop proofflow-product-api.service")
        stopped = json.loads(live.host("docker inspect proofflow-product-api"))[0]
        require(stopped["Id"] == before["Id"] and not stopped["State"]["Running"],
                "INCIDENT_PREDECESSOR_NOT_STOPPED")
        persist("archive_pending")
        live.host("docker rename proofflow-product-api " + record["archived_container"])
        persist("rebuild_pending")
        rebuilt = json.loads(live.host("/usr/bin/python3 -I -B "
                                       + installer + "/install_product_services.py"))
        require(rebuilt["image"] == IMAGE, "INCIDENT_IMAGE_CHANGED")
        after = json.loads(live.host("docker inspect proofflow-product-api"))[0]
        validate_container(after, "api", image["Config"]["Env"])
        require(after["Id"] != before["Id"] and after["State"]["Running"],
                "API_NOT_RECONSTRUCTED")
        require(live.host("docker inspect --format '{{.State.Running}}' "
                          + record["archived_container"]) == b"false", "PREDECESSOR_RESTARTED")
        record["after_container"] = after["Id"]
        record["authority_after_sha256"] = hashlib.sha256(live.sql(AUTHORITY)).hexdigest()
        require(record["authority_after_sha256"] == authority_before,
                "AUTHORITY_CHANGED_ON_REBUILD")
        inventory = json.loads(live.host("docker exec --user=10003:10003 proofflow-product-api "
                                        "python -I -B -c " + shlex.quote(
                                            "import sys;sys.path.insert(0,'/app');" + PROBE)))
        expected = {line[1:] for line in (ROOT / ".dockerignore").read_text().splitlines()
                    if line.startswith(("!api/", "!contracts/", "!orchestrator/", "!integrations/",
                                        "!worker/", "!verifier/"))
                    and line.endswith((".py", ".js", ".css", ".html"))}
        require(inventory.keys() == expected and all(hashlib.sha256((ROOT / n).read_bytes())
                .hexdigest() == digest for n, digest in inventory.items()), "REBUILT_SOURCE_DRIFT")
        record["source_files_verified"] = len(inventory)
        persist("rebuild_verified_http_pending")
        # New transport connection, same revoked credentials: never provision a
        # replacement identity for this negative assertion.
        context = ssl.create_default_context(cafile=str(PRIVATE / "tls/ca.pem"))
        with httpx.Client(base_url=ORIGIN, headers=revoked_headers, trust_env=False,
                          timeout=20, verify=context) as old:
            require(old.get("/v1/session").status_code == 403, "REBUILD_REVIVED_SESSION")
        client = live.login(workspace)
        response = client.get("/v1/assets/" + asset + "/download")
        require(response.status_code == 200 and response.content == raw, "REBUILD_ASSET_CHANGED")
        require(client.get("/health/ready").status_code == 503, "REBUILD_OPENED_READINESS")
        record["checks"].extend(["new_container_exact_image_config_and_sources",
            "durable_authority_unchanged", "revoked_session_stays_denied",
            "fresh_authorized_session_reads_exact_asset", "readiness_stays_closed"])
        persist("cleanup_pending")
        require(client.post("/v1/workspace/delete",
                json={"workspace_id": workspace, "confirm": True}).status_code == 200,
                "INCIDENT_FIXTURE_DELETE_FAILED")
        live.host("systemctl start proofflow-product-retention.service")
        require(live.sql("SELECT count(*) FROM pf_product.workspaces;") == b"0",
                "INCIDENT_FIXTURE_CLEANUP_UNCERTAIN")
        require(live.sql("SELECT enabled FROM pf_product.execution_policy;") == b"f"
                and live.sql("SELECT bool_and(blocked) FROM pf_budget.accounts;",
                             "proofflow_budget") == b"t", "ADMISSION_CHANGED")
        record.update(completed=True, finished_at=datetime.now(UTC).isoformat(),
                      cleanup_confirmed=True, product_admission="closed",
                      inference_admission="closed")
        persist("completed")
    print(json.dumps({"completed": True, "checks": record["checks"],
                      "source_files_verified": len(inventory), "cleanup_confirmed": True,
                      "host_reimage": False, "new_resources": 0}))


if __name__ == "__main__":
    main()
