"""Offline quote/admission preparation checks; no cloud resources or API calls."""

import importlib
import json
from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace

import pytest

from tests.unit.test_funded_review import fixture


@pytest.mark.parametrize("fault", [None, "extra_instance", "addon", "price", "latched",
                                  "cap", "low_credit", "nan", "cross_month"])
def test_hosting_preview_keeps_reservations_and_never_extends(monkeypatch, fault):
    _, state, account, plans, _, now = fixture(monkeypatch)
    m = importlib.import_module("prepare_judging_hosting")
    state["resources"] = {"vm_control": "control", "vm_worker": "worker"}
    instances = [{"id": role, "label": m.LABEL+'-'+role, "tags": [m.LABEL],
                  "region": "icn", "plan": plan, "features": []} for role, plan in m.PLANS.items()]
    if fault == "extra_instance":
        instances.append(dict(instances[0]))
    elif fault == "addon":
        instances[0]["features"] = ["auto_backups"]
    elif fault == "price":
        plans[0]["monthly_cost"] = 99
    elif fault == "latched":
        state["credit_guard"] = {"admission_closed": True}
    elif fault == "cap":
        state["project_limit_usd"] = 151
    elif fault == "low_credit":
        account["balance"] = -149
    elif fault == "nan":
        account["pending_charges"] = "NaN"
    elif fault == "cross_month":
        state["created_at"] = "2026-10-01T00:00:00+00:00"
    before = deepcopy((state, account, plans, instances))
    if fault:
        with pytest.raises(RuntimeError):
            m.preview(state, account, plans, instances, now)
    else:
        report = m.preview(state, account, plans, instances, now)
        assert report["additional_14_day_compute_estimate_usd"] == "36.00"
        assert report["compute_reservation_usd"] == 72
        assert report["total_reservation_usd"] == 145
        assert not report["deadline_extended"]
        assert not report["post_event_no_payment_access_verified"]
        assert report["current_funded_cutoff"] == state["review_due_at"]
    assert (state, account, plans, instances) == before


def test_actual_host_result_shape_and_readonly_operations(monkeypatch, capsys):
    _, state, account, plans, budget, now = fixture(monkeypatch)
    m = importlib.import_module("prepare_judging_hosting")
    state["resources"] = {"vm_control": "control", "vm_worker": "worker", "inference": "inference"}
    state["budget_install_intent"] = {"account_id": "account"}
    budget["id"] = "account"
    instances = [{"id": role, "label": m.LABEL+'-'+role, "tags": [m.LABEL],
                  "region": "icn", "plan": plan, "features": []} for role, plan in m.PLANS.items()]
    reservations = [{"id": str(i), "account_id": "account", "purpose": purpose,
                     "state": "reserved", "reserved_micro": amount, "charged_micro": None}
                    for i, (purpose, amount) in enumerate(
                        (("compute", 72000000), ("other", 48000000)))]
    replies = {"/account": {"account": account}, "/plans?per_page=500": {"plans": plans},
               "/instances?per_page=100": {"instances": instances, "meta": {"total": 2}},
               "/inference": {"subscriptions": [{"id": "inference",
                                                   "label": m.LABEL+'-inference'}]}}
    closed = []

    def request(method, route):
        assert method == "GET"
        return replies[route]

    def host(role, command, *, stdin):
        assert role == "control" and "-d proofflow_budget" in command
        assert stdin.startswith(b"SELECT ") and stdin.count(b";") == 1
        return SimpleNamespace(returncode=0, stdout=json.dumps({
            "account": budget, "reservations": reservations}).encode())

    monkeypatch.setattr(m, "Admin", lambda: SimpleNamespace(
        state=deepcopy(state), request=request, host=host, close=lambda: closed.append(True)))
    monkeypatch.setattr(m, "datetime", SimpleNamespace(now=lambda _: now,
                                                       fromisoformat=datetime.fromisoformat))
    m.main()
    report = json.loads(capsys.readouterr().out)
    assert report["reservations_readback"] == "PASS" and closed == [True]
    assert "account_id" not in report and not report["deadline_extended"]
