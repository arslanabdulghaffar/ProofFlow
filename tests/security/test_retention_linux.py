"""Real Linux descriptor/lock/restore/crash checks; no fixture program is executed."""

import json
import os
import sys
from pathlib import Path
from uuid import uuid4

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux flock/descriptor boundary")


@pytest.fixture
def tree(tmp_path):
    from orchestrator.retention import retire

    assets, jobs = tmp_path / "assets", tmp_path / "jobs"
    assets.mkdir(mode=0o700)
    jobs.mkdir(mode=0o700)
    workspace, job, execution = uuid4(), uuid4(), uuid4()
    directory = assets / workspace.hex
    directory.mkdir(mode=0o700)
    (directory / ("a" * 64)).write_bytes(b"synthetic CSV")
    os.chmod(directory / ("a" * 64), 0o400)
    run = jobs / execution.hex
    run.mkdir(mode=0o700)
    (run / "intent.json").write_text(json.dumps({"job": job.hex}))
    (run / "pipeline.py.txt").write_bytes(b"# inert source, never executed")
    plan = {"workspace": str(workspace), "jobs": [str(job)], "manifest_sha256": "b" * 64}
    return retire, assets, jobs, directory, run, plan


def test_retirement_is_idempotent_and_prevents_restored_reads_and_writes(tree):
    from api.app.product_store import ProductFailure
    from api.app.workspace_assets import WorkspaceAssets

    retire, assets, jobs, directory, run, plan = tree
    assert retire(plan, assets, jobs)["bytes_removed"]
    assert not directory.exists() and not run.exists()
    assert retire(plan, assets, jobs)["bytes_removed"]
    directory.mkdir(mode=0o700)  # Simulated old byte restore cannot resurrect authority.
    (directory / ("a" * 64)).write_bytes(b"restored")
    fd = os.open(assets, os.O_RDONLY | os.O_DIRECTORY)
    try:
        from uuid import UUID

        store = WorkspaceAssets(fd)
        with pytest.raises(ProductFailure, match="ACCESS_DENIED"):
            store.read(UUID(plan["workspace"]), "a" * 64)
        with pytest.raises(ProductFailure, match="ACCESS_DENIED"):
            store.put(UUID(plan["workspace"]), b"new")
    finally:
        os.close(fd)


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "fifo"])
def test_retirement_refuses_unsafe_nodes_and_preserves_external_targets(tree, kind, tmp_path):
    from orchestrator.retention import RetentionError

    retire, assets, jobs, directory, _, plan = tree
    outside = tmp_path / "outside"
    outside.write_bytes(b"preserve")
    bad = directory / "unsafe"
    if kind == "symlink":
        bad.symlink_to(outside)
    elif kind == "hardlink":
        os.link(outside, bad)
    else:
        os.mkfifo(bad)
    with pytest.raises((RetentionError, OSError)):
        retire(plan, assets, jobs)
    assert outside.read_bytes() == b"preserve" and directory.exists()


@pytest.mark.parametrize("which", ["assets", "jobs"])
def test_retirement_waits_for_live_asset_or_journal_lease(tree, which):
    import fcntl

    retire, assets, jobs, directory, run, plan = tree
    fd = os.open(assets if which == "assets" else jobs, os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(fd, fcntl.LOCK_SH)
        with pytest.raises(BlockingIOError):
            retire(plan, assets, jobs)
        assert directory.exists() and run.exists()
    finally:
        os.close(fd)
    assert retire(plan, assets, jobs)["bytes_removed"]


def test_crashed_partial_journal_retirement_resumes_from_bound_directory(tree, monkeypatch):
    import orchestrator.retention as module

    retire, assets, jobs, directory, run, plan = tree
    original = module.empty_tree

    def interrupted(fd):
        names = os.listdir(fd)
        os.unlink(names[0], dir_fd=fd)
        raise OSError("synthetic interruption")

    monkeypatch.setattr(module, "empty_tree", interrupted)
    with pytest.raises(OSError):
        retire(plan, assets, jobs)
    assert not run.exists() and any(n.name.startswith(".retiring-") for n in jobs.iterdir())
    monkeypatch.setattr(module, "empty_tree", original)
    assert retire(plan, assets, jobs)["bytes_removed"]
    assert not directory.exists() and not any(
        n.name.startswith(".retiring-") for n in jobs.iterdir()
    )


def test_other_job_and_workspace_are_never_removed(tree):
    retire, assets, jobs, _, _, plan = tree
    other = jobs / uuid4().hex
    other.mkdir(mode=0o700)
    (other / "intent.json").write_text(json.dumps({"job": uuid4().hex}))
    outside = assets / uuid4().hex
    outside.mkdir(mode=0o700)
    assert retire(plan, assets, jobs)["bytes_removed"]
    assert other.is_dir() and outside.is_dir()


def test_deleted_job_cannot_resume_even_after_old_journal_restore(tree):
    from uuid import UUID

    from orchestrator.verification_run import VerificationRun
    from worker.protocol import SupervisorError

    retire, assets, jobs, _, _, plan = tree
    retire(plan, assets, jobs)
    runner = VerificationRun(None, Path("/unused"), "b" * 64, jobs)
    with pytest.raises(SupervisorError, match="VERIFICATION_JOB_DELETED"):
        runner.execute(
            execution=uuid4(),
            job=UUID(plan["jobs"][0]),
            generation=1,
            pipeline=b"# never executed",
            contract=b"{}",
            transactions=b"",
            customers=b"",
            purpose="original",
        )
