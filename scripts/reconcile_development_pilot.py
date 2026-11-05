"""Pilot readback; explicit one-time flag adds its conservative development allocation."""

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from product_live_session import LiveSession, require  # noqa: E402
from vultr_phase1 import PRIVATE, ROOT  # noqa: E402

from eval.development import cases  # noqa: E402
from eval.report import digest, manifest, summarize  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--record-completed-allocation", action="store_true",
                        help="Reserve the completed pilot's $1.20 allowance, without model calls")
    args = parser.parse_args()
    source = PRIVATE / "evidence/phase5-model-pilot-v1.json"
    pilot = json.loads(source.read_bytes())
    require(pilot["completed"] and pilot["budget_closed"] and len(pilot["runs"]) == 12,
            "PILOT_INCOMPLETE")
    calls = [c for r in pilot["runs"] for c in r["calls"]]
    ids = [str(UUID(c["request"])) for c in calls]
    require(len(set(ids)) == len(ids), "DUPLICATE_PILOT_CALL")
    with LiveSession() as live:
        require(live.sql("SELECT count(*)=1 AND bool_and(blocked) FROM pf_budget.accounts;",
                         "proofflow_budget") == b"t", "INFERENCE_NOT_CLOSED")
        allocation = str(UUID(pilot["settings"]["jobs"][0]["run_id"]))
        require(len(pilot["revision"]) == 64 and all(c in "0123456789abcdef"
                for c in pilot["revision"]), "INVALID_PILOT_REVISION")
        if args.record_completed_allocation:
            live.sql("SET ROLE pf_product_provisioner; SELECT pf_product.reserve_evaluation('"
                     + allocation + "','" + pilot["revision"] + "',1200000);")
        # UUID-only values, not source/model SQL. No credentials or provider bodies returned.
        names = ",".join("'" + identifier + "'::uuid" for identifier in ids)
        raw = live.sql("SELECT jsonb_agg(jsonb_build_object('id',p.id,'reserve',p.reserve_micro,"
            "'outcome',p.outcome,'response_sha256',p.response_hash,'reservation_state',r.state,"
            "'usage',convert_from(p.response,'UTF8')::jsonb->'usage',"
            "'model',convert_from(p.payload,'UTF8')::jsonb->>'model')) "
            "FROM pf_budget.probe_receipts p JOIN pf_budget.reservations r ON r.id=p.id "
            "WHERE p.id IN (" + names + ");", "proofflow_budget")
        receipts = {r["id"]: r for r in json.loads(raw)}
        require(set(receipts) == set(ids), "PILOT_RECEIPT_MISSING")
        for call in calls:
            row = receipts[call["request"]]
            require(row["reserve"] == call["reserved_micro_usd"]
                    and row["outcome"] == "PARSED_RESPONSE"
                    and row["response_sha256"] == call["response_sha256"]
                    and row["reservation_state"] == "uncertain"
                    and row["model"] == "qwen3.8-flash-next"
                    and row["usage"]["prompt_tokens"] == call["input_tokens"]
                    and row["usage"]["completion_tokens"] == call["output_tokens"],
                    "PILOT_RECEIPT_DISAGREEMENT")
        final = {"observed_at": datetime.now(UTC).isoformat(), "credit": live.credit,
                 "budget_closed": True, "execution_enabled": live.policy["enabled"],
                 "provider_receipts": list(receipts.values())}
        final["shared_development_allocation"] = json.loads(live.sql(
            "SELECT jsonb_build_object('pilot_reserved_micro',e.reserved_micro,"
            "'manifest_sha256',e.manifest_sha256,'total_reserved_micro',a.reserved_micro) "
            "FROM pf_product.evaluation_allocations e CROSS JOIN pf_product.repair_allocation a "
            "WHERE e.id='" + allocation + "';"))
        require(final["shared_development_allocation"]["pilot_reserved_micro"] == 1200000
                and final["shared_development_allocation"]["manifest_sha256"] == pilot["revision"]
                and final["shared_development_allocation"]["total_reserved_micro"] <= 5000000,
                "PILOT_SHARED_ALLOCATION_MISSING")
        final["retention"] = json.loads(live.sql("SELECT jsonb_build_object("
            "'remaining_workspaces',(SELECT count(*) FROM pf_product.workspaces),"
            "'expired_workspaces',(SELECT count(*) FROM pf_product.workspaces "
            "WHERE expires_at<=clock_timestamp()),'completed_deletions',(SELECT count(*) "
            "FROM pf_product.deletions WHERE completed_at IS NOT NULL));"))
        deleted = json.loads(live.sql("SELECT coalesce(jsonb_agg(workspace_id),'[]') "
            "FROM pf_product.deletions WHERE completed_at IS NOT NULL;"))
        absent = 0
        for identifier in deleted:
            identifier = UUID(identifier).hex
            require(live.host("test ! -e /var/lib/proofflow-product/assets/" + identifier
                    + " && test -f /var/lib/proofflow-product/assets/.deleted-" + identifier
                    + " && echo passed") == b"passed", "RETENTION_BYTES_OR_MARKER_FAILED")
            absent += 1
        final["retention"]["asset_absence_and_markers_verified"] = absent
        services = live.host("systemctl is-active proofflow-product-api.service "
            "proofflow-product-dispatcher.service proofflow-product-retention.timer")
        final["services"] = services.decode().splitlines()
        require(final["services"] == ["active"] * 3, "SERVICE_HEALTH_FAILED")
        final["pr"] = json.loads(live.sql("SELECT jsonb_build_object('state',state,'writes',"
            "(SELECT count(*) FROM pf_product.pr_writes w WHERE w.intent_id=p.id)) "
            "FROM pf_product.pr_intents p WHERE id='b34e8d47-ab50-4527-a83f-c72feca85c40';"))
        require(final["pr"] == {"state": "COMPLETE", "writes": 3}, "PR_RECEIPTS_CHANGED")
        runtime, grader = live.policy["runtime_sha256"], live.policy["verifier_sha256"]
    def file_hash(name):
        return hashlib.sha256((ROOT / name).read_bytes()).hexdigest()

    freeze = {"source": digest(pilot["sources"]),
              "prompts": file_hash("orchestrator/repair_proposal.py"),
              "runtime": runtime, "grader": grader,
              "schemas": file_hash("schemas/merchant_revenue_v1.1.schema.json"),
              "model_quote": digest(pilot["settings"]["provider"]["quote"])}
    selected = [{k: c[k] for k in ("id", "family", "kind", "sha256")}
                for c in cases() if c["id"] in pilot["settings"]["cases"]]
    plan = manifest(cases=selected, freeze=freeze, stage="development")
    records = []
    for run in pilot["runs"]:
        known = all(c["estimated_micro_usd"] is not None for c in run["calls"])
        records.append({"plan_sha256": digest(plan), "run_id": run["run_id"], "case": run["case"],
            "arm": run["arm"], "repeat": 1, "decision": run["decision"], "grade": run["grade"],
            "cleanup": run["cleanup"], "latency_ms": run["elapsed_ms"], "calls": len(run["calls"]),
            "input_tokens": sum(c["input_tokens"] for c in run["calls"]) if known else None,
            "output_tokens": sum(c["output_tokens"] for c in run["calls"]) if known else None,
            "reserved_micro_usd": sum(c["reserved_micro_usd"] for c in run["calls"]),
            "estimated_micro_usd": sum(c["estimated_micro_usd"] for c in run["calls"])
                if known else None,
            "receipt_sha256": hashlib.sha256(json.dumps(run, sort_keys=True).encode()).hexdigest()})
    report = summarize(plan, records)
    report["evidence_validation"] = f"{len(calls)}_ACTUAL_PROVIDER_RECEIPTS_RECONCILED"
    report["scope_notes"] = ["Development repair-core pilot, not held-out or product end-to-end",
        "D not run in this pilot; prior positive-control runs are not silently reused",
        "Accounting manifest assembled after runs; launch manifest/revision fixed before calls",
        "Three repairable plus one source-ambiguous case; small disclosed canary-derived sample",
        "Reported usage estimate is not a settled provider invoice; reservations remain held"]
    evidence = {"pilot_revision": pilot["revision"], "pilot_receipt_sha256":
        hashlib.sha256(source.read_bytes()).hexdigest(), "report": report, "records": records,
        "accounting_manifest": plan, "final_state": final}
    (PRIVATE / "evidence/phase5-pilot-reconciled.json").write_text(json.dumps(evidence, indent=2))
    print(json.dumps({"jobs": 12, "provider_calls": len(calls),
                      "reserved_micro_usd": sum(c["reserved_micro_usd"] for c in calls),
                      "estimated_micro_usd": sum(c["estimated_micro_usd"] for c in calls),
                      "retention": final["retention"],
                      "credit": final["credit"]["remaining_credit"]}))


if __name__ == "__main__":
    main()
