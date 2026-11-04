"""Local confirmation tests: no input automation, account access or external writes."""

from datetime import UTC, datetime
from pathlib import Path

import pytest


@pytest.mark.parametrize("answer", ["", "yes", "APPROVE", "APPROVE " + "b" * 64, "exact"])
def test_local_confirmation_requires_the_displayed_full_digest(monkeypatch, answer):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    from scripts.approve_phase4_pr_locally import confirm_exact

    record = {"pr": {"preview_sha256": "a" * 64, "expires_at": "2030-01-01T00:10:00+00:00"}}
    now = lambda: datetime(2030, 1, 1, tzinfo=UTC)  # noqa: E731
    if answer == "exact":
        assert confirm_exact(record, lambda _: "APPROVE " + "a" * 64, now) == "a" * 64
    else:
        with pytest.raises(RuntimeError, match="APPROVAL_CANCELLED_NO_WRITE"):
            confirm_exact(record, lambda _: answer, now)


def test_expiry_is_checked_again_after_human_input(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    from scripts.approve_phase4_pr_locally import confirm_exact

    record = {"pr": {"preview_sha256": "a" * 64, "expires_at": "2030-01-01T00:10:00+00:00"}}
    ticks = iter([datetime(2030, 1, 1, tzinfo=UTC), datetime(2030, 1, 1, 0, 10, tzinfo=UTC)])
    with pytest.raises(RuntimeError, match="PREVIEW_EXPIRED_NO_WRITE"):
        confirm_exact(record, lambda _: "APPROVE " + "a" * 64, lambda: next(ticks))


def test_redirected_input_cannot_prepare_or_approve(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    from scripts import approve_phase4_pr_locally as local

    monkeypatch.setattr(local.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(local, "prepare", lambda *a, **k: pytest.fail("Unexpected preparation"))
    with pytest.raises(RuntimeError, match="INTERACTIVE_TERMINAL_REQUIRED_NO_ACTION"):
        local.main()
