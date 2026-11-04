"""Use only after the owner approves the exact current preview; never renew authority."""

import argparse
import asyncio
import json
import ssl
import time
from datetime import UTC, datetime
from uuid import UUID

import httpx
from check_phase4_expired_approval import existing_session
from prepare_github_app import preflight, protected_local
from product_live_session import ORIGIN, PRIVATE, LiveSession, require
from refresh_phase4_pr_preview import RECORD


def approve_exact(client, record, approved_digest, now):
    expected = record["pr"]
    require(
        approved_digest == expected["preview_sha256"], "EXACT_OPERATOR_DIGEST_REQUIRED"
    )
    path = "/v1/pr-intents/" + str(UUID(record["pr_intent"]))
    response = client.get(path)
    require(response.status_code == 200, "CURRENT_PR_INTENT_UNAVAILABLE")
    current = response.json()
    require(
        current["preview_sha256"] == approved_digest
        and current["preview"] == expected["preview"],
        "CURRENT_PREVIEW_CHANGED",
    )
    if current["approved_at"] is not None:
        return current  # Existing approval only authorizes reconciliation; never another POST.
    require(
        current["state"] == "PREVIEW" and current["currently_authorized"] is True
        and datetime.fromisoformat(current["expires_at"]) > now,
        "PREVIEW_EXPIRED_OR_REVOKED",
    )
    response = client.post(
        path + "/approve", json={"confirm": True, "preview_sha256": approved_digest}
    )
    require(response.status_code == 200, "APPROVAL_NOT_CONFIRMED_RECONCILE")
    # Read committed state; the POST response is not an external completion receipt.
    return None


async def readback(record, status):
    metadata, pem = protected_local()
    app, base = await preflight(metadata, pem)
    preview = record["pr"]["preview"]
    require(base["base_sha"] == preview["inspection"]["base_sha"], "GITHUB_BASE_CHANGED")
    token = await app.token()
    intent = record["pr_intent"]
    head = await app.read_branch(token, intent)
    require(head == status["result"]["head_sha"], "GITHUB_HEAD_CHANGED")
    await app.verify_commit(
        token, intent, head, base["base_sha"], preview["candidate_source"].encode("utf-8")
    )
    pr = await app.find_pr(token, intent)
    require(pr is not None, "GITHUB_PR_MISSING")
    result = app.verify_pr(pr, intent, head, base["base_sha"], preview["title"], preview["body"])
    require(result == status["result"], "GITHUB_RECEIPT_CHANGED")
    return result


def main(approved_digest):
    record = json.loads(RECORD.read_bytes())
    # Validate approval before loading secrets or opening any service connection.
    require(approved_digest == record["pr"]["preview_sha256"], "EXACT_OPERATOR_DIGEST_REQUIRED")
    saved = existing_session(record["session_file"])
    with LiveSession() as live:
        live.client = httpx.Client(
            base_url=ORIGIN, trust_env=False, timeout=20,
            verify=ssl.create_default_context(cafile=str(PRIVATE / "tls/ca.pem")),
            headers={"Cookie": "__Host-proofflow=" + saved["token"], "Origin": ORIGIN,
                     "X-ProofFlow-CSRF": saved["csrf"]},
        )
        approve_exact(live.client, record, approved_digest, datetime.now(UTC))
        path = "/v1/pr-intents/" + str(UUID(record["pr_intent"]))
        result_path = PRIVATE / "evidence" / ("phase4-pr-result-" + record["pr_intent"] + ".json")
        for _ in range(90):
            response = live.client.get(path)
            require(response.status_code == 200, "APPROVAL_READBACK_UNAVAILABLE")
            status = response.json()
            result_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
            if status["state"] in ("COMPLETE", "STOPPED", "UNCERTAIN"):
                break
            time.sleep(2)
        require(status["state"] == "COMPLETE", "PR_INCOMPLETE_RECONCILE_SAVED_RESULT")
        require(
            len(status["writes"]) == 3
            and {w["stage"] for w in status["writes"]} == {"branch", "commit", "pr"}
            and all(w["confirmed_at"] is not None for w in status["writes"]),
            "PR_WRITE_RECEIPTS_INCOMPLETE",
        )
        external = asyncio.run(readback(record, status))
        # Restart only the trusted dispatcher after completion, then read persisted state again.
        live.host("systemctl restart proofflow-product-dispatcher.service")
        require(
            live.host("systemctl is-active proofflow-product-dispatcher.service") == b"active",
            "DISPATCHER_RESTART_FAILED",
        )
        response = live.client.get(path)
        require(response.status_code == 200, "RESTART_READBACK_UNAVAILABLE")
        after = response.json()
        require(
            after["state"] == "COMPLETE" and after["writes"] == status["writes"]
            and after["result"] == status["result"],
            "RESTART_RECEIPTS_CHANGED",
        )
        replay = live.client.post(
            path + "/approve", json={"confirm": True, "preview_sha256": approved_digest}
        )
        require(
            replay.status_code == 200 and replay.json()["already_applied"] is True,
            "EXACT_APPROVAL_REPLAY_FAILED",
        )
        require(live.client.get(path).json()["writes"] == status["writes"], "REPLAY_CREATED_WRITE")
        require(live.client.post("/v1/logout").status_code == 204, "SESSION_LOGOUT_FAILED")
        receipt = {
            "observed_at": datetime.now(UTC).isoformat(), "intent": record["pr_intent"],
            "preview_sha256": approved_digest, "external_readback": external,
            "writes": status["writes"], "completed_dispatcher_restart": "passed",
            "same_approval_replay": "already_applied_no_new_write", "credit": live.credit,
            "new_worker_executions": 0, "provider_calls": 0, "new_cloud_resources": 0,
            "external_response_loss": "NOT_INJECTED; separate SQL/HTTP-double evidence only",
            "temporary_session_logged_out": True,
        }
        result_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(receipt))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approved-preview-sha256", required=True)
    args = parser.parse_args()
    try:
        main(args.approved_preview_sha256)
    except Exception:
        raise SystemExit("PR_ACCEPTANCE_INCOMPLETE_RECONCILE_PRIVATE_RESULT") from None
