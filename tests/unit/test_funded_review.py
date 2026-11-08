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
@pytest.mark.parametrize("review_date", ["2026-11-06", "2026-11-08"])
def test_durable_intent_and_old_deadline_preserved_on_uncertainty(
    monkeypatch, tmp_path, fault, review_date
):
    m, state, account, plans, budget, now = fixture(monkeypatch)
    budget["id"] = str(uuid4())
    record = m.review(state, account, plans, budget, now)
    before = b"opaque ledger bytes"
    saved, writes = [], []
    admin = SimpleNamespace(state=state, save=lambda: saved.append(dict(state)))

    def sql(statement, database):
        assert database == "proofflow_budget"
        if statement.startswith("UPDATE"):
            assert (tmp_path / ("funded-review-"+review_date+"-intent.json")).exists()
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
            m.apply_review(live, budget, before, record, tmp_path, review_date)
        assert not saved and state["review_due_at"] == record["prior_review_due_at"]
        assert not (tmp_path / ("funded-review-"+review_date+"-completed.json")).exists()
    else:
        m.apply_review(live, budget, before, record, tmp_path, review_date)
        assert len(saved) == 1 and state["review_due_at"] == record["review_due_at"]
    # Even an uncertain update is never submitted again through this intent.
    with pytest.raises(FileExistsError):
        m.apply_review(live, budget, before, record, tmp_path, review_date)
    assert len(writes) == 1


@pytest.mark.parametrize("field", ["enabled", "runtime_sha256", "verifier_sha256"])
def test_funding_cannot_accept_open_or_different_deployment(monkeypatch, field):
    m, *_ = fixture(monkeypatch)
    policy = {"enabled":False,"runtime_sha256":m.RUNTIME,"verifier_sha256":m.VERIFIER}
    policy[field] = True if field == "enabled" else "0"*64
    with pytest.raises(RuntimeError, match="POLICY_CHANGED"):
        m.closed(SimpleNamespace(policy=policy))


@pytest.mark.parametrize("phase", ["unapplied", "remote", "local", "complete"])
def test_readonly_inspection_classifies_crash_boundaries(monkeypatch, phase):
    import hashlib
    from copy import deepcopy

    m, state, account, plans, budget, now = fixture(monkeypatch)
    budget["id"] = "synthetic-account"
    state["budget_install_intent"] = {"account_id": budget["id"]}
    ledger = json.dumps([
        {"id": str(i), "account_id": budget["id"], "purpose": purpose, "state": "reserved",
         "reserved_micro": amount, "charged_micro": None}
        for i, (purpose, amount) in enumerate((("compute", 72000000), ("other", 48000000)))
    ]).encode()
    intent = m.review(state, account, plans, budget, now)
    intent["reservation_sha256"] = hashlib.sha256(ledger).hexdigest()
    completed = None
    if phase != "unapplied":
        budget["expires_at"] = intent["review_due_at"]
    if phase in {"local", "complete"}:
        state["review_due_at"] = intent["review_due_at"]
        state["funded_review"] = intent
    if phase == "complete":
        completed = deepcopy(intent)
    before = deepcopy((state, budget, intent, completed))
    report = m.inspect_review(state, budget, intent, completed, ledger, now)
    assert report["status"] == {"unapplied": "NOT_APPLIED_NO_RETRY",
        "remote": "REMOTE_APPLIED_LOCAL_PENDING", "local": "LOCAL_APPLIED_RECEIPT_PENDING",
        "complete": "COMPLETED_MATCHED"}[phase]
    assert report["requires_reconciliation"] == (phase != "complete")
    assert report["read_only"] and not report["deadline_extended"]
    assert not report["admission_opened"] and not report["post_event_access_verified"]
    assert (state, budget, intent, completed) == before


@pytest.mark.parametrize("fault", ["latched", "expired", "foreign", "cap", "timeline",
                                  "ledger", "receipt", "local", "remote", "open"])
def test_funding_inspection_cannot_accept_changed_or_stopped_authority(monkeypatch, fault):
    import hashlib

    m, state, account, plans, budget, now = fixture(monkeypatch)
    budget["id"] = "synthetic-account"
    state["budget_install_intent"] = {"account_id": budget["id"]}
    ledger = json.dumps([
        {"id": str(i), "account_id": budget["id"], "purpose": purpose, "state": "reserved",
         "reserved_micro": amount, "charged_micro": None}
        for i, (purpose, amount) in enumerate((("compute", 72000000), ("other", 48000000)))
    ]).encode()
    intent = m.review(state, account, plans, budget, now)
    intent["reservation_sha256"] = hashlib.sha256(ledger).hexdigest()
    completed = None
    if fault == "latched":
        state["credit_guard"] = {"admission_closed": True}
    elif fault == "expired":
        now += timedelta(hours=7)
    elif fault == "foreign":
        budget["id"] = "different"
    elif fault == "cap":
        budget["project_limit"] += 1
    elif fault == "timeline":
        intent["review_due_at"] = (now+timedelta(hours=49)).isoformat()
    elif fault == "ledger":
        ledger += b" "
    elif fault == "receipt":
        completed = {**intent, "new_resources": 1}
    elif fault == "local":
        state["review_due_at"] = (now+timedelta(hours=4)).isoformat()
    elif fault == "remote":
        budget["expires_at"] = (now+timedelta(hours=4)).isoformat()
    else:
        budget["blocked"] = False
    with pytest.raises(RuntimeError, match="FUNDED_INSPECTION_"):
        m.inspect_review(state, budget, intent, completed, ledger, now)



def test_inspect_entrypoint_cannot_enter_live_session_or_echo_native_error(monkeypatch, capsys):
    m, *_ = fixture(monkeypatch)
    monkeypatch.setattr(m.sys, "argv", ["review", "--inspect", "--review-date", "2026-11-08"])
    monkeypatch.setattr(m, "LiveSession", lambda: pytest.fail("mutating session reached"))

    def fail(*_):
        raise RuntimeError("synthetic-private-native-diagnostic")

    monkeypatch.setattr(m, "inspect_saved_review", fail)
    assert m.main() == 1
    raw = capsys.readouterr().out
    assert "synthetic-private" not in raw
    assert json.loads(raw)["requires_reconciliation"]


def test_inspection_only_uses_pinned_identity_and_readonly_snapshot(monkeypatch, tmp_path):
    m, state, _, _, budget, now = fixture(monkeypatch)
    state["control_machine_id"] = "synthetic-machine"
    prefix = "funded-review-2026-11-08"
    for suffix in ("intent", "completed"):
        (tmp_path / (prefix+"-"+suffix+".json")).write_text("{}")
    closed, reached = [], []

    def host(role, command, **kwargs):
        assert role == "control"
        reached.append(command)
        if command == "cat /etc/machine-id":
            return SimpleNamespace(returncode=0, stdout=b"synthetic-machine\n")
        assert "-d proofflow_budget" in command and "-X -qAt" in command
        query = kwargs["stdin"].decode()
        assert query.startswith("BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;")
        assert "UPDATE" not in query and "DELETE" not in query
        assert "::text" in query and query.endswith("COMMIT;")
        return SimpleNamespace(returncode=0, stdout=json.dumps({
            "accounts": [budget], "ledger": "[]"}).encode())

    monkeypatch.setattr(m, "Admin", lambda: SimpleNamespace(
        state=state, host=host, close=lambda: closed.append(True)))
    monkeypatch.setattr(m, "inspect_review", lambda *args: {"ledger_bytes": args[-2] == b"[]"})
    assert m.inspect_saved_review(tmp_path, "2026-11-08") == {"ledger_bytes": True}
    assert len(reached) == 2 and closed == [True]
