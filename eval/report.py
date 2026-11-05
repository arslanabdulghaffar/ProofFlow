"""Offline bounded evaluation accounting. Never executes candidates or calls a provider.

Records must be reconciled to real private receipts before publication. Hash binding
detects accidental mixing; it is not a signature or proof that a measurement occurred.
"""

import hashlib
import math
import re
from collections import Counter
from statistics import median

from contracts.codec import canonical_bytes

ARMS = ("A", "B", "C", "D")
FAMILIES = ("schema", "units", "joins", "duplicates", "completeness", "downstream")
HASH = re.compile(r"[a-f0-9]{64}")
ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
DECISIONS = {"accepted", "held", "clarification", "failed", "timeout", "cancelled"}


def require(value):
    if not value:
        raise ValueError("EVALUATION_RECORD_INVALID")


def digest(value):
    raw = canonical_bytes({"domain": "proofflow-eval-v1", "value": value})
    return hashlib.sha256(raw).hexdigest()


def integer(value, maximum):
    return type(value) is int and 0 <= value <= maximum


def manifest(*, cases, freeze, stage, repeats=1):
    """Predeclare balanced cases, artifact identities and equal cost ceilings.

This is a schedule/forecast only. Actual dispatch also requires the durable budget
ledger and fresh credit/rate evidence; this object never opens admission.
"""
    require(stage in ("development", "final") and type(repeats) is int and repeats in (1, 3))
    require(type(cases) is list and 1 <= len(cases) <= 24)
    require(type(freeze) is dict and set(freeze) == {
        "source", "prompts", "runtime", "schemas", "grader", "model_quote",
    } and all(type(v) is str and HASH.fullmatch(v) for v in freeze.values()))
    seen = set()
    for case in cases:
        require(type(case) is dict and set(case) == {"id", "family", "kind", "sha256"})
        require(type(case["id"]) is str and ID.fullmatch(case["id"]) and case["id"] not in seen)
        require(case["family"] in FAMILIES and case["kind"] in ("repairable", "ambiguous"))
        require(type(case["sha256"]) is str and HASH.fullmatch(case["sha256"]))
        seen.add(case["id"])
    if stage == "final":
        require(len(cases) in (12, 24))
        for family in FAMILIES:
            counts = Counter(c["kind"] for c in cases if c["family"] == family)
            require(counts == {"repairable": len(cases) // 6 - 1, "ambiguous": 1})
    cap = 50000 if repeats == 3 else 100000
    reserved = len(cases) * 3 * repeats * cap
    require(reserved <= (1200000 if stage == "development" else 12000000))
    jobs = []
    # Each case/repeat gets one interleaved A/B/C round; D runs once/case.
    # Ordering depends on public case hashes, never outcomes or protected seeds.
    for repeat in range(1, repeats + 1):
        for case in sorted(cases, key=lambda item: digest([item["sha256"], repeat])):
            arms = sorted(ARMS if repeat == 1 else ARMS[:3],
                          key=lambda arm: digest([case["sha256"], repeat, arm]))
            jobs.extend({"case": case["id"], "arm": arm, "repeat": repeat} for arm in arms)
    return {"version": "proofflow-evaluation-v1", "stage": stage, "repeats": repeats,
            "cases": cases, "freeze": freeze, "jobs": jobs,
            "per_model_job_cap_micro_usd": cap, "forecast_micro_usd": reserved,
            "dispatch_authorized": False}


def percentiles(values):
    if not values:
        return {"n": 0, "median_ms": None, "p95_ms": None}
    ordered = sorted(values)
    return {"n": len(values), "median_ms": median(ordered),
            "p95_ms": ordered[math.ceil(0.95 * len(ordered)) - 1]}


def summarize(plan, records):
    """Keep missing runs, failures, unknown grades/costs and cleanup in the report."""
    require(type(plan) is dict)
    expected = manifest(cases=plan["cases"], freeze=plan["freeze"],
                        stage=plan["stage"], repeats=plan["repeats"])
    require(plan == expected)
    require(type(records) is list and len(records) <= len(plan["jobs"]))
    plan_hash = digest(plan)
    keys = {(j["case"], j["arm"], j["repeat"]) for j in plan["jobs"]}
    seen, run_ids = {}, set()
    for row in records:
        require(type(row) is dict and set(row) == {
            "plan_sha256", "run_id", "case", "arm", "repeat", "decision", "grade",
            "cleanup", "latency_ms", "calls", "input_tokens", "output_tokens",
            "reserved_micro_usd", "estimated_micro_usd", "receipt_sha256",
        })
        key = (row["case"], row["arm"], row["repeat"])
        require(key in keys and key not in seen and type(row["repeat"]) is int)
        require(type(row["run_id"]) is str and ID.fullmatch(row["run_id"])
                and row["run_id"] not in run_ids and row["plan_sha256"] == plan_hash)
        require(type(row["receipt_sha256"]) is str and HASH.fullmatch(row["receipt_sha256"]))
        require(row["decision"] in DECISIONS
                and row["grade"] in ("correct", "incorrect", "unknown"))
        require(row["cleanup"] in ("confirmed", "failed", "unknown", "no_execution"))
        require(integer(row["latency_ms"], 3600000) and integer(row["calls"], 3))
        require(integer(row["reserved_micro_usd"], plan["per_model_job_cap_micro_usd"]))
        usage = (row["input_tokens"], row["output_tokens"], row["estimated_micro_usd"])
        require(all(v is None for v in usage) or (
            integer(usage[0], 3 * 262144) and integer(usage[1], 3 * 8192)
            and integer(usage[2], row["reserved_micro_usd"])))
        if row["arm"] == "D" or row["calls"] == 0:
            require(row["calls"] == 0 and row["reserved_micro_usd"] == 0 and usage == (0, 0, 0))
        else:
            require(row["reserved_micro_usd"] > 0)
        if row["decision"] == "accepted":
            require(row["cleanup"] in ("confirmed", "failed", "unknown"))
        seen[key] = row
        run_ids.add(row["run_id"])
    report = {"plan_sha256": plan_hash, "stage": plan["stage"],
              "evidence_validation": "RECEIPT_RECONCILIATION_REQUIRED",
              "held_out_claim": "NOT_ESTABLISHED_BY_ACCOUNTING",
              "cost_unit": "micro_USD", "cost_source": "provider_usage_estimate_not_invoice",
              "arms": {}}
    for arm in ARMS:
        planned = [j for j in plan["jobs"] if j["arm"] == arm]
        rows = [r for r in records if r["arm"] == arm]
        accepted = [r for r in rows if r["decision"] == "accepted"]
        wrong = sum(r["grade"] == "incorrect" for r in accepted)
        unknown = sum(r["grade"] == "unknown" for r in accepted)
        families = {}
        for family in FAMILIES:
            ids = {c["id"] for c in plan["cases"] if c["family"] == family}
            families[family] = {"planned": sum(j["case"] in ids for j in planned),
                                "observed": sum(r["case"] in ids for r in rows)}
        outcomes = {}
        for kind in ("repairable", "ambiguous"):
            ids = {c["id"] for c in plan["cases"] if c["kind"] == kind}
            counted = [r for r in rows if r["case"] in ids]
            successful = sum(r["grade"] == "correct"
                             and r["cleanup"] in ("confirmed", "no_execution")
                             and r["decision"] in (("accepted",) if kind == "repairable"
                                                   else ("held", "clarification"))
                             for r in counted)
            outcomes[kind] = {"planned": sum(j["case"] in ids for j in planned),
                              "observed": len(counted), "successful": successful,
                              "not_run": sum(j["case"] in ids for j in planned) - len(counted)}
        report["arms"][arm] = {
            "planned": len(planned), "observed": len(rows), "not_run": len(planned) - len(rows),
            "decisions": dict(Counter(r["decision"] for r in rows)), "outcomes": outcomes,
            "accepted": len(accepted), "incorrect_accepted": wrong, "ungraded_accepted": unknown,
            "incorrect_acceptance_rate": (
                wrong / len(accepted) if accepted and not unknown else None),
            "cleanup_failures": sum(r["cleanup"] == "failed" for r in rows),
            "cleanup_unknown": sum(r["cleanup"] == "unknown" for r in rows),
            "latency": percentiles([r["latency_ms"] for r in rows]),
            "calls": sum(r["calls"] for r in rows),
            "known_input_tokens": sum(r["input_tokens"] or 0 for r in rows),
            "known_output_tokens": sum(r["output_tokens"] or 0 for r in rows),
            "reserved_micro_usd": sum(r["reserved_micro_usd"] for r in rows),
            "known_estimated_micro_usd": sum(r["estimated_micro_usd"] or 0 for r in rows),
            "usage_unknown_runs": sum(r["estimated_micro_usd"] is None for r in rows),
            "families": families,
        }
    return report
