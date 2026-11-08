"""Read-only judging-period cost preview. Never renews, provisions or opens admission."""

import json
from datetime import UTC, datetime
from decimal import ROUND_CEILING, Decimal

from review_credit_window import RESERVATIONS, check_reservations
from vultr_credit_guard import FINAL_TEARDOWN, stop_reason
from vultr_phase1 import LABEL, PLANS, PRICES, Admin


def require(value, code):
    if not value:
        raise RuntimeError(code)


def preview(state, account, plans, instances, now):
    require(state["project"] == LABEL and state["project_limit_usd"] == 150
            and state["reservations_usd"] == RESERVATIONS
            and state["credit_expiry_date"] == "2026-12-04", "HOSTING_PLAN_CHANGED")
    require(stop_reason(account, state, now) is None, "HOSTING_STOP_OR_ACCOUNT_REVIEW")
    remaining = -Decimal(str(account["balance"])) - Decimal(str(account["pending_charges"]))
    require(remaining >= 150, "HOSTING_CREDIT_MARGIN")
    require(len(instances) == 2, "HOSTING_INSTANCE_COUNT_CHANGED")
    quotes = []
    for role, plan_id in PLANS.items():
        selected = [p for p in plans if p["id"] == plan_id]
        require(len(selected) == 1, "HOSTING_PLAN_MISSING")
        plan = selected[0]
        require(plan["monthly_cost"] == PRICES[role] and "icn" in plan["locations"]
                and not plan.get("location_cost", {}).get("icn"), "HOSTING_QUOTE_CHANGED")
        owned = [i for i in instances if i["id"] == state["resources"]["vm_" + role]]
        require(len(owned) == 1, "HOSTING_INSTANCE_CHANGED")
        item = owned[0]
        require(item["plan"] == plan_id and item["region"] == "icn"
                and item["label"] == LABEL + "-" + role and LABEL in item["tags"]
                and not set(item.get("features", [])) & {"auto_backups", "ddos_protection"},
                "HOSTING_INSTANCE_POLICY_CHANGED")
        quotes.append({"role": role, "plan": plan_id, "monthly_usd": PRICES[role]})
    created = datetime.fromisoformat(state["created_at"])
    require(created <= now < FINAL_TEARDOWN and created.year == FINAL_TEARDOWN.year
            and created.month == FINAL_TEARDOWN.month, "HOSTING_BILLING_PERIOD_CHANGED")
    hourly = Decimal(72) / Decimal(672)

    def estimate(seconds):
        hours = (Decimal(str(seconds)) / 3600).to_integral_value(rounding=ROUND_CEILING)
        return str(min(Decimal(72), hours * hourly).quantize(Decimal("0.01"),
                                                          rounding=ROUND_CEILING))

    return {"observed_at": now.isoformat(), "status": "CONDITIONAL_READ_ONLY_PREPARATION",
            "remaining_credit_usd": str(remaining), "vm_quotes": quotes,
            "additional_7_day_compute_estimate_usd": estimate(7*86400),
            "additional_14_day_compute_estimate_usd": estimate(14*86400),
            "compute_from_creation_to_final_cutoff_estimate_usd":
                estimate((FINAL_TEARDOWN-created).total_seconds()),
            "compute_reservation_usd": 72, "total_reservation_usd": 145,
            "project_cap_usd": 150, "inference_cap_usd": 25,
            "current_funded_cutoff": state["review_due_at"],
            "absolute_final_cutoff": FINAL_TEARDOWN.isoformat(),
            "credit_ledger_expiry_date": state["credit_expiry_date"],
            "post_event_no_payment_access_verified": False,
            "provider_hard_stop_verified": False, "tax_coverage_verified": False,
            "deadline_extended": False, "new_resources": 0, "model_calls": 0,
            "estimate_note": "Compute only, rounded up; full monthly reservation retained. "
                "Excludes unknown taxes/overages. Credit is not post-event eligibility.",
            "next_review": "Closed/idle fresh review, at most48 hours via existing helper; "
                "do not reopen a latched/expired stop or change final cutoff."}


def main():
    admin = Admin()
    try:
        account = admin.request("GET", "/account")["account"]
        plans = admin.request("GET", "/plans?per_page=500")["plans"]
        result = admin.request("GET", "/instances?per_page=100")
        require(result["meta"]["total"] == len(result["instances"]), "HOSTING_PAGINATED_INSTANCES")
        record = preview(admin.state, account, plans, result["instances"], datetime.now(UTC))
        subscriptions = admin.request("GET", "/inference")["subscriptions"]
        require(len(subscriptions) == 1
                and subscriptions[0]["id"] == admin.state["resources"]["inference"]
                and subscriptions[0]["label"] == LABEL + "-inference", "HOSTING_INFERENCE_CHANGED")
        sql = ("SELECT json_build_object('account',"
               "(SELECT row_to_json(a) FROM pf_budget.accounts a),"
               "'reservations',(SELECT coalesce(json_agg(r),'[]'::json) "
               "FROM pf_budget.reservations r));")
        raw = admin.host("control", "docker exec -i --user=70:70 proofflow-budget psql -X -qAt "
                         "-h /run/proofflow-budget -U postgres -d proofflow_budget "
                         "--set ON_ERROR_STOP=1", stdin=sql.encode())
        require(raw.returncode == 0, "HOSTING_LEDGER_READ_FAILED")
        ledger = json.loads(raw.stdout)
        budget = ledger["account"]
        require(budget["id"] == admin.state["budget_install_intent"]["account_id"]
                and budget["project_limit"] == 150000000 and budget["inference_limit"] == 25000000
                and budget["probe_limit"] == 2000000
                and datetime.fromisoformat(budget["expires_at"])
                    == datetime.fromisoformat(admin.state["review_due_at"]),
                "HOSTING_BUDGET_CHANGED")
        check_reservations(ledger["reservations"], budget["id"])
        record["reservations_readback"] = "PASS"
        record["inference_admission_blocked_at_observation"] = budget["blocked"]
        print(json.dumps(record))
    finally:
        admin.close()


if __name__ == "__main__":
    main()
