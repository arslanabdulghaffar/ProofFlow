"""Visible-browser startup must precede remote admission or credential access."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import guest_demo  # noqa: E402
import playwright.sync_api  # noqa: E402


class PlaywrightFixture:
    def __init__(self, chromium):
        self.chromium = chromium

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


def test_missing_visible_executable_never_prepares_guest(tmp_path, monkeypatch):
    def missing(**_):
        raise playwright.sync_api.Error("fixture installed browser unavailable")

    chromium = SimpleNamespace(executable_path=str(tmp_path / "missing-chrome.exe"), launch=missing)
    monkeypatch.setattr(playwright.sync_api, "sync_playwright", lambda: PlaywrightFixture(chromium))

    def forbidden():
        pytest.fail("Remote guest preparation must not run before browser preflight")

    monkeypatch.setattr(guest_demo, "prepare_guest_access", forbidden)
    with pytest.raises(
        RuntimeError, match="Visible (Chromium is missing|Microsoft Edge could not start)"
    ):
        guest_demo.open_browser()


def test_launched_browser_is_closed_if_guest_preparation_fails(tmp_path, monkeypatch):
    executable = tmp_path / "fixture-not-executed.exe"
    executable.write_text("inert fixture")
    closed = []
    browser = SimpleNamespace(close=lambda: closed.append(True))

    def launch(*, headless, channel=None):
        assert headless is False
        assert channel == ("msedge" if sys.platform == "win32" else None)
        return browser

    chromium = SimpleNamespace(executable_path=str(executable), launch=launch)
    monkeypatch.setattr(playwright.sync_api, "sync_playwright", lambda: PlaywrightFixture(chromium))

    def failure():
        raise RuntimeError("fixture admission refusal")

    monkeypatch.setattr(guest_demo, "prepare_guest_access", failure)
    with pytest.raises(RuntimeError, match="fixture admission refusal"):
        guest_demo.open_browser()
    assert closed == [True]
