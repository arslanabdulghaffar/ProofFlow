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


def test_diagnostics_expose_only_fixed_codes(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    from scripts.approve_phase4_pr_locally import safe_failure

    code = "PREVIEW_STOPPED_PREFLIGHT_WORKSPACE_EXPIRED_OR_UNAVAILABLE"
    assert safe_failure(RuntimeError(code)) == code
    for value in ("secret body", code + " secret", "PREVIEW_STOPPED_EVIL_secret"):
        assert safe_failure(RuntimeError(value)) == (
            "LOCAL_APPROVAL_STOPPED_RECONCILE_SAVED_EVIDENCE"
        )


def test_expired_workspace_stops_before_session_or_preview(monkeypatch, tmp_path):
    import json
    from types import SimpleNamespace

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    from scripts import refresh_phase4_pr_preview as refresh

    evidence = tmp_path / "evidence"
    evidence.mkdir()
    source = evidence / "source.json"
    source.write_text(json.dumps({
        "workspace": "1c7529c0-b6c4-4f83-919a-d10942dce4ff",
        "version": "ad9e5f6b-46ff-4366-b153-6e0a269d798d",
        "candidate_sha256": "a" * 64, "status": "ready",
    }))
    monkeypatch.setattr(refresh, "PRIVATE", tmp_path)
    monkeypatch.setattr(refresh, "SOURCE", source)
    queries = []

    class Live:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def sql(self, statement, *args):
            queries.append(statement)
            if "bool_and(blocked)" in statement:
                return b"t"
            return b"0" if "pr_writes" in statement else b"f"

        def login(self, *_):
            pytest.fail("Expired workspace must not create a session")

    monkeypatch.setattr(refresh, "LiveSession", Live)
    path = evidence / "attempt.json"
    with pytest.raises(RuntimeError, match="PREFLIGHT_WORKSPACE_EXPIRED_OR_UNAVAILABLE"):
        refresh.main(path, emit=False)
    saved = json.loads(path.read_bytes())
    assert saved["preparation_stage"] == "preflight"
    assert saved["preparation_failure"] == "WORKSPACE_EXPIRED_OR_UNAVAILABLE"
    assert saved["external_approval"] is False
    assert all(q.startswith("SELECT") for q in queries)
    assert "41 minutes" in queries[-1]
    # Unclassified native failure is redacted both on disk and in the raised error.
    monkeypatch.setattr(refresh, "LiveSession", lambda: SimpleNamespace())
    path2 = evidence / "second.json"
    with pytest.raises(RuntimeError, match="CONNECT_UNCLASSIFIED_PREPARATION_FAILURE"):
        refresh.main(path2, emit=False)
    assert json.loads(path2.read_bytes())["preparation_failure"] == (
        "UNCLASSIFIED_PREPARATION_FAILURE"
    )
    before = path.read_bytes()
    with pytest.raises(RuntimeError, match="RECONCILE_EXISTING_REFRESH_RECORD"):
        refresh.main(path, emit=False)
    assert path.read_bytes() == before


def test_live_proof_waits_through_all_original_running_states(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    from scripts import prepare_phase4_pr_workspace as fresh

    states = iter(["QUEUED", "BASELINE_RUNNING", "BASELINE_VERIFYING", "RECONCILING",
                   "NEEDS_REVIEW"])
    sleeps = []
    client = SimpleNamespace(get=lambda _: SimpleNamespace(
        status_code=200, json=lambda: {"state": next(states)},
    ))
    monkeypatch.setattr(fresh.time, "sleep", sleeps.append)
    assert fresh.wait_terminal(client, "/v1/jobs/fixture", {
        "NEEDS_REVIEW", "FAILED_INFRA", "CANCELLED",
    })["state"] == "NEEDS_REVIEW"
    assert sleeps == [1, 1, 1, 1]
