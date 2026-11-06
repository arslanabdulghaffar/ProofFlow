"""Offline funded-window tests; no cloud calls, credentials or resource changes."""

import importlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest


def fixture(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    m = importlib.import_module("scripts.review_credit_window")
    now = datetime(2026, 11, 6, 15, tzinfo=UTC)
    prior = (now + timedelta(hours=6)).isoformat()
    state = {"project": m.LABEL, "review_due_at": prior,
             "created_at": (now - timedelta(days=2)).isoformat(),
             "credit_expiry_date": "2026-12-04", "project_limit_usd": 150,
             "reservations_usd": dict(m.RESERVATIONS)}
    account = {"balance": -200, "pending_charges": 7}
    plans = [{"id": value, "monthly_cost": m.PRICES[key], "locations": ["icn"]}
             for key, value in m.PLANS.items()]
    budget = {"blocked": True, "project_limit": 150000000, "inference_limit": 25000000,
              "probe_limit": 2000000, "expires_at": prior}
    return m, state, account, plans, budget, now


def test_review_preserves_full_allocations_caps_and_bounded_window(monkeypatch):
    m, *args = fixture(monkeypatch)
    result = m.review(*args)
    assert datetime.fromisoformat(result["review_due_at"]) == args[-1] + timedelta(hours=48)
    assert result["remaining_credit"] == "193" and result["reserved_total_usd"] == 145
    assert result["project_cap_usd"] == 150 and result["inference_cap_usd"] == 25
    assert result["new_resources"] == 0 and not result["admission"]
    assert not result["provider_hard_stop"] and not result["tax_coverage_verified"]


@pytest.mark.parametrize("fault", ["expired", "latched", "allocation", "credit", "nan",
                                  "quote", "region", "open", "cap", "expiry", "period"])
def test_changed_or_unfunded_state_cannot_extend(monkeypatch, fault):
    m, state, account, plans, budget, now = fixture(monkeypatch)
    if fault == "expired":
        state["review_due_at"] = now.isoformat()
    elif fault == "latched":
        state["credit_guard"] = {"admission_closed": True}
    elif fault == "allocation":
        state["reservations_usd"]["inference"] = 26
    elif fault == "credit":
        account["pending_charges"] = 51
    elif fault == "nan":
        account["balance"] = "NaN"
    elif fault == "quote":
        plans[0]["monthly_cost"] += 1
    elif fault == "region":
        plans[0]["location_cost"] = {"icn": 5}
    elif fault == "open":
        budget["blocked"] = False
    elif fault == "cap":
        budget["inference_limit"] += 1
    elif fault == "expiry":
        budget["expires_at"] = now.isoformat()
    else:
        state["created_at"] = "2026-10-01T00:00:00+00:00"
    with pytest.raises(RuntimeError):
        m.review(state, account, plans, budget, now)


@pytest.mark.parametrize("fault", [None, "missing", "overspend", "foreign", "duplicate"])
def test_existing_conservative_reservations_are_not_released(monkeypatch, fault):
    m, *_ = fixture(monkeypatch)
    rows = [{"id": str(i), "account_id": "fixture", "purpose": p, "state": "reserved",
             "reserved_micro": amount, "charged_micro": None}
            for i, (p, amount) in enumerate((("compute", 72000000), ("other", 48000000),
                                             ("inference", 5000000), ("probe", 1000000)))]
    if fault == "missing":
        rows.pop(0)
    elif fault == "overspend":
        rows[2]["reserved_micro"] = 25000000
    elif fault == "foreign":
        rows[0]["account_id"] = "other"
    elif fault == "duplicate":
        rows.append(rows[-1])
    if fault:
        with pytest.raises(RuntimeError):
            m.check_reservations(rows, "fixture")
    else:
        m.check_reservations(rows, "fixture")


@pytest.mark.parametrize("fault", [None, "lost_reply", "ledger", "readback"])
def test_durable_intent_and_old_deadline_preserved_on_uncertainty(monkeypatch, tmp_path, fault):
    m, state, account, plans, budget, now = fixture(monkeypatch)
    budget["id"] = str(uuid4())
    record = m.review(state, account, plans, budget, now)
    before = b"opaque ledger bytes"
    saved, writes = [], []
    admin = SimpleNamespace(state=state, save=lambda: saved.append(dict(state)))

    def sql(statement, database):
        assert database == "proofflow_budget"
        if statement.startswith("UPDATE"):
            assert (tmp_path / "funded-review-2026-11-06-intent.json").exists()
            assert not saved and state["review_due_at"] == record["prior_review_due_at"]
            writes.append(statement)
            if fault == "lost_reply":
                raise RuntimeError("SIMULATED_UNKNOWN_COMMIT")
            return record["review_due_at"].encode()
        if statement == m.LEDGER_SQL:
            return b"changed" if fault == "ledger" else before
        result = {**budget, "expires_at": record["review_due_at"]}
        if fault == "readback":
            result["blocked"] = False
        return json.dumps(result).encode()

    live = SimpleNamespace(admin=admin, sql=sql)
    if fault:
        with pytest.raises(RuntimeError):
            m.apply_review(live, budget, before, record, tmp_path)
        assert not saved and state["review_due_at"] == record["prior_review_due_at"]
        assert not (tmp_path / "funded-review-2026-11-06-completed.json").exists()
    else:
        m.apply_review(live, budget, before, record, tmp_path)
        assert len(saved) == 1 and state["review_due_at"] == record["review_due_at"]
    # Even an uncertain update is never submitted again through this intent.
    with pytest.raises(FileExistsError):
        m.apply_review(live, budget, before, record, tmp_path)
    assert len(writes) == 1
