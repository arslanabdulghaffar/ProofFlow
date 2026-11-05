"""Use only after the owner approves the exact current preview; never renew authority."""

import argparse
import asyncio
import hashlib
import json
import re
import ssl
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import httpx
from check_phase4_expired_approval import existing_session
from install_product_services import IMAGE
from prepare_github_app import preflight, protected_local
from product_live_session import ORIGIN, PRIVATE, LiveSession, require
from refresh_phase4_pr_preview import RECORD


def approve_exact(client, record, approved_digest, now, check_only=False):
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
    if check_only:
        return current
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


def main(approved_digest, inject_reply_loss=False, record_path=None, emit=True):
    record_path = RECORD if record_path is None else record_path
    require(record_path.parent == PRIVATE / "evidence", "PRIVATE_RECORD_PATH_REQUIRED")
    record = json.loads(record_path.read_bytes())
    # Validate approval before loading secrets or opening any service connection.
    require(
        type(approved_digest) is str and re.fullmatch(r"[a-f0-9]{64}", approved_digest)
        and approved_digest == record["pr"]["preview_sha256"], "EXACT_OPERATOR_DIGEST_REQUIRED",
    )
    saved = existing_session(record["session_file"])
    with LiveSession() as live:
        live.client = httpx.Client(
            base_url=ORIGIN, trust_env=False, timeout=20,
            verify=ssl.create_default_context(cafile=str(PRIVATE / "tls/ca.pem")),
            headers={"Cookie": "__Host-proofflow=" + saved["token"], "Origin": ORIGIN,
                     "X-ProofFlow-CSRF": saved["csrf"]},
        )
        current = approve_exact(
            live.client, record, approved_digest, datetime.now(UTC), check_only=True
        )
        # Fail expired/unauthorized sessions before stopping services. Recovery never reinjects.
        inject_reply_loss = inject_reply_loss and current["approved_at"] is None
        injected, fault_lease = None, None
        if inject_reply_loss:
            require(
                not live.host("docker ps -aq --filter=name=^/proofflow-pr-reply-loss$"),
                "PR_FAULT_CONTAINER_ALREADY_EXISTS",
            )
            live.host("systemctl stop proofflow-product-dispatcher.service")
        try:
            approve_exact(live.client, record, approved_digest, datetime.now(UTC))
            if inject_reply_loss:
                identity = str(UUID(record["pr_intent"]))
                command = (
                    "timeout --signal=TERM --kill-after=5s 90s docker run --rm -i --pull=never "
                    "--name=proofflow-pr-reply-loss --label=proofflow.role=pr-reply-loss "
                    "--network=host --read-only --cap-drop=ALL "
                    "--security-opt=no-new-privileges --user=10003:10003 --group-add=10001 "
                    "--memory=256m --memory-swap=256m --cpus=1 --pids-limit=32 "
                    "--ulimit=core=0 --ulimit=nofile=128:128 "
                    "--mount=type=bind,src=/run/proofflow-budget,"
                    "dst=/run/proofflow-budget,readonly "
                    "--mount=type=bind,src=/etc/proofflow-product-dispatcher/credentials,"
                    "dst=/etc/proofflow-product/credentials,readonly "
                    "--mount=type=bind,src=/etc/proofflow-github,"
                    "dst=/etc/proofflow-github,readonly "
                    "sha256:" + IMAGE + " python -B - " + identity + " " + approved_digest
                )
                execution = live.admin.host(
                    "control", command, stdin=Path(__file__).with_name(
                        "probe_phase4_pr_reply_loss.py").read_bytes(), timeout=105,
                )
                # Preserve a bounded, secret-free failure receipt before raising.
                # Approval may already be durable; normal service restart below
                # can complete it, so a failure must never suggest a fresh PR.
                if execution.returncode != 0:
                    (PRIVATE / "evidence" / ("phase4-pr-fault-" + identity + ".json")).write_text(
                        json.dumps({"intent": identity, "status": "driver_failed",
                                    "code": "FAULT_DRIVER_FAILED_RECONCILE_OUTBOX",
                                    "returncode": execution.returncode,
                                    "stdout_sha256": hashlib.sha256(execution.stdout).hexdigest(),
                                    "stderr_sha256": hashlib.sha256(execution.stderr).hexdigest(),
                                    "response_loss_proven": False}, indent=2),
                        encoding="utf-8",
                    )
                require(execution.returncode == 0, "FAULT_DRIVER_FAILED_RECONCILE_OUTBOX")
                injected = json.loads(execution.stdout)
                pending = live.client.get("/v1/pr-intents/" + identity).json()
                require(
                    pending["state"] == "PR_PENDING" and len(pending["writes"]) == 3
                    and sum(w["confirmed_at"] is None for w in pending["writes"]) == 1,
                    "LOST_REPLY_NOT_DURABLE_PENDING",
                )
                # Canonical UUID only; this is an administrator read, never a lease/status edit.
                lease_sql = (  # UUID parsed above
                    "SELECT jsonb_build_object('generation',generation,'lease_until',lease_until,"  # noqa: S608
                    "'state',state) FROM pf_product.pr_intents WHERE id='" + identity + "';"
                )
                fault_lease = json.loads(live.sql(lease_sql))
                (PRIVATE / "evidence" / ("phase4-pr-fault-" + identity + ".json")).write_text(
                    json.dumps({"injected": injected, "pending": pending,
                                "lease": fault_lease}, indent=2),
                    encoding="utf-8",
                )
        finally:
            if inject_reply_loss:
                try:
                    owned = live.host(
                        "docker ps -aq --filter=name=^/proofflow-pr-reply-loss$ "
                        "--filter=label=proofflow.role=pr-reply-loss"
                    )
                    if owned:
                        live.host("docker stop -t 5 proofflow-pr-reply-loss")
                finally:
                    live.host("systemctl start proofflow-product-dispatcher.service")
        path = "/v1/pr-intents/" + str(UUID(record["pr_intent"]))
        result_path = PRIVATE / "evidence" / ("phase4-pr-result-" + record["pr_intent"] + ".json")
        last_state = None
        for _ in range(150):
            response = live.client.get(path)
            require(response.status_code == 200, "APPROVAL_READBACK_UNAVAILABLE")
            status = response.json()
            if emit and status["state"] != last_state:
                print("PR state: " + status["state"], flush=True)
                last_state = status["state"]
            result_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
            if status["state"] in ("COMPLETE", "STOPPED", "UNCERTAIN"):
                break
            time.sleep(2)
        require(status["state"] == "COMPLETE", "PR_INCOMPLETE_RECONCILE_SAVED_RESULT")
        recovered_lease = json.loads(live.sql(lease_sql)) if fault_lease else None
        if fault_lease:
            require(
                recovered_lease["generation"] > fault_lease["generation"]
                and recovered_lease["state"] == "COMPLETE"
                and recovered_lease["lease_until"] is None,
                "FRESH_CONTROLLER_RECOVERY_NOT_PROVEN",
            )
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
            "external_response_loss": injected or "NOT_INJECTED; separate SQL/HTTP doubles only",
            "fault_lease": fault_lease, "recovered_lease": recovered_lease,
            "temporary_session_logged_out": True,
        }
        result_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        if emit:
            print(json.dumps(receipt))
        return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approved-preview-sha256", required=True)
    parser.add_argument("--inject-pr-reply-loss", action="store_true")
    args = parser.parse_args()
    try:
        main(args.approved_preview_sha256, args.inject_pr_reply_loss)
    except Exception:
        raise SystemExit("PR_ACCEPTANCE_INCOMPLETE_RECONCILE_PRIVATE_RESULT") from None
