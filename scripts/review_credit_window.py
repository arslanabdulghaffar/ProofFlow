"""Fresh funded review for existing resources; never create services or raise caps.

Extends one unexpired review window by at most 48 hours after actual account,
plan, identity, closed-admission and unchanged-reservation checks. A latched or
expired stop cannot be reopened. Partial/uncertain application requires readback.
"""

import argparse
import hashlib
import json
import sys
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from comparison_api import save  # noqa: E402
from install_product_services import IMAGE  # noqa: E402
from product_live_session import LiveSession, require  # noqa: E402
from vultr_credit_guard import FINAL_TEARDOWN  # noqa: E402
from vultr_phase1 import LABEL, PLANS, PRICES, PRIVATE  # noqa: E402

RESERVATIONS = {"compute": 72, "inference": 25, "later_storage": 18,
                "incidental": 10, "contingency": 20}
RUNTIME = "fd9a1e227c437066fe9bb63f14deae0567cfbb7d70a5c9e23284c2fbbb09ac17"
VERIFIER = "0290920d63d9b55108c83d300922f5af84608147495f340e86025fc0e599e63b"


def closed(live):
    # Funding uses the accepted current deployment, not frozen evaluation pins.
    require(not live.policy["enabled"] and live.policy["runtime_sha256"] == RUNTIME
            and live.policy["verifier_sha256"] == VERIFIER, "FUNDED_REVIEW_POLICY_CHANGED")
    require(live.sql("SELECT count(*)=1 AND bool_and(blocked) FROM pf_budget.accounts;",
                     "proofflow_budget") == b"t", "FUNDED_REVIEW_INFERENCE_OPEN")
    require(live.sql("SELECT count(*) FROM pf_product.jobs WHERE state NOT IN "
                     "('NEEDS_REVIEW','FAILED_INFRA','CANCELLED');") == b"0",
            "FUNDED_REVIEW_JOBS_NOT_IDLE")
    require(live.sql("SELECT count(*) FROM pf_product.pr_intents WHERE lease_owner IS NOT NULL "
                     "OR state IN ('BRANCH_PENDING','COMMIT_PENDING','PR_PENDING');") == b"0",
            "FUNDED_REVIEW_PR_NOT_IDLE")
    require(live.host("systemctl is-active proofflow-product-api.service "
                      "proofflow-product-dispatcher.service proofflow-product-retention.timer")
            == b"active\nactive\nactive", "FUNDED_REVIEW_SERVICES_UNHEALTHY")
    for role in ("api", "dispatcher"):
        require(live.host("docker inspect --format='{{.Image}}' proofflow-product-" + role)
                == ("sha256:" + IMAGE).encode(), "FUNDED_REVIEW_IMAGE_CHANGED")


def review(state, account, plans, budget, now):
    prior = datetime.fromisoformat(state["review_due_at"])
    require(
        state["project"] == LABEL
        and not state.get("credit_guard", {}).get("admission_closed")
        and now < prior < now + timedelta(hours=48),
        "FUNDED_REVIEW_CANNOT_REOPEN_STOP",
    )
    require(
        state["reservations_usd"] == RESERVATIONS
        and state["project_limit_usd"] == 150
        and state["credit_expiry_date"] == "2026-12-04",
        "FUNDED_REVIEW_ALLOCATION_CHANGED",
    )
    balance, pending = Decimal(str(account["balance"])), Decimal(str(account["pending_charges"]))
    require(balance.is_finite() and pending.is_finite() and pending >= 0,
            "FUNDED_REVIEW_ACCOUNTING_INVALID")
    remaining = -balance - pending
    require(remaining >= 150, "FUNDED_REVIEW_CREDIT_MARGIN")
    prices = {}
    for role, identifier in PLANS.items():
        selected = [p for p in plans if p["id"] == identifier]
        require(len(selected) == 1, "FUNDED_REVIEW_PLAN_MISSING")
        plan = selected[0]
        require(plan["monthly_cost"] == PRICES[role] and "icn" in plan["locations"]
                and not plan.get("location_cost", {}).get("icn"), "FUNDED_REVIEW_QUOTE_CHANGED")
        prices[role] = PRICES[role]
    require(
        budget["blocked"] is True
        and budget["project_limit"] == 150000000
        and budget["inference_limit"] == 25000000
        and budget["probe_limit"] == 2000000
        and datetime.fromisoformat(budget["expires_at"]) == prior,
        "FUNDED_REVIEW_BUDGET_CHANGED",
    )
    due = min(now + timedelta(hours=48), FINAL_TEARDOWN)
    created = datetime.fromisoformat(state["created_at"])
    require(created <= now < due and prior < due and created.year == due.year
            and created.month == due.month, "FUNDED_REVIEW_BILLING_PERIOD")
    # Preserve the full $72 monthly compute allocation rather than refunding it
    # using an hourly estimate. No provider hard-stop or tax coverage is inferred.
    return {"prior_review_due_at": prior.isoformat(), "review_due_at": due.isoformat(),
            "reviewed_at": now.isoformat(), "remaining_credit": str(remaining),
            "monthly_compute_quote_usd": sum(prices.values()), "reserved_total_usd": 145,
            "project_cap_usd": 150, "inference_cap_usd": 25,
            "provider_hard_stop": False, "tax_coverage_verified": False,
            "new_resources": 0, "admission": False, "inference": False}


def check_reservations(rows, account):
    totals = dict.fromkeys(("compute", "other", "inference", "probe"), 0)
    seen = set()
    for row in rows:
        require(row["account_id"] == account and row["id"] not in seen
                and row["purpose"] in totals
                and row["state"] in {"reserved", "uncertain", "settled"},
                "FUNDED_REVIEW_RESERVATION_SCOPE")
        seen.add(row["id"])
        amount = row["charged_micro"] if row["state"] == "settled" else row["reserved_micro"]
        require(type(amount) is int and amount >= 0, "FUNDED_REVIEW_RESERVATION_AMOUNT")
        totals[row["purpose"]] += amount
    require(totals["compute"] == 72000000 and totals["other"] == 48000000
            and totals["probe"] <= 2000000 and totals["probe"] + totals["inference"] <= 25000000,
            "FUNDED_REVIEW_RESERVATION_CAP")


LEDGER_SQL = "SELECT coalesce(json_agg(r ORDER BY id),'[]'::json) FROM pf_budget.reservations r;"


def receipt_prefix(review_date):
    require(date.fromisoformat(review_date).isoformat() == review_date,
            "FUNDED_REVIEW_DATE_INVALID")
    return "funded-review-" + review_date


def apply_review(live, budget, before, record, root, review_date="2026-11-06"):
    prefix = receipt_prefix(review_date)
    save(root, prefix + "-intent.json", record)
    prior = datetime.fromisoformat(record["prior_review_due_at"]).isoformat()
    due = datetime.fromisoformat(record["review_due_at"]).isoformat()
    identifier = str(UUID(budget["id"]))
    # Trusted administrative funding configuration, never product statuses or
    # a refund. Parsed UUID/datetimes only. Old guard stays stricter on failure.
    changed = live.sql(
        "UPDATE pf_budget.accounts SET expires_at='" + due + "' WHERE id='" + identifier  # noqa: S608
        + "' AND blocked AND expires_at='" + prior + "' AND project_limit=150000000"
        + " AND inference_limit=25000000 AND probe_limit=2000000 RETURNING expires_at;",
        "proofflow_budget",
    )
    require(datetime.fromisoformat(changed.decode()) == datetime.fromisoformat(due),
            "FUNDED_REVIEW_SQL_UNCERTAIN")
    require(live.sql(LEDGER_SQL, "proofflow_budget") == before,
            "FUNDED_REVIEW_RESERVATIONS_CHANGED")
    readback = json.loads(live.sql("SELECT row_to_json(a) FROM pf_budget.accounts a;",
                                  "proofflow_budget"))
    require(readback == {**budget, "expires_at": readback["expires_at"]}
            and datetime.fromisoformat(readback["expires_at"]) == datetime.fromisoformat(due),
            "FUNDED_REVIEW_READBACK_FAILED")
    live.admin.state["review_due_at"] = due
    live.admin.state["funded_review"] = record
    live.admin.save()
    save(root, prefix + "-completed.json", record)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", required=True)
    parser.add_argument("--review-date", required=True, help="Today's KST date; new receipt only")
    options = parser.parse_args()
    require(options.review_date == (datetime.now(UTC)+timedelta(hours=9)).date().isoformat(),
            "FUNDED_REVIEW_DATE_MUST_BE_TODAY_KST")
    prefix = receipt_prefix(options.review_date)
    root = PRIVATE / "evidence"
    require(not (root / (prefix + "-intent.json")).exists(),
            "FUNDED_REVIEW_ALREADY_ATTEMPTED_RECONCILE")
    with LiveSession() as live:
        closed(live)
        account = live.admin.request("GET", "/account")["account"]
        plans = live.admin.request("GET", "/plans?per_page=500")["plans"]
        resources = live.admin.state["resources"]
        instances = live.admin.request("GET", "/instances?per_page=100")
        require(instances["meta"]["total"] == 2 and len(instances["instances"]) == 2,
                "FUNDED_REVIEW_RESOURCE_COUNT_CHANGED")
        for role, plan in PLANS.items():
            observed = [i for i in instances["instances"] if i["id"] == resources["vm_" + role]]
            require(len(observed) == 1, "FUNDED_REVIEW_INSTANCE_CHANGED")
            item = observed[0]
            require(item["label"] == LABEL + "-" + role and item["plan"] == plan
                    and item["region"] == "icn" and LABEL in item["tags"]
                    and not set(item.get("features", [])) & {"auto_backups", "ddos_protection"},
                    "FUNDED_REVIEW_INSTANCE_POLICY_CHANGED")
        inference = live.admin.request("GET", "/inference")["subscriptions"]
        require(len(inference) == 1 and inference[0]["id"] == resources["inference"]
                and inference[0]["label"] == LABEL + "-inference",
                "FUNDED_REVIEW_INFERENCE_CHANGED")
        accounts = json.loads(live.sql("SELECT json_agg(a) FROM pf_budget.accounts a;",
                                      "proofflow_budget"))
        require(len(accounts) == 1, "FUNDED_REVIEW_ACCOUNT_COUNT_CHANGED")
        budget = accounts[0]
        identifier = str(UUID(budget["id"]))
        require(identifier == live.admin.state["budget_install_intent"]["account_id"],
                "FUNDED_REVIEW_ACCOUNT_CHANGED")
        before = live.sql(LEDGER_SQL, "proofflow_budget")
        check_reservations(json.loads(before), identifier)
        record = review(live.admin.state, account, plans, budget, datetime.now(UTC))
        record["reservation_sha256"] = hashlib.sha256(before).hexdigest()
        apply_review(live, budget, before, record, root, options.review_date)
        print(json.dumps(record))


if __name__ == "__main__":
    main()
