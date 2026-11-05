"""Prepare one fresh exact preview of an existing eligible version; never approve it."""

import hashlib
import json
import time
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID, uuid4

from check_phase4_expired_approval import existing_session
from prepare_phase4_pr_preview import save_session
from product_live_session import PRIVATE, LiveSession, require

RECORD = PRIVATE / "evidence/phase4-pr-refresh-20261105-0740.json"
SOURCE = PRIVATE / "evidence/phase4-pr-workspace-20261105.json"
STAGES = {"connect", "preflight", "session", "save_session", "read_session",
          "request_preview", "read_preview", "render_preview"}
SAFE_ERRORS = {
    "MANAGEMENT_PREFLIGHT_FAILED", "ADMINISTRATOR_OPERATION_IN_PROGRESS",
    "PRIVATE_HOST_OPERATION_FAILED", "PRIVATE_TUNNEL_UNAVAILABLE",
    "CREDIT_GUARD_NOT_ADMITTING", "ADMISSION_MUST_START_CLOSED", "REPAIR_NOT_IDLE",
    "WORKSPACE_EXPIRED_OR_UNAVAILABLE", "PRIVATE_SESSION_SAVE_FAILED",
    "PRIVATE_SESSION_UNAVAILABLE", "PRIVATE_SESSION_READBACK_FAILED",
    "FRESH_PREVIEW_NOT_ACCEPTED", "FRESH_PREVIEW_UNAVAILABLE", "FRESH_PREVIEW_NOT_READY",
    "INFERENCE_MUST_REMAIN_BLOCKED", "REVIEW_EXISTING_EXTERNAL_WRITES",
}


def require_workspace(live, workspace):
    # Check before creating credentials or an intent; expiry is never extended.
    require(live.sql(
        "SELECT COALESCE(bool_and(kind='operator' AND revoked_at IS NULL AND "  # noqa: S608 - UUID only
        "expires_at>clock_timestamp()+interval '41 minutes'),false) "
        f"FROM pf_product.workspaces WHERE id='{UUID(workspace)}';"
    ) == b"t", "WORKSPACE_EXPIRED_OR_UNAVAILABLE")


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


def _prepare(record_path, emit):
    source = SOURCE if SOURCE.exists() else PRIVATE / "evidence/phase4-pr-preview-intent.json"
    prior = json.loads(source.read_bytes())
    expected_source = (prior["candidate_sha256"] if source == SOURCE else hashlib.sha256(
        prior["pr"]["preview"]["candidate_source"].encode()).hexdigest())
    if source == SOURCE:
        require(prior.get("status") == "ready", "FRESH_WORKSPACE_NOT_READY")
    identity = uuid4()
    record = {
        "workspace": str(UUID(prior["workspace"])),
        "version": str(UUID(prior["version"])),
        "source_record": source.name,
        "pr_intent": str(identity),
        "session_file": "phase4-pr-" + identity.hex + ".dpapi",
        "external_approval": False,
        "preparation_stage": "connect",
    }
    with record_path.open("x", encoding="utf-8") as output:
        json.dump(record, output)

    def save():
        record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

    def stage(value):
        record["preparation_stage"] = value
        save()

    with LiveSession() as live:
        stage("preflight")
        require(
            live.sql("SELECT bool_and(blocked) FROM pf_budget.accounts;", "proofflow_budget")
            == b"t",
            "INFERENCE_MUST_REMAIN_BLOCKED",
        )
        require(
            live.sql("SELECT count(*) FROM pf_product.pr_writes;") == b"0",
            "REVIEW_EXISTING_EXTERNAL_WRITES",
        )
        require_workspace(live, record["workspace"])
        stage("session")
        client = live.login(record["workspace"])
        stage("save_session")
        save_session(live.secret, record["session_file"])
        stage("read_session")
        saved = existing_session(record["session_file"])
        require(
            saved == {"token": live.secret.token, "csrf": live.secret.csrf},
            "PRIVATE_SESSION_READBACK_FAILED",
        )
        stage("request_preview")
        response = client.post(
            "/v1/versions/" + record["version"] + "/pr-preview",
            json={"intent_id": record["pr_intent"]},
        )
        require(response.status_code == 202, "FRESH_PREVIEW_NOT_ACCEPTED")
        stage("read_preview")
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
            hashlib.sha256(status["preview"]["candidate_source"].encode()).hexdigest()
            == expected_source,
            "EXISTING_CANDIDATE_CHANGED",
        )
        record["observed_at"] = datetime.now(UTC).isoformat()
        record["credit"] = live.credit
        stage("render_preview")
        record["review_artifact"] = render_preview(record)
        record["preparation_stage"] = "ready"
        save()
        summary = {
            "intent": record["pr_intent"], "preview_sha256": status["preview_sha256"],
            "expires_at": status["expires_at"], "review_artifact": record["review_artifact"],
            "base_sha": status["preview"]["inspection"]["base_sha"],
            "branch": status["preview"]["branch"], "credit": live.credit,
            "new_worker_jobs": 0, "new_model_calls": 0, "external_writes": 0,
        }
        if emit:
            print(json.dumps(summary))
        return record


def main(record_path=None, emit=True):
    record_path = RECORD if record_path is None else record_path
    require(record_path.parent == PRIVATE / "evidence", "PRIVATE_RECORD_PATH_REQUIRED")
    require(not record_path.exists(), "RECONCILE_EXISTING_REFRESH_RECORD")
    try:
        return _prepare(record_path, emit)
    except Exception as error:
        # Native errors may contain secrets. Persist only fixed stage/error codes.
        stage, code = "connect", "UNCLASSIFIED_PREPARATION_FAILURE"
        if str(error) in SAFE_ERRORS:
            code = str(error)
        if record_path.exists():
            record = json.loads(record_path.read_bytes())
            stage = record.get("preparation_stage", "connect")
            stage = stage if stage in STAGES else "connect"
            record["preparation_failure"] = code
            record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        raise RuntimeError(f"PREVIEW_STOPPED_{stage.upper()}_{code}") from None


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("FRESH_PREVIEW_FAILED_RECONCILE_PRIVATE_RECORD") from None
