"""Full-product A evaluation adapter. No activation, external PR or candidate execution.

The finite campaign driver owns credit/quote checks, admission and cutoff timers.
This adapter persists exact IDs before writes and refuses all uncertain reruns.
"""

import hashlib
import json
import os
import time
from datetime import UTC, datetime
from uuid import UUID, uuid4

from orchestrator.probe_response import parse_probe_response
from orchestrator.repair_evidence import bind_sources, classify
from orchestrator.repair_proposal import COMPLETION_TOKENS, PROMPT_TOKEN_RESERVE


def require(value, code):
    if not value:
        raise RuntimeError(code)


def save(folder, name, value):
    """Immutable bounded campaign record; directory is under the private evidence root."""
    raw = json.dumps(value, sort_keys=True).encode()
    require(len(raw) <= 8 * 1024 * 1024, "COMPARISON_RECORD_LIMIT")
    with (folder / name).open("xb") as output:
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())


def wait(client, path, seconds):
    deadline = time.monotonic() + seconds
    while True:
        response = client.get(path)
        require(response.status_code == 200, "COMPARISON_STATUS_UNAVAILABLE")
        value = response.json()
        if value["state"] in ("NEEDS_REVIEW", "AWAITING_APPROVAL", "FAILED_INFRA", "CANCELLED"):
            return value
        require(
            value["state"]
            in ("QUEUED", "RUNNING", "BASELINE_RUNNING", "BASELINE_VERIFYING", "RECONCILING"),
            "COMPARISON_STATE_UNRECOGNIZED",
        )
        require(time.monotonic() < deadline, "COMPARISON_STATUS_UNCERTAIN")
        time.sleep(1)


def calls_from_rows(rows):
    """Count prepared requests conservatively; retain unknown delivery/usage as unknown."""
    require(len(rows) <= 3, "COMPARISON_CALL_LIMIT")
    output = []
    for row in rows:
        call = {
            "request": str(UUID(row["request_id"])),
            "reserved_micro_usd": row["reserved_micro"],
            "estimated_micro_usd": None,
            "input_tokens": None,
            "output_tokens": None,
            "outcome": row["outcome"],
            "delivery_confirmed": False,
        }
        require(
            type(row["reserved_micro"]) is int and row["reserved_micro"] > 0,
            "COMPARISON_RESERVATION_INVALID",
        )
        output.append(call)
        if row["outcome"] != "PARSED_RESPONSE":
            continue
        quote = json.loads(bytes.fromhex(row["quote"][2:]))
        require(
            quote["model"] == "qwen3.8-flash-next"
            and quote["input_rate"] == 100000
            and quote["output_rate"] == 200000,
            "COMPARISON_RATE_CHANGED",
        )
        response = parse_probe_response(
            bytes.fromhex(row["response"][2:]),
            model=quote["model"],
            completion_bound=COMPLETION_TOKENS,
        )
        call.update(response_sha256=response.response_sha256, delivery_confirmed=True)
        if response.usage is None or response.usage.prompt_tokens > PROMPT_TOKEN_RESERVE:
            continue
        usage = response.usage
        call.update(
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
            estimated_micro_usd=(
                usage.prompt_tokens * 100000 + usage.completion_tokens * 200000 + 999999
            )
            // 1000000,
        )
    require(sum(c["reserved_micro_usd"] for c in output) <= 100000, "COMPARISON_JOB_CAP_EXCEEDED")
    return output


def grade_export(export, executions, files, policy):
    """Check the actual last candidate and two fresh protected receipts, not API PASS text."""
    source = export["candidate_source"].encode()
    require(
        export["activation_approved"] is False
        and hashlib.sha256(source).hexdigest() == export["candidate_sha256"],
        "COMPARISON_EXPORT_BINDING",
    )
    require(
        3 <= len(executions) <= 9
        and len({e["execution_id"] for e in executions}) == len(executions),
        "COMPARISON_FRESH_EXECUTIONS_REQUIRED",
    )
    require(
        all(e["result"] and e["result"]["worker"]["cleanup"] == "confirmed" for e in executions),
        "COMPARISON_CLEANUP_UNCERTAIN",
    )
    final = executions[-3:]
    require(
        [e["purpose"] for e in final] == ["candidate", "canary_ownership", "canary_quarantine"]
        and len({e["attempt"] for e in final}) == 1,
        "COMPARISON_PROOFS_INCOMPLETE",
    )
    for row in final:
        intent = row["intent"]
        require(
            intent["execution"] == UUID(row["execution_id"]).hex
            and intent["pipeline_sha256"] == export["candidate_sha256"]
            and intent["purpose"] == row["purpose"]
            and intent["contract_raw_sha256"] == hashlib.sha256(files["contract.json"]).hexdigest()
            and intent["runtime_sha256"] == policy["runtime_sha256"]
            and intent["verifier_rootfs"] == policy["verifier_sha256"],
            "COMPARISON_PROOF_BINDING",
        )
        if row["purpose"] == "candidate":
            bind_sources(
                intent,
                source=source,
                contract=files["contract.json"],
                transactions=files["transactions.csv"],
                customers=files["customers.csv"],
                runtime=policy["runtime_sha256"],
                verifier=policy["verifier_sha256"],
                purpose="candidate",
            )
        verdict, _ = classify(
            row["result"], intent, policy["runtime_sha256"], policy["verifier_sha256"]
        )
        require(
            verdict in (("match", "held") if row["purpose"] == "canary_quarantine" else ("match",)),
            "COMPARISON_PROOF_DID_NOT_PASS",
        )
    return export["candidate_sha256"]


def run(live, job, case, root):
    """One synthetic full API job. Caller must close admission even on an exception."""
    require(job["arm"] == "A", "COMPARISON_ARM_INVALID")
    identifier = str(UUID(job["run_id"]))
    folder = root / identifier
    folder.mkdir(mode=0o700)
    started = time.monotonic()
    files = case["files"]
    require(
        {n: hashlib.sha256(raw).hexdigest() for n, raw in files.items()} == case["file_hashes"],
        "COMPARISON_SOURCE_CHANGED",
    )
    workspace = str(uuid4())
    ids = {kind: str(uuid4()) for kind in ("contract", "pipeline", "transactions", "customers")}
    keys = {kind: str(uuid4()) for kind in ("original", "repair")}
    intent = {
        **job,
        "workspace": workspace,
        "assets": ids,
        "idempotency": keys,
        "file_hashes": case["file_hashes"],
        "started_at": datetime.now(UTC).isoformat(),
    }
    save(folder, "intent.json", intent)  # All authority-bearing IDs precede network writes.
    result = {
        **job,
        "workspace": workspace,
        "decision": "failed",
        "grade": "unknown",
        "cleanup": "no_execution",
        "calls": [],
        "executions": [],
    }
    try:
        result["stage"] = "provision_fixture"
        live.sql(
            "SET ROLE pf_product_provisioner; SELECT pf_product.create_workspace('"
            + workspace
            + "','operator',clock_timestamp()+interval '2 hours');"
        )
        client = live.login(workspace)
        result["stage"] = "intake"
        for kind, name in (
            ("contract", "contract.json"),
            ("pipeline", "pipeline.py.txt"),
            ("transactions", "transactions.csv"),
            ("customers", "customers.csv"),
        ):
            response = client.post("/v1/assets/" + kind + "/" + ids[kind], content=files[name])
            require(response.status_code == 201, "COMPARISON_UPLOAD_FAILED")
            require(
                response.json()["sha256"] == case["file_hashes"][name], "COMPARISON_UPLOAD_CHANGED"
            )
            save(folder, "upload-" + kind + ".json", response.json())
        response = client.post(
            "/v1/contracts/" + ids["contract"] + "/approve",
            json={"expected_sha256": case["file_hashes"]["contract.json"], "confirm": True},
        )
        save(
            folder,
            "contract-approval.json",
            {"status": response.status_code, "body": response.json()},
        )
        if (
            response.status_code == 422
            and response.json().get("error", {}).get("code") == "UNKNOWN_UNIT"
        ):
            result.update(
                decision="clarification", grade="correct", intake_rejection="UNKNOWN_UNIT"
            )
            return result
        require(response.status_code == 200, "COMPARISON_CONTRACT_APPROVAL_FAILED")
        result["stage"] = "original"
        response = client.post(
            "/v1/jobs",
            json={**{k + "_id": v for k, v in ids.items()}, "idempotency_key": keys["original"]},
        )
        require(response.status_code == 202, "COMPARISON_ORIGINAL_ENQUEUE_UNCERTAIN")
        parent = str(UUID(response.json()["job_id"]))
        save(folder, "original-enqueued.json", response.json())
        original = wait(client, "/v1/jobs/" + parent, 120)
        save(folder, "original.json", original)
        result["original_decision"] = original["outcome"]
        require(original["state"] == "NEEDS_REVIEW", "COMPARISON_ORIGINAL_INFRASTRUCTURE")
        receipt = original["report"]
        require(receipt["worker"]["cleanup"] == "confirmed", "COMPARISON_ORIGINAL_CLEANUP")
        result["cleanup"] = "confirmed"
        diagnosis = (receipt.get("source") or receipt.get("semantic"))["report"]["result"]
        if diagnosis["blocking_occurrences"] > 0:
            result.update(decision="held", grade="correct")
            return result
        # Original matches must not silently become model-repair successes.
        if original["outcome"] == "match":
            result.update(ineffective_fault=True, decision="failed", grade="unknown")
            return result
        require(
            original["outcome"] in ("execution_failed", "mismatch"),
            "COMPARISON_ORIGINAL_UNSUPPORTED",
        )
        result["stage"] = "repair"
        response = client.post(
            "/v1/repairs", json={"parent_id": parent, "idempotency_key": keys["repair"]}
        )
        require(response.status_code == 202, "COMPARISON_REPAIR_ENQUEUE_UNCERTAIN")
        repair = str(UUID(response.json()["repair_id"]))
        save(folder, "repair-enqueued.json", response.json())
        value = wait(client, "/v1/repairs/" + repair, 360)
        save(folder, "repair.json", value)
        result["repair"] = value
        executions = json.loads(
            live.sql(
                "SELECT coalesce(json_agg(e ORDER BY generation),'[]'::json) "
                "FROM pf_product.repair_executions e WHERE repair_id='" + repair + "';"
            )
        )
        rows = json.loads(
            live.sql(
                "SELECT coalesce(json_agg(c ORDER BY ordinal),'[]'::json) "
                "FROM pf_product.repair_calls c WHERE repair_id='" + repair + "';"
            )
        )
        save(folder, "repair-executions.json", executions)
        save(folder, "repair-calls.json", rows)
        result["calls"] = calls_from_rows(rows)
        require(
            value["calls"] == len(rows)
            and value["reserved_micro"] == sum(c["reserved_micro_usd"] for c in result["calls"]),
            "COMPARISON_CALL_ACCOUNTING_MISMATCH",
        )
        result["executions"] = [
            {
                "execution": e["execution_id"],
                "purpose": e["purpose"],
                "cleanup": (e.get("result") or {}).get("worker", {}).get("cleanup", "unknown"),
            }
            for e in executions
        ]
        require(
            all(e["cleanup"] == "confirmed" for e in result["executions"]),
            "COMPARISON_REPAIR_CLEANUP",
        )
        require(value["state"] != "FAILED_INFRA", "COMPARISON_REPAIR_INFRASTRUCTURE")
        if value["state"] == "AWAITING_APPROVAL":
            response = client.get("/v1/repairs/" + repair + "/export")
            require(response.status_code == 200, "COMPARISON_EXPORT_FAILED")
            export = response.json()
            save(folder, "export.json", export)
            candidate = grade_export(export, executions, files, live.policy)
            result.update(decision="accepted", grade="correct", candidate_sha256=candidate)
        elif value["state"] == "CANCELLED":
            result["decision"] = "cancelled"
        elif value["outcome"] == "needs_clarification":
            result["decision"] = "clarification"  # Model-authored questions need human review.
        elif value["outcome"] == "deadline_exceeded":
            result["decision"] = "timeout"
        return result
    except Exception as error:
        result.update(error_type=type(error).__name__, critical=True, grade="unknown")
        if result.get("stage") in ("original", "repair"):
            result["cleanup"] = "unknown"
        return result
    finally:
        result["elapsed_ms"] = round((time.monotonic() - started) * 1000)
        save(folder, "result.json", result)


def retire(live, result, root):
    """Only this completed synthetic workspace, after all evidence was saved."""
    require(not result.get("critical"), "COMPARISON_RECONCILE_BEFORE_RETIREMENT")
    folder = root / str(UUID(result["run_id"]))
    workspace = str(UUID(result["workspace"]))
    require(
        json.loads((folder / "result.json").read_bytes()) == result, "COMPARISON_RESULT_NOT_DURABLE"
    )
    save(folder, "retirement-intent.json", {"workspace": workspace})
    client = live.login(workspace)
    response = client.post(
        "/v1/workspace/delete", json={"workspace_id": workspace, "confirm": True}
    )
    require(
        response.status_code == 200 and response.json()["access_revoked"] is True,
        "COMPARISON_RETIREMENT_UNCERTAIN",
    )
    save(folder, "retirement-requested.json", response.json())
    live.host("systemctl start proofflow-product-retention.service")
    completed = live.sql(
        "SELECT count(*) FROM pf_product.deletions WHERE workspace_id='"  # noqa: S608 - canonical UUID
        + workspace
        + "' AND completed_at IS NOT NULL;"
    )
    require(completed == b"1", "COMPARISON_RETIREMENT_INCOMPLETE")
    asset_root = "/var/lib/proofflow-product/assets/"
    hex_id = UUID(workspace).hex
    require(
        live.host(
            "test ! -e "
            + asset_root
            + hex_id
            + " && test -f "
            + asset_root
            + ".deleted-"
            + hex_id
            + " && echo retired"
        )
        == b"retired",
        "COMPARISON_BYTES_NOT_RETIRED",
    )
    save(folder, "retirement-completed.json", {"workspace": workspace, "sql_completed": True})
