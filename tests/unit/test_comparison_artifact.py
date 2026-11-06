"""Invented failed records only; no live measurement or candidate execution."""

import pytest

from eval.comparison_artifact import check
from eval.comparison_cases import cases
from eval.report import digest, manifest, summarize


def fixture():
    synthetic = cases("f" * 64)
    plan = manifest(
        cases=[{k: c[k] for k in ("id", "family", "kind", "sha256")} for c in synthetic],
        freeze=dict.fromkeys(("source", "prompts", "runtime", "schemas", "grader", "model_quote"),
                             "a" * 64),
        stage="final",
    )
    records = [{
        **job, "run_id": "fixture-" + str(index), "plan_sha256": digest(plan),
        "decision": "failed", "grade": "unknown", "cleanup": "no_execution",
        "latency_ms": 0, "calls": 0, "input_tokens": 0, "output_tokens": 0,
        "reserved_micro_usd": 0, "estimated_micro_usd": 0, "receipt_sha256": "b" * 64,
    } for index, job in enumerate(plan["jobs"])]
    return {
        "version": "proofflow-synthetic-comparison-v1", "plan": plan,
        "cases": [{"id": c["id"], "files": {k: v.decode() for k, v in c["files"].items()},
                   "oracle_summary": c["oracle_summary"]} for c in synthetic],
        "records": records, "report": summarize(plan, records),
        "provenance": {"fixture": True},
    }


def test_recompute_all_denominators_and_frozen_synthetic_inputs():
    artifact = fixture()
    result = check(artifact)
    assert sum(arm["observed"] for arm in result["arms"].values()) == 96
    assert all(arm["decisions"] == {"failed": 24} for arm in result["arms"].values())
    assert result["evidence_validation"] == "RECEIPT_RECONCILIATION_REQUIRED"


@pytest.mark.parametrize("fault", ["source", "oracle", "score", "case", "record", "extra"])
def test_portable_record_tampering_rejected(fault):
    artifact = fixture()
    if fault == "source":
        artifact["cases"][0]["files"]["pipeline.py.txt"] = "inert changed source"
    elif fault == "oracle":
        artifact["cases"][0]["oracle_summary"]["net_minor_units"] += 1
    elif fault == "score":
        artifact["report"]["arms"]["A"]["outcomes"]["repairable"]["successful"] = 18
    elif fault == "case":
        artifact["cases"].pop()
    elif fault == "record":
        artifact["records"].pop()
        artifact["report"] = summarize(artifact["plan"], artifact["records"])
    else:
        artifact["unrelated"] = "not allowed"
    with pytest.raises(ValueError):
        check(artifact)
