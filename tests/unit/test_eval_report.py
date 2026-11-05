"""Invented accounting records only; never measured repair results."""

import copy

import pytest

from eval.report import FAMILIES, digest, manifest, summarize


def plan():
    cases = [{"id": f"{family}-{kind}", "family": family, "kind": kind,
              "sha256": digest([family, kind])}
             for family in FAMILIES for kind in ("repairable", "ambiguous")]
    return manifest(cases=cases, freeze=dict.fromkeys(
        ("source", "prompts", "runtime", "schemas", "grader", "model_quote"), "1" * 64),
        stage="final")


def record(p, arm="A", kind="repairable", **changes):
    return {"plan_sha256": digest(p), "run_id": "fixture-1", "case": "schema-" + kind,
            "arm": arm, "repeat": 1, "decision": "accepted", "grade": "correct",
            "cleanup": "confirmed", "latency_ms": 500, "calls": 1,
            "input_tokens": 100, "output_tokens": 100, "reserved_micro_usd": 27853,
            "estimated_micro_usd": 30, "receipt_sha256": "2" * 64, **changes}


def test_missing_is_not_run_and_zero_acceptance_rate_is_undefined():
    report = summarize(plan(), [])
    for arm in report["arms"].values():
        assert arm["planned"] == arm["not_run"] == 12
        assert arm["observed"] == 0 and arm["incorrect_acceptance_rate"] is None
        assert arm["latency"] == {"n": 0, "median_ms": None, "p95_ms": None}


def test_failures_unknown_cost_and_unknown_grade_are_not_hidden():
    p = plan()
    rows = [record(p, grade="unknown", cleanup="unknown", input_tokens=None,
                   output_tokens=None, estimated_micro_usd=None),
            record(p, kind="ambiguous", run_id="fixture-2", decision="timeout",
                   grade="unknown", latency_ms=300000)]
    arm = summarize(p, rows)["arms"]["A"]
    assert arm["planned"] == 12 and arm["observed"] == 2 and arm["not_run"] == 10
    assert arm["incorrect_acceptance_rate"] is None and arm["ungraded_accepted"] == 1
    assert arm["usage_unknown_runs"] == 1 and arm["reserved_micro_usd"] == 55706
    assert arm["outcomes"]["repairable"]["successful"] == 0
    assert arm["outcomes"]["ambiguous"]["successful"] == 0
    assert arm["latency"]["p95_ms"] == 300000 and arm["latency"]["n"] == 2


@pytest.mark.parametrize("changes", [
    {"plan_sha256": "0" * 64}, {"calls": True}, {"repeat": True},
    {"reserved_micro_usd": 100001}, {"estimated_micro_usd": -1},
    {"case": "not-planned"}, {"cleanup": "invented"}, {"latency_ms": -1},
    {"input_tokens": None}, {"receipt_sha256": "invalid"},
    {"arm": "D"}, {"calls": 0},
])
def test_malformed_or_unbound_records_fail_closed(changes):
    p = plan()
    with pytest.raises(ValueError):
        summarize(p, [record(p, **changes)])


def test_duplicate_result_cannot_select_best_or_replace_failure():
    p = plan()
    with pytest.raises(ValueError):
        summarize(p, [record(p), record(p, run_id="fixture-2", grade="incorrect")])


def test_declared_plan_cannot_be_reduced_after_results():
    p = plan()
    changed = copy.deepcopy(p)
    changed["jobs"].pop()
    with pytest.raises(ValueError):
        summarize(changed, [record(p)])


def test_pilot_cap_and_balanced_final_set():
    p = plan()
    assert p["forecast_micro_usd"] == 3600000 and not p["dispatch_authorized"]
    assert len(p["jobs"]) == 48
    with pytest.raises(ValueError):
        manifest(cases=p["cases"], freeze=p["freeze"], stage="development")
    with pytest.raises(ValueError):
        manifest(cases=p["cases"][:-1], freeze=p["freeze"], stage="final")


def test_successes_require_grade_and_safe_cleanup():
    p = plan()
    rows = [record(p), record(p, kind="ambiguous", run_id="fixture-2", decision="held")]
    arm = summarize(p, rows)["arms"]["A"]
    assert arm["outcomes"]["repairable"]["successful"] == 1
    assert arm["outcomes"]["ambiguous"]["successful"] == 1
    rows[0]["cleanup"] = "failed"
    assert summarize(p, rows)["arms"]["A"]["outcomes"]["repairable"]["successful"] == 0
