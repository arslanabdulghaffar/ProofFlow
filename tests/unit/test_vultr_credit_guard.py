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
        return {"instance": {"id": "owned-" + role, "label": "unrelated" if self.mismatch else
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
    with pytest.raises(RuntimeError, match="DELETION_UNCONFIRMED"):
        run(cloud, NOW)
    assert not cloud.deleted
    assert cloud.persisted["credit_guard"]["admission_closed"]


def test_uncertain_delete_reconciles_absence_without_second_delete():
    cloud = Cloud(lose_delete_reply=True)
    with pytest.raises(RuntimeError, match="DELETION_UNCONFIRMED"):
        run(cloud, NOW)
    run(cloud, NOW)
    assert cloud.calls.count(("DELETE", "/instances/owned-control")) == 1


class InferenceCloud(Cloud):
    def __init__(self, *, wrong_label=False, lose_reply=False):
        super().__init__()
        self.state["resources"]["inference"] = "owned-subscription"
        self.wrong_label, self.lose_reply = wrong_label, lose_reply
        self.revoked = False

    def request(self, method, route):
        if not route.startswith("/inference/"):
            return super().request(method, route)
        self.calls.append((method, route))
        assert route == "/inference/owned-subscription"
        if method == "DELETE":
            assert self.persisted["credit_guard"]["admission_closed"]
            self.revoked = True
            if self.lose_reply:
                self.lose_reply = False
                raise RuntimeError("CONNECTION_LOST")
            return {}
        if self.revoked:
            raise RuntimeError("VULTR_HTTP_404")
        return {"subscription": {"id": "owned-subscription", "label": "unrelated"
                                 if self.wrong_label else "proofflow-phase1-inference"}}


def test_guard_revokes_exact_subscription_before_compute_and_reads_absence():
    cloud = InferenceCloud()
    run(cloud, NOW)
    assert cloud.revoked and cloud.persisted["credit_guard"]["inference_revoked"]
    assert cloud.calls.index(("DELETE", "/inference/owned-subscription")) < cloud.calls.index(
        ("DELETE", "/instances/owned-control"))


def test_guard_refuses_changed_subscription():
    cloud = InferenceCloud(wrong_label=True)
    with pytest.raises(RuntimeError, match="DELETION_UNCONFIRMED"):
        run(cloud, NOW)
    assert not cloud.revoked


def test_guard_reconciles_lost_subscription_delete_without_replay():
    cloud = InferenceCloud(lose_reply=True)
    with pytest.raises(RuntimeError, match="DELETION_UNCONFIRMED"):
        run(cloud, NOW)
    run(cloud, NOW)
    assert cloud.calls.count(("DELETE", "/inference/owned-subscription")) == 1
    assert cloud.deleted == {"control", "worker"}


def test_missing_account_response_closes_admission_but_still_stops_owned_resources():
    cloud = Cloud()
    request = cloud.request
    def fail_account(method, route):
        if route == "/account":
            raise RuntimeError("ACCOUNT_ENDPOINT_UNAVAILABLE")
        return request(method, route)
    cloud.request = fail_account
    assert run(cloud, NOW)["reason"] == "ACCOUNTING_UNAVAILABLE"
    assert cloud.deleted == {"control", "worker"}


def test_subscription_failure_does_not_leave_known_compute_running():
    cloud = InferenceCloud(wrong_label=True)
    with pytest.raises(RuntimeError, match="DELETION_UNCONFIRMED"):
        run(cloud, NOW)
    assert cloud.deleted == {"control", "worker"}
    assert not cloud.revoked
    assert cloud.persisted["credit_guard"]["pending_resource_roles"] == ["inference"]
