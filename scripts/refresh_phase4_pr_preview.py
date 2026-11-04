"""Prepare one fresh exact preview of an existing eligible version; never approve it."""

import json
import time
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID, uuid4

from check_phase4_expired_approval import existing_session
from prepare_phase4_pr_preview import save_session
from product_live_session import PRIVATE, LiveSession, require

RECORD = PRIVATE / "evidence/phase4-pr-refresh-20261105.json"


def render_preview(record):
    status = record["pr"]
    value = status["preview"]
    config = value["configuration"]
    expires = datetime.fromisoformat(status["expires_at"]).astimezone(
        timezone(timedelta(hours=9))
    )
    text = (
        "# Exact private draft PR preview\n\n"
        "Creates one branch, commits pipeline.py there, and opens one private draft PR. "
        "No merge, CI execution, deployment or publication.\n\n"
        f"Repository: {config['owner']}/{config['repository']} (private)\n\n"
        f"Base: {config['base']} at {value['inspection']['base_sha']}\n\n"
        f"Branch: {value['branch']}\n\n"
        f"Path: {config['path']}\n\n"
        f"Version: {status['version_id']}\n\n"
        f"Candidate SHA256: {value['version']['candidate_sha256']}\n\n"
        f"Intent: {record['pr_intent']}\n\n"
        f"Preview SHA256: {status['preview_sha256']}\n\n"
        f"Expires: {expires.isoformat()} (KST)\n\n"
        "Reuses the previously verified synthetic version and its three isolated checks. "
        "This is automated evidence, not independent human sign-off.\n\n"
        f"## Exact title\n\n{value['title']}\n\n"
        f"## Exact body\n\n{value['body']}\n\n"
        f"## Exact diff\n\n`````diff\n{value['inspection']['diff']}\n`````\n"
    )
    destination = PRIVATE / "evidence" / ("phase4-pr-preview-" + record["pr_intent"] + ".md")
    with destination.open("x", encoding="utf-8", newline="\n") as output:
        output.write(text)
    return str(destination)


def main():
    require(not RECORD.exists(), "RECONCILE_EXISTING_REFRESH_RECORD")
    prior = json.loads((PRIVATE / "evidence/phase4-pr-preview-intent.json").read_bytes())
    identity = uuid4()
    record = {
        "workspace": str(UUID(prior["workspace"])),
        "version": str(UUID(prior["version"])),
        "previous_intent": str(UUID(prior["pr_intent"])),
        "pr_intent": str(identity),
        "session_file": "phase4-pr-" + identity.hex + ".dpapi",
        "external_approval": False,
    }
    with RECORD.open("x", encoding="utf-8") as output:
        json.dump(record, output)

    def save():
        RECORD.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

    with LiveSession() as live:
        require(
            live.sql("SELECT bool_and(blocked) FROM pf_budget.accounts;", "proofflow_budget")
            == b"t",
            "INFERENCE_MUST_REMAIN_BLOCKED",
        )
        require(
            live.sql("SELECT count(*) FROM pf_product.pr_writes;") == b"0",
            "REVIEW_EXISTING_EXTERNAL_WRITES",
        )
        client = live.login(record["workspace"])
        save_session(live.secret, record["session_file"])
        saved = existing_session(record["session_file"])
        require(
            saved == {"token": live.secret.token, "csrf": live.secret.csrf},
            "PRIVATE_SESSION_READBACK_FAILED",
        )
        response = client.post(
            "/v1/versions/" + record["version"] + "/pr-preview",
            json={"intent_id": record["pr_intent"]},
        )
        require(response.status_code == 202, "FRESH_PREVIEW_NOT_ACCEPTED")
        for _ in range(60):
            response = client.get("/v1/pr-intents/" + record["pr_intent"])
            require(response.status_code == 200, "FRESH_PREVIEW_UNAVAILABLE")
            record["pr"] = response.json()
            save()
            if record["pr"]["state"] != "PREPARING":
                break
            time.sleep(1)
        status = record["pr"]
        require(
            status["state"] == "PREVIEW" and status["currently_authorized"] is True
            and status["approved_at"] is None and status["writes"] == [],
            "FRESH_PREVIEW_NOT_READY",
        )
        require(
            status["preview"]["candidate_source"] == prior["pr"]["preview"]["candidate_source"],
            "EXISTING_CANDIDATE_CHANGED",
        )
        record["observed_at"] = datetime.now(UTC).isoformat()
        record["credit"] = live.credit
        record["review_artifact"] = render_preview(record)
        save()
        print(json.dumps({
            "intent": record["pr_intent"], "preview_sha256": status["preview_sha256"],
            "expires_at": status["expires_at"], "review_artifact": record["review_artifact"],
            "base_sha": status["preview"]["inspection"]["base_sha"],
            "branch": status["preview"]["branch"], "credit": live.credit,
            "new_worker_jobs": 0, "new_model_calls": 0, "external_writes": 0,
        }))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("FRESH_PREVIEW_FAILED_RECONCILE_PRIVATE_RECORD") from None
