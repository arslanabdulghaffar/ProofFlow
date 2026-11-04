"""Existing deployed dispatcher read-only GitHub checks; no preview, approval or candidate run."""

import hashlib
import json
import ssl
from datetime import UTC, datetime
from pathlib import Path

import httpx
from install_product_services import IMAGE
from product_live_session import ORIGIN, PRIVATE, LiveSession, require

REMOTE = r'''
import asyncio,hashlib,json
from pathlib import Path
from integrations.github_setup import load_github_app
from integrations.github_app import GitHubFailure,dedicated_tree

async def main():
    app=load_github_app()
    assert app is not None
    original=app.request
    calls=[]
    async def restricted(method,path,*args,**kwargs):
        assert method=='GET' or (method=='POST' and path==
            '/app/installations/'+str(app.config.installation_id)+'/access_tokens')
        calls.append({'method':method,'path':path})
        return await original(method,path,*args,**kwargs)
    app.request=restricted
    token=await app.token()
    base=await app.inspect_base(token)
    absent=[]
    for intent in ('5bcb30d6-05d9-4381-b466-6a2ba948909f',
                   '709af4a1-4367-44f8-884a-8b4ec4f86fe5'):
        assert await app.read_branch(token,intent) is None
        assert await app.find_pr(token,intent) is None
        absent.append(intent)
    for mode in ('100755','120000','160000'):
        try:
            dedicated_tree({'sha':'a'*40,'truncated':False,'tree':[
                {'path':'pipeline.py','mode':mode,'type':'blob','sha':'b'*40}]},
                'a'*40,'pipeline.py')
        except GitHubFailure: pass
        else: raise RuntimeError('mode')
    try: app.verify_pr([],absent[0],'a'*40,'b'*40,'fixture','fixture')
    except GitHubFailure: pass
    else: raise RuntimeError('shape')
    print(json.dumps({'repository_id':app.config.repository_id,'private':True,
        'base_sha':base['base_sha'],'base_tree_sha':base['base_tree_sha'],
        'expired_intents_without_branch_or_pr':absent,'calls':calls,
        'mode_and_malformed_shape_checks':'passed_trusted_static_fixtures',
        'adapter_sha256':hashlib.sha256(Path('/app/integrations/github_app.py').read_bytes()).hexdigest()}))
try: asyncio.run(main())
except Exception: raise SystemExit('READ_ONLY_GITHUB_PROBE_FAILED') from None
'''


def main():
    with LiveSession() as live:
        require(
            live.sql("SELECT bool_and(blocked) FROM pf_budget.accounts;", "proofflow_budget")
            == b"t", "INFERENCE_NOT_BLOCKED",
        )
        require(live.sql("SELECT count(*) FROM pf_product.pr_writes;") == b"0", "WRITE_FOUND")
        for role in ("api", "dispatcher"):
            require(
                live.host("docker inspect --format '{{.Image}}' proofflow-product-" + role)
                == ("sha256:" + IMAGE).encode(), "DEPLOYED_IMAGE_CHANGED",
            )
        services = live.host(
            "systemctl is-active proofflow-product-api.service "
            "proofflow-product-dispatcher.service proofflow-product-retention.timer"
        ).decode().splitlines()
        require(services == ["active"] * 3, "SERVICE_NOT_ACTIVE")
        remote = json.loads(live.host(
            "docker exec -i --user=10003:10003 proofflow-product-dispatcher python -B -",
            REMOTE.encode(),
        ))
        require(
            remote["adapter_sha256"] == hashlib.sha256(
                (Path(__file__).resolve().parents[1] / "integrations/github_app.py").read_bytes()
            ).hexdigest(), "DEPLOYED_ADAPTER_SOURCE_CHANGED",
        )
        with httpx.Client(
            base_url=ORIGIN, trust_env=False, timeout=10,
            verify=ssl.create_default_context(cafile=str(PRIVATE / "tls/ca.pem")),
        ) as client:
            require(client.get("/health/live").status_code == 200, "API_NOT_LIVE")
            require(client.get("/").status_code == 200, "WORKBENCH_UNAVAILABLE")
            require(client.get("/v1/session").status_code == 403, "ANONYMOUS_SESSION_ACCEPTED")
            readiness = client.get("/health/ready")
            require(readiness.status_code == 503, "PREMATURE_READY_CLAIM")
        require(live.sql("SELECT count(*) FROM pf_product.pr_writes;") == b"0", "WRITE_FOUND")
        receipt = {
            "observed_at": datetime.now(UTC).isoformat(), "product_image_sha256": IMAGE,
            "deployed_dispatcher_github": remote, "services": services,
            "private_tls_http": "live200_workbench200_anonymous403_acceptance_incomplete503",
            "credit": live.credit, "external_writes": 0, "new_previews": 0,
            "new_worker_executions": 0, "provider_calls": 0, "new_cloud_resources": 0,
            "product_inference_admission": "closed",
        }
        (PRIVATE / "evidence/phase4-readback-hardening-result.json").write_text(
            json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(receipt))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("READBACK_HARDENING_CHECK_FAILED_RECONCILE_DEPLOYMENT") from None
