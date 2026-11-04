"""Bind independently checked output bytes to this exact candidate and execution."""

import hashlib

from orchestrator.repair_proposal import RepairRejected
from worker.protocol import runtime_identity_digest


def classify(result: dict, intent: dict, runtime: str, verifier: str) -> tuple[str, dict]:
    if result.get("intent") != intent:
        raise RepairRejected("REPAIR_EXECUTION_BINDING")
    worker = result.get("worker", {})
    if (
        worker.get("cleanup") != "confirmed"
        or worker.get("execution") != intent["execution"]
        or worker.get("job") != intent["job"]
        or worker.get("generation") != intent["generation"]
        or worker.get("manifest") != intent["manifest_sha256"]
        or runtime_identity_digest(worker.get("runtime", {})) != runtime
    ):
        raise RepairRejected("REPAIR_CLEANUP_UNCERTAIN")
    if (
        worker.get("collected") is not True
        or type(worker.get("runtime_client_exit_code")) is not int
        or worker["runtime_client_exit_code"] != 0
        or worker.get("unit_result") != "success"
    ):
        return "execution_failed", {"code": "CANDIDATE_EXECUTION_FAILED"}
    semantic = result.get("semantic") or {}
    report = semantic.get("report", {})
    if (
        semantic.get("cleanup_confirmed") is not True
        or semantic.get("rootfs_sha256") != verifier
        or report.get("version") != "proofflow-verifier-v1"
    ):
        raise RepairRejected("REPAIR_VERIFIER_UNCERTAIN")
    if report.get("status") != "processed":
        return "rejected", {"code": "CANDIDATE_OUTPUT_REJECTED"}
    checked = report.get("result", {})
    if checked.get("operation") != "verify" or any(
        checked.get(key) != intent[key]
        for key in ("transactions_sha256", "customers_sha256", "contract_sha256")
    ):
        raise RepairRejected("REPAIR_VERIFIER_BINDING")
    files = worker.get("files", [])
    hashes = {item["name"]: item["sha256"] for item in files}
    if (
        len(hashes) != len(files)
        or not {"ledger.jsonl", "unresolved.jsonl"} <= hashes.keys()
        or not hashes.keys() <= {"ledger.jsonl", "unresolved.jsonl", "rollups.jsonl"}
        or hashes != checked.get("output_hashes")
    ):
        raise RepairRejected("REPAIR_OUTPUT_BINDING")
    count, blocking = checked.get("finding_count"), checked.get("blocking_occurrences")
    if (
        type(count) is not int
        or count < 0
        or type(blocking) is not int
        or blocking < 0
        or type(checked.get("findings")) is not list
    ):
        raise RepairRejected("REPAIR_VERIFIER_BINDING")
    if checked.get("comparison") == "match" and count == 0 and not checked["findings"]:
        return ("held" if blocking else "match"), {}
    if checked.get("comparison") != "mismatch" or count == 0 or not checked["findings"]:
        raise RepairRejected("REPAIR_VERIFIER_BINDING")
    # Protected canary feedback never reveals a row, hidden owner, seed or expected output.
    if intent["purpose"] != "candidate":
        return "mismatch", {"code": "PROTECTED_CHECK_FAILED"}
    return "mismatch", {
        "code": "CONTRACT_MISMATCH",
        "findings": checked["findings"][:5],
        "ownership_witnesses": checked.get("ownership_witnesses", [])[:1],
    }


def bind_sources(intent, *, source, contract, transactions, customers, runtime, verifier, purpose):
    values = {
        "pipeline_sha256": source,
        "contract_raw_sha256": contract,
        "transactions_sha256": transactions,
        "customers_sha256": customers,
    }
    if (
        any(intent.get(key) != hashlib.sha256(raw).hexdigest() for key, raw in values.items())
        or intent.get("runtime_sha256") != runtime
        or intent.get("verifier_rootfs") != verifier
        or intent.get("purpose") != purpose
    ):
        raise RepairRejected("REPAIR_SOURCE_BINDING")
