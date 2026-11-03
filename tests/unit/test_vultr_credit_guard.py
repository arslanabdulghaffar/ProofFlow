"""Offline guard fault tests. No credentials, cloud deletion or spending."""

import copy
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from vultr_credit_guard import run, stop_reason  # noqa: E402

NOW = datetime(2026, 11, 4, tzinfo=UTC)
STATE = {"project": "proofflow-phase1", "review_due_at": "2026-11-07T00:00:00+00:00",
         "resources": {"vm_control": "owned-control", "vm_worker": "owned-worker"}}


def test_cutoff_reserves_thirty_dollars_and_survives_invoice_rollover():
    assert stop_reason({"balance": "-200", "pending_charges": "119.99"}, STATE, NOW) is None
    assert stop_reason({"balance": "-200", "pending_charges": "120"}, STATE, NOW)
    assert stop_reason({"balance": "-80", "pending_charges": "0"}, STATE, NOW)
    assert stop_reason({"balance": "-100", "pending_charges": "20"}, STATE, NOW)


@pytest.mark.parametrize("account", [{}, {"balance": "NaN", "pending_charges": 0},
                                    {"balance": -200, "pending_charges": -1}])
def test_missing_or_invalid_accounting_stops(account):
    assert stop_reason(account, STATE, NOW) == "ACCOUNTING_UNAVAILABLE"


def test_deadline_and_latch_cannot_be_cleared_by_new_credit():
    rich = {"balance": -1000, "pending_charges": 0}
    assert stop_reason(rich, STATE, datetime(2026, 11, 7, tzinfo=UTC))
    state = dict(STATE, credit_guard={"admission_closed": True})
    assert stop_reason(rich, state, NOW) == "LATCHED_STOP"
    state = dict(STATE, review_due_at="2026-12-10T00:00:00+00:00")
    assert stop_reason(rich, state, datetime(2026, 11, 23, tzinfo=UTC))


class Cloud:
    def __init__(self, *, mismatch=False, lose_delete_reply=False):
        self.state = copy.deepcopy(STATE)
        self.calls = []
        self.deleted = set()
        self.mismatch, self.lose_delete_reply = mismatch, lose_delete_reply
        self.persisted = None

    def save(self):
        self.persisted = copy.deepcopy(self.state)

    def request(self, method, route):
        self.calls.append((method, route))
        if route == "/account":
            return {"account": {"balance": "-200", "pending_charges": "121"}}
        role = route.removeprefix("/instances/owned-")
        if method == "DELETE":
            assert self.persisted["credit_guard"]["admission_closed"]
            self.deleted.add(role)
            if self.lose_delete_reply:
                self.lose_delete_reply = False
                raise RuntimeError("CONNECTION_LOST")
            return {}
        if role in self.deleted:
            raise RuntimeError("VULTR_HTTP_404")
        return {"instance": {"label": "unrelated" if self.mismatch else
                             "proofflow-phase1-" + role,
                             "plan": "vhp-2c-4gb-amd" if role == "control"
                             else "vhp-4c-8gb-amd", "region": "icn",
                             "tags": ["proofflow-phase1"]}}


def test_only_exact_project_ids_deleted_and_absence_read_back():
    cloud = Cloud()
    assert run(cloud, NOW)["deleted_vm_roles"] == ["control", "worker"]
    assert cloud.deleted == {"control", "worker"}
    assert not any(method == "POST" for method, _ in cloud.calls)


def test_identity_mismatch_does_not_delete():
    cloud = Cloud(mismatch=True)
    with pytest.raises(RuntimeError, match="IDENTITY_MISMATCH"):
        run(cloud, NOW)
    assert not cloud.deleted
    assert cloud.persisted["credit_guard"]["admission_closed"]


def test_uncertain_delete_reconciles_absence_without_second_delete():
    cloud = Cloud(lose_delete_reply=True)
    with pytest.raises(RuntimeError, match="CONNECTION_LOST"):
        run(cloud, NOW)
    run(cloud, NOW)
    assert cloud.calls.count(("DELETE", "/instances/owned-control")) == 1
