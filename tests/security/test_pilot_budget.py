"""Local Linux reservation fault tests; fake downstream journal, no provider calls."""

import json
import sys
from types import SimpleNamespace
from uuid import uuid4

import pytest

from eval.pilot_budget import PilotJournal, PilotLimit

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux private journal")


def setup(tmp_path):
    tmp_path.chmod(0o700)
    jobs = [str(uuid4()) for _ in range(12)]
    (tmp_path / "plan.json").write_text(json.dumps({"jobs": jobs}))
    (tmp_path / "plan.json").chmod(0o600)
    return jobs


def test_unknown_calls_stay_reserved_and_replay_cannot_send(tmp_path):
    jobs = setup(tmp_path)
    plan = SimpleNamespace(request_sha256="a" * 64, reserve_micro_usd=27853)
    journal = PilotJournal(tmp_path, jobs[0], None)
    request = uuid4()
    assert journal.hold(request, plan)
    assert not PilotJournal(tmp_path, jobs[0], None).hold(request, plan)
    assert journal.hold(uuid4(), plan) and journal.hold(uuid4(), plan)
    with pytest.raises(PilotLimit, match="BUDGET_EXHAUSTED"):
        journal.hold(uuid4(), plan)
    with pytest.raises(PilotLimit, match="CONFLICT"):
        PilotJournal(tmp_path, jobs[1], None).hold(request, plan)


def test_job_cap_unsafe_receipt_and_unknown_job_fail_closed(tmp_path):
    jobs = setup(tmp_path)
    journal = PilotJournal(tmp_path, jobs[0], None)
    plan = SimpleNamespace(request_sha256="b" * 64, reserve_micro_usd=60000)
    assert journal.hold(uuid4(), plan)
    with pytest.raises(PilotLimit, match="BUDGET_EXHAUSTED"):
        journal.hold(uuid4(), plan)
    with pytest.raises(PilotLimit, match="NOT_DECLARED"):
        PilotJournal(tmp_path, str(uuid4()), None).hold(uuid4(), plan)
    target = tmp_path / "unsafe.json"
    target.write_text('{}')
    (tmp_path / ("call-" + uuid4().hex + ".json")).symlink_to(target)
    with pytest.raises(OSError):
        PilotJournal(tmp_path, jobs[1], None).hold(uuid4(), plan)
