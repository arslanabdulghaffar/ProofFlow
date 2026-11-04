"""Trusted private HTTP integration client. Fixture programs are bytes sent to the worker."""

import base64
import hashlib
import json
import ssl
import sys
import time
from uuid import uuid4

import httpx


def require(condition, code):
    if not condition:
        raise RuntimeError(code)


def main():
    data = json.loads(sys.stdin.buffer.read(131072))
    transport = httpx.HTTPTransport(uds="/run/proofflow-product-api/api.sock",
        verify=ssl.create_default_context(cafile="/etc/proofflow-product/tls/ca.pem"))
    headers = {"Cookie": "__Host-proofflow=" + data["session"],
               "Origin": "https://127.0.0.1:18443", "X-ProofFlow-CSRF": data["csrf"]}
    checks, results = [], []
    with httpx.Client(transport=transport, base_url="https://127.0.0.1:18443",
                      headers=headers, timeout=15) as client:
        require(client.get("/health/live").status_code == 200, "LIVENESS_FAILED")
        require(client.get("/health/ready").status_code == 503, "FALSE_READINESS")
        require(client.get("/v1/session").json()["workspace_id"] == data["workspace"],
                "SCRAM_SESSION_FAILED")
        require(client.get("/v1/session", headers={"Cookie": ""}).status_code == 403,
                "UNAUTHENTICATED_REQUEST_ALLOWED")
        require(client.post("/v1/jobs", json={}, headers={"X-ProofFlow-CSRF": ""})
                .status_code == 403, "CSRF_ALLOWED")
        checks.append("actual_tls_scram_session_auth_csrf_readiness")
        for case in data["cases"]:
            ids = {}
            for kind in ("pipeline", "transactions", "customers", "contract"):
                raw = base64.b64decode(case[kind], validate=True)
                identifier = str(uuid4())
                response = client.post("/v1/assets/" + kind + "/" + identifier, content=raw)
                require(response.status_code == 201, "UPLOAD_" + kind.upper() + "_FAILED")
                require(response.json()["sha256"] == hashlib.sha256(raw).hexdigest(),
                        "UPLOAD_HASH_CHANGED")
                require(client.get("/v1/assets/" + identifier + "/download").content == raw,
                        "DOWNLOAD_BYTES_CHANGED")
                foreign = {"Cookie": "__Host-proofflow=" + data["foreign_session"]}
                require(client.get("/v1/assets/" + identifier + "/download", headers=foreign)
                        .status_code == 404, "CROSS_WORKSPACE_DISCLOSURE")
                ids[kind + "_id"] = identifier
            contract_hash = hashlib.sha256(base64.b64decode(case["contract"])).hexdigest()
            approval = "/v1/contracts/" + ids["contract_id"] + "/approve"
            require(client.post(approval, json={"expected_sha256": "0" * 64, "confirm": True})
                    .status_code == 409, "WRONG_VERSION_APPROVED")
            require(client.post(approval, json={"expected_sha256": contract_hash, "confirm": True})
                    .status_code == 200, "EXACT_APPROVAL_FAILED")
            request = {**ids, "idempotency_key": case["idempotency_key"]}
            enqueued = client.post("/v1/jobs", json=request)
            require(enqueued.status_code == 202, "ENQUEUE_FAILED")
            job = enqueued.json()["job_id"]
            require(client.post("/v1/jobs", json=request).json()["job_id"] == job,
                    "IDEMPOTENCY_CREATED_SECOND_JOB")
            for _ in range(90):
                result = client.get("/v1/jobs/" + job).json()
                if result["state"] in ("NEEDS_REVIEW", "FAILED_INFRA", "CANCELLED"):
                    break
                time.sleep(1)
            require(result["state"] == "NEEDS_REVIEW", "ORIGINAL_NOT_REVIEWABLE")
            require(result["outcome"] == case["expected"], "ORIGINAL_OUTCOME_CHANGED")
            if case["expected"] == "mismatch":
                semantic = result["report"]["semantic"]["report"]["result"]
                require(any(f["check"] == "V04" for f in semantic["findings"]), "OWNER_NOT_CAUGHT")
                require(bool(semantic["ownership_witnesses"]), "NO_OWNERSHIP_WITNESS")
                page = client.get("/jobs/" + job)
                require(page.status_code == 200 and "owner-A" in page.text
                        and "owner-B" in page.text, "FAILURE_VIEW_MISSING_ACTUAL_EVIDENCE")
            elif case["expected"] == "held":
                require(result["report"]["semantic"]["report"]["result"]
                        ["blocking_occurrences"] == 2, "EXCLUSION_HID_MISSING_ATTRIBUTE")
            else:
                require(result.get("execution_id") is None, "INVALID_INPUT_DISPATCHED")
            results.append(result)
            print(json.dumps({"case": case["name"], "state": result["state"],
                              "outcome": result["outcome"]}), file=sys.stderr, flush=True)
        require(client.post("/v1/logout").status_code == 204, "LOGOUT_FAILED")
        require(client.get("/v1/session").status_code == 403, "REVOKED_SESSION_ALLOWED")
        checks.extend(["immutable_upload_download_workspace_isolation_exact_approval",
                       "scoped_enqueue_idempotency_actual_worker_bounded_verifier",
                       "persisted_wrong_owner_witness_failure_page",
                       "q08_filtered_missing_attribute_held",
                       "invalid_input_rejected_without_worker", "session_revocation"])
    print(json.dumps({"checks": checks, "jobs": results, "fixture_only": True,
                      "provider_calls": 0}))


if __name__ == "__main__":
    main()
