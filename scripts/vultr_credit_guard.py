"""Administrator credit guard for this project's recorded resources only.

Runs from the owner's Windows account, outside application/candidate execution.
Provider accounting can lag and the administrator computer can be offline: this
is an operational early cutoff, never a provider guarantee against overage.
"""

import json
import re
import sys
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from vultr_phase1 import LABEL, PLANS, Admin

FINAL_TEARDOWN = datetime(2026, 11, 23, 0, 0, tzinfo=UTC)
EARLY_STOP_USD = Decimal("120")
INITIAL_CREDIT_USD = Decimal("200")


def stop_reason(account: dict, state: dict, now: datetime) -> str | None:
    if state.get("credit_guard", {}).get("admission_closed"):
        return "LATCHED_STOP"
    if now >= min(FINAL_TEARDOWN, datetime.fromisoformat(state["review_due_at"])):
        return "FUNDED_REVIEW_DEADLINE"
    try:
        balance = Decimal(str(account["balance"]))
        pending = Decimal(str(account["pending_charges"]))
        if not balance.is_finite() or not pending.is_finite() or pending < 0:
            raise ValueError("invalid accounting")
    except (KeyError, InvalidOperation, ValueError):
        return "ACCOUNTING_UNAVAILABLE"
    remaining = -balance - pending
    if INITIAL_CREDIT_USD - remaining >= EARLY_STOP_USD:
        return "EARLY_CREDIT_CUTOFF"
    return None


def run(admin: Admin, now: datetime) -> dict:
    if admin.state.get("project") != LABEL:
        raise RuntimeError("GUARD_PROJECT_MISMATCH")
    try:
        account = admin.request("GET", "/account")["account"]
    except Exception:
        account = {}  # Missing accounting closes admission; still try exact owned teardown.
    reason = stop_reason(account, admin.state, now)
    guard = admin.state.setdefault("credit_guard", {})
    guard.update({"checked_at": now.isoformat(), "early_stop_usd": str(EARLY_STOP_USD),
                  "last_reason": reason, "provider_hard_stop": False})
    if not reason:
        guard["remaining_credit_observed"] = str(
            -Decimal(str(account["balance"])) - Decimal(str(account["pending_charges"])))
        admin.save()
        return {"credit_guard": "within_early_cutoff", "checked_at": now.isoformat(),
                "remaining_credit": guard["remaining_credit_observed"],
                "review_due_at": admin.state["review_due_at"]}
    guard["admission_closed"] = True
    admin.save()  # Latch before any destructive request. No automatic recreation.
    resources = admin.state.get("resources", {})
    targets = []
    if resources.get("inference"):
        targets.append(("inference", "/inference/", "subscription", resources["inference"],
                        {"label": LABEL + "-inference"}))
    for role, plan in PLANS.items():
        if resources.get("vm_" + role):
            targets.append((role, "/instances/", "instance", resources["vm_" + role],
                            {"label": LABEL + "-" + role, "plan": plan, "region": "icn"}))
    deleted, pending = [], []
    for role, prefix, key, identifier, expected in targets:
        try:
            if not re.fullmatch(r"[a-zA-Z0-9-]{1,64}", identifier):
                raise RuntimeError("GUARD_RESOURCE_ID_INVALID")
            route = prefix + identifier
            try:
                observed = admin.request("GET", route)[key]
            except RuntimeError as error:
                if str(error) != "VULTR_HTTP_404":
                    raise
            else:
                if (any(observed.get(k) != v for k, v in expected.items())
                        or observed.get("id") != identifier
                        or (key == "instance" and LABEL not in observed.get("tags", []))):
                    raise RuntimeError("GUARD_RESOURCE_IDENTITY_MISMATCH")
                admin.request("DELETE", route)
                try:
                    admin.request("GET", route)
                except RuntimeError as error:
                    if str(error) != "VULTR_HTTP_404":
                        raise
                else:
                    raise RuntimeError("GUARD_DELETION_PENDING_READBACK")
            if role == "inference":
                guard["inference_revoked"] = True
            else:
                deleted.append(role)
        except Exception:
            # One unavailable/mismatched resource must not prevent safe teardown
            # of the other exact owned resources. Never delete an unverified ID.
            pending.append(role)
        guard["deleted_vm_roles"] = deleted.copy()
        guard["pending_resource_roles"] = pending.copy()
        admin.save()
    if pending:
        raise RuntimeError("GUARD_DELETION_UNCONFIRMED")
    # Inference dispatch runs only on the control VM; deleting it terminates its
    # credentials/callers. Unknown in-flight usage remains reserved in the ledger.
    guard["completed_at"] = now.isoformat()
    admin.save()
    return {"credit_guard": "stopped_project_compute", "reason": reason,
            "deleted_vm_roles": deleted, "provider_hard_stop": False}


if __name__ == "__main__":
    try:
        admin = Admin()
        try:
            print(json.dumps(run(admin, datetime.now(UTC))))
        finally:
            admin.close()
    except Exception:
        print("CREDIT_GUARD_FAILED_REQUIRES_ADMINISTRATOR", file=sys.stderr)
        raise SystemExit(1) from None
