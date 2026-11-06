"""Linux marker expiry on idle private roots; no production paths or candidates."""

import os
import sys
import time
from uuid import uuid4

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux retention roots")


def roots(tmp_path):
    from orchestrator.retention import marker

    paths = [tmp_path / name for name in ("assets", "jobs")]
    for path in paths:
        path.mkdir(mode=0o700)
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            marker(fd, ".deleted-" + uuid4().hex)  # Legacy fixture markers.
        finally:
            os.close(fd)
    return paths


def test_markers_expire_only_after_seven_days_on_idle_roots(tmp_path, monkeypatch):
    from orchestrator.retention import prune_markers

    assets, jobs = roots(tmp_path)
    now = time.time()
    assert prune_markers(assets, jobs)["removed"] == 0
    monkeypatch.setattr("orchestrator.retention.time.time", lambda: now + 8 * 86400)
    assert prune_markers(assets, jobs) == {"removed": 2, "deferred": None}
    assert not list(assets.iterdir()) and not list(jobs.iterdir())


def test_raw_tree_defers_all_marker_pruning(tmp_path, monkeypatch):
    from orchestrator.retention import prune_markers

    assets, jobs = roots(tmp_path)
    (jobs / uuid4().hex).mkdir(mode=0o700)
    now = time.time()
    monkeypatch.setattr("orchestrator.retention.time.time", lambda: now + 8 * 86400)
    assert prune_markers(assets, jobs) == {"removed": 0, "deferred": "RAW_TREES_PRESENT"}
    assert len(list(assets.iterdir())) == 1


@pytest.mark.parametrize("change", ["content", "hardlink", "symlink"])
def test_unsafe_marker_is_never_followed_or_removed(tmp_path, monkeypatch, change):
    from orchestrator.retention import RetentionError, prune_markers

    assets, jobs = roots(tmp_path)
    target = next(assets.iterdir())
    if change == "content":
        target.chmod(0o600)
        target.write_bytes(b"changed\n")
        target.chmod(0o400)
    elif change == "hardlink":
        os.link(target, tmp_path / "outside")
    else:
        target.unlink()
        target.symlink_to(tmp_path / "missing")
    now = time.time()
    monkeypatch.setattr("orchestrator.retention.time.time", lambda: now + 8 * 86400)
    with pytest.raises(RetentionError, match="MARKER"):
        prune_markers(assets, jobs)
    assert target.exists() or target.is_symlink()
