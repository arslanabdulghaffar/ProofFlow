"""Real local files/locks only; no candidate code, provider or ledger calls."""

import asyncio
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Linux private journal/locks")


def setup(tmp_path):
    from eval.comparison_journal import ComparisonJournal, initialize
    from orchestrator.probe_plan import RateQuote
    from orchestrator.repair_provider import prepare_repair_plan

    jobs = {str(uuid4()): arm for arm in ("B", "C") for _ in range(24)}
    campaign = "a" * 64
    root = tmp_path / "journal"
    initialize(root, campaign, jobs)
    now = datetime.now(UTC)
    quote = RateQuote("qwen3.8-flash-next", 100000, 200000, now, now + timedelta(hours=1), "b" * 64)
    plan = prepare_repair_plan("synthetic inert prompt", quote, now)
    journal = ComparisonJournal(root, next(iter(jobs)), campaign)
    return journal, plan, jobs


def test_prepare_reopen_exact_receipt_unknown_retained_and_recovery(tmp_path):
    from eval.comparison_journal import ComparisonJournal, ComparisonJournalError
    from orchestrator.probe_journal import recover_response

    journal, plan, jobs = setup(tmp_path)
    request = uuid4()
    assert asyncio.run(journal.prepare(request, plan)) is True
    assert asyncio.run(journal.snapshot(request))["state"] == "PREPARED"
    reopened = ComparisonJournal(journal.root, journal.job, journal.campaign)
    assert asyncio.run(reopened.prepare(request, plan)) is False
    with pytest.raises(ComparisonJournalError):
        asyncio.run(reopened.prepare(request, replace(plan, payload=b"changed")))
    foreign = ComparisonJournal(journal.root, list(jobs)[1], journal.campaign)
    with pytest.raises(ComparisonJournalError):
        asyncio.run(foreign.snapshot(request))
    with pytest.raises(ComparisonJournalError):
        asyncio.run(foreign.prepare(request, plan))
    body = json.dumps(
        {
            "id": "chatcmpl-synthetic",
            "object": "chat.completion",
            "model": "qwen3.8-flash-next",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": '{"ok":true}'},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10},
        }
    ).encode()
    assert asyncio.run(journal.record(request, plan, "PARSED_RESPONSE", body, 200, 10))
    assert not asyncio.run(journal.record(request, plan, "PARSED_RESPONSE", body, 200, 10))
    snapshot = asyncio.run(reopened.snapshot(request))
    parsed = recover_response(snapshot, request, plan)
    assert parsed.response_sha256 == hashlib.sha256(body).hexdigest()
    with pytest.raises(ComparisonJournalError):
        asyncio.run(journal.record(request, plan, "OUTCOME_UNKNOWN", None, None, 11))
    assert not asyncio.run(journal.prepare(request, plan))


def test_three_calls_and_independent_per_job_money_bound(tmp_path):
    from eval.comparison_journal import ComparisonJournal, ComparisonJournalError

    journal, plan, jobs = setup(tmp_path)
    for _ in range(3):
        assert asyncio.run(journal.prepare(uuid4(), plan))
    with pytest.raises(ComparisonJournalError):
        asyncio.run(journal.prepare(uuid4(), plan))
    second = ComparisonJournal(journal.root, list(jobs)[1], journal.campaign)
    large = replace(plan, reserve_micro_usd=50001)
    assert asyncio.run(second.prepare(uuid4(), large))
    with pytest.raises(ComparisonJournalError):
        asyncio.run(second.prepare(uuid4(), large))
    assert len(list(journal.root.glob("request-*"))) == 4


def test_full_declared_campaign_capacity_and_total_envelope(tmp_path):
    from eval.comparison_journal import ComparisonJournal, ComparisonJournalError

    journal, plan, jobs = setup(tmp_path)
    high = replace(plan, reserve_micro_usd=100000)
    for job in jobs:
        lane = ComparisonJournal(journal.root, job, journal.campaign)
        assert asyncio.run(lane.prepare(uuid4(), high))
    assert (
        sum(json.loads(p.read_bytes())["reserve_micro_usd"] for p in journal.root.glob("request-*"))
        == 4800000
    )
    with pytest.raises(ComparisonJournalError):
        asyncio.run(journal.prepare(uuid4(), plan))
    foreign = ComparisonJournal(journal.root, str(uuid4()), journal.campaign)
    with pytest.raises(ComparisonJournalError):
        asyncio.run(foreign.prepare(uuid4(), plan))


def test_concurrent_calls_never_exceed_one_job_envelope(tmp_path):
    from eval.comparison_journal import ComparisonJournalError

    journal, plan, _ = setup(tmp_path)

    def attempt(_):
        try:
            return asyncio.run(journal.prepare(uuid4(), plan))
        except (BlockingIOError, ComparisonJournalError):
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        accepted = list(pool.map(attempt, range(16)))
    assert 1 <= sum(accepted) <= 3
    assert len(list(journal.root.glob("request-*"))) == sum(accepted)


@pytest.mark.parametrize(
    "fault", ["symlink", "hardlink", "fifo", "mode", "campaign", "orphan", "extra"]
)
def test_unsafe_storage_cannot_admit_a_call(tmp_path, fault):
    from eval.comparison_journal import ComparisonJournalError

    journal, plan, _ = setup(tmp_path)
    target = journal.root / ("response-" + uuid4().hex + ".json")
    if fault == "symlink":
        target.symlink_to(journal.root / "plan.json")
    elif fault == "hardlink":
        os.link(journal.root / "plan.json", target)
    elif fault == "fifo":
        os.mkfifo(target, 0o600)
    elif fault == "mode":
        (journal.root / "plan.json").chmod(0o644)
    elif fault == "campaign":
        journal.campaign = "c" * 64
    else:
        if fault == "extra":
            target = journal.root / "unknown-file"
        target.write_bytes(b"{}")
        target.chmod(0o600)
    with pytest.raises(ComparisonJournalError):
        asyncio.run(journal.prepare(uuid4(), plan))
    assert not list(journal.root.glob("request-*"))


def test_failed_fsync_holds_request_and_never_grants_retry(tmp_path, monkeypatch):
    from eval import comparison_journal as module

    journal, plan, _ = setup(tmp_path)
    request = uuid4()
    with monkeypatch.context() as patch:
        patch.setattr(module.os, "fsync", lambda _: (_ for _ in ()).throw(OSError("fixture")))
        with pytest.raises(OSError):
            asyncio.run(journal.prepare(request, plan))
    assert not asyncio.run(journal.prepare(request, plan))
    assert asyncio.run(journal.snapshot(request))["state"] == "PREPARED"


def test_partial_or_foreign_initialization_is_never_overwritten(tmp_path):
    from eval.comparison_journal import ComparisonJournalError, initialize

    journal, _, jobs = setup(tmp_path)
    with pytest.raises(FileExistsError):
        initialize(journal.root, journal.campaign, jobs)
    with pytest.raises(ComparisonJournalError):
        initialize(tmp_path / "other", journal.campaign, dict(list(jobs.items())[:-1]))
    assert not (tmp_path / "other").exists()


def test_global_budget_denial_remains_required_and_same_request_cannot_retry(tmp_path):
    from orchestrator.probe_plan import RateQuote
    from orchestrator.vultr_probe import ProbeDispatchError, _run_prepared

    journal, plan, _ = setup(tmp_path)
    now = datetime.now(UTC)
    quote = RateQuote("qwen3.8-flash-next", 100000, 200000, now, now + timedelta(hours=1), "b" * 64)

    class DeniedBudget:
        attempts = 0

        async def reserve(self, *_):
            self.attempts += 1
            raise OSError("synthetic global admission failure")

        async def claim(self, *_):
            raise AssertionError("claim must not follow failed reserve")

    budget, request = DeniedBudget(), uuid4()
    args = {
        "budget": budget,
        "request_id": request,
        "plan": plan,
        "quote": quote,
        "max_completion_tokens": 8192,
        "api_key": "synthetic-fixture",
        "journal": journal,
    }
    with pytest.raises(ProbeDispatchError, match="PROVIDER_OUTCOME_UNCERTAIN"):
        asyncio.run(_run_prepared(**args))
    stored = asyncio.run(journal.snapshot(request))
    assert stored["state"] == "RECORDED" and stored["outcome"] == "OUTCOME_UNKNOWN"
    assert stored["response_base64"] is None
    with pytest.raises(ProbeDispatchError, match="PROBE_ALREADY_RECORDED"):
        asyncio.run(_run_prepared(**args))
    assert budget.attempts == 1
