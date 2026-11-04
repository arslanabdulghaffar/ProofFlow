"""Fixed synthetic recovery client: API only, never executes the submitted fixture."""

import base64
import hashlib
import json
import ssl
import sys
from uuid import uuid4

import httpx


def main():
    data = json.loads(sys.stdin.buffer.read(131072))
    transport = httpx.HTTPTransport(uds="/run/proofflow-product-api/api.sock",
        verify=ssl.create_default_context(cafile="/etc/proofflow-product/tls/ca.pem"))
    with httpx.Client(transport=transport, base_url="https://127.0.0.1:18443", timeout=15,
        headers={"Cookie": "__Host-proofflow=" + data["session"],
                 "Origin": "https://127.0.0.1:18443", "X-ProofFlow-CSRF": data["csrf"]}) as client:
        if data["operation"] == "enqueue":
            ids = {}
            for kind in ("pipeline", "transactions", "customers", "contract"):
                raw = base64.b64decode(data[kind], validate=True)
                identifier = str(uuid4())
                response = client.post("/v1/assets/" + kind + "/" + identifier, content=raw)
                if response.status_code != 201:
                    raise RuntimeError("RECOVERY_UPLOAD_FAILED")
                ids[kind + "_id"] = identifier
                if kind == "contract":
                    response = client.post("/v1/contracts/" + identifier + "/approve", json={
                        "expected_sha256": hashlib.sha256(raw).hexdigest(), "confirm": True})
                    if response.status_code != 200:
                        raise RuntimeError("RECOVERY_APPROVAL_FAILED")
            response = client.post("/v1/jobs", json={**ids,
                "idempotency_key": data["idempotency_key"]})
            if response.status_code != 202:
                raise RuntimeError("RECOVERY_ENQUEUE_FAILED")
        elif data["operation"] == "cancel":
            response = client.post("/v1/jobs/" + data["job"] + "/cancel")
            if response.status_code != 200:
                raise RuntimeError("RECOVERY_CANCEL_FAILED")
        else:
            raise RuntimeError("RECOVERY_OPERATION_INVALID")
        print(json.dumps(response.json()))


if __name__ == "__main__":
    main()
