"""Read-only private deployed edge/source policy; no execution or public activation."""

import hashlib
import json
import shlex
import ssl
from datetime import UTC, datetime

import httpx
from check_product_image import IMAGE, PROBE
from install_product_services import validate_container
from probe_public_ingress_http import probe
from product_live_session import ORIGIN, LiveSession, require
from vultr_phase1 import PRIVATE, ROOT


def main():
    with LiveSession() as live:
        with httpx.Client(base_url=ORIGIN, trust_env=False, timeout=10,
                          verify=ssl.create_default_context(cafile=str(PRIVATE / "tls/ca.pem")),
                          follow_redirects=False) as client:
            result = probe(client)
        image = json.loads(live.host("docker image inspect sha256:" + IMAGE))[0]
        for role in ("api", "dispatcher"):
            config = json.loads(live.host("docker inspect proofflow-product-" + role))[0]
            validate_container(config, role, image["Config"]["Env"])
            require(config["State"]["Running"], "SERVICE_NOT_RUNNING")
        inventory = json.loads(live.host("docker exec proofflow-product-api python -c "
                                         + shlex.quote(PROBE)))
        for name, digest in inventory.items():
            require(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest,
                    "DEPLOYED_SOURCE_MISMATCH")
        private = live.host("test ! -e /etc/proofflow-product-api/tls/origin.json "
                            "&& test ! -e /etc/proofflow-public/enabled && echo private")
        require(private == b"private", "PUBLIC_CONFIGURATION_UNEXPECTED")
        require(live.sql("SELECT count(*)=1 AND bool_and(blocked) FROM pf_budget.accounts;",
                         "proofflow_budget") == b"t", "INFERENCE_NOT_CLOSED")
        require(live.sql("SELECT count(*) FROM pf_product.workspaces;") == b"0",
                "WORKSPACES_REMAIN")
        result.update(observed_at=datetime.now(UTC).isoformat(), image=IMAGE,
                      source_files=len(inventory), source_hashes_match=True,
                      container_policy="verified both roles", product_admission="closed",
                      inference_admission="closed", workspaces=0, credit=live.credit,
                      network_path="private pinned SSH/TLS only; not public acceptance")
        path = PRIVATE / "evidence/phase6-ingress-readback-2026-11-08.json"
        with path.open("x", encoding="utf-8") as output:
            json.dump(result, output, sort_keys=True)
        print(json.dumps({k: v for k, v in result.items() if k != "credit"}))


if __name__ == "__main__":
    main()
