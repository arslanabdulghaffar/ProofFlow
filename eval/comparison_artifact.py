"""Portable synthetic evidence accounting, without credentials or candidate execution."""

import hashlib

from eval.comparison_cases import check_oracle
from eval.report import digest, summarize

FILES = {"pipeline.py.txt", "contract.json", "transactions.csv", "customers.csv"}


def check(artifact):
    """Recompute dataset hashes/oracles and metrics; hashes are not live-call proof."""
    if set(artifact) != {"version", "plan", "cases", "records", "report", "provenance"}:
        raise ValueError("COMPARISON_ARTIFACT_FIELDS")
    if artifact["version"] != "proofflow-synthetic-comparison-v1":
        raise ValueError("COMPARISON_ARTIFACT_VERSION")
    plan = artifact["plan"]
    if len(artifact["cases"]) != len(plan["cases"]):
        raise ValueError("COMPARISON_ARTIFACT_CASE_COUNT")
    for case, expected in zip(artifact["cases"], plan["cases"], strict=True):
        if set(case) != {"id", "files", "oracle_summary"} or case["id"] != expected["id"]:
            raise ValueError("COMPARISON_ARTIFACT_CASE")
        if set(case["files"]) != FILES:
            raise ValueError("COMPARISON_ARTIFACT_FILES")
        files = {name: raw.encode("utf-8") for name, raw in case["files"].items()}
        if any(len(raw) > 32768 for raw in files.values()):
            raise ValueError("COMPARISON_ARTIFACT_SIZE")
        hashes = {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}
        if digest({"files": hashes, "oracle": case["oracle_summary"]}) != expected["sha256"]:
            raise ValueError("COMPARISON_ARTIFACT_CASE_HASH")
        check_oracle({**case, "files": files})  # Source tables only; pipeline remains inert bytes.
    computed = summarize(plan, artifact["records"])
    # These two fields require the separately recorded private live receipt audit.
    for key, value in computed.items():
        if key not in {"evidence_validation", "held_out_claim"}:
            if artifact["report"].get(key) != value:
                raise ValueError("COMPARISON_ARTIFACT_METRICS")
    if any(arm["not_run"] for arm in computed["arms"].values()):
        raise ValueError("COMPARISON_ARTIFACT_INCOMPLETE")
    return computed
