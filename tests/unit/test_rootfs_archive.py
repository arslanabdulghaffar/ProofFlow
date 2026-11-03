"""Inspect inert tar bytes only. Never extract or execute archive contents."""

import io
import tarfile

import pytest

from worker.protocol import SupervisorError
from worker.rootfs import inspect_tar


@pytest.mark.parametrize("fault", ["absolute", "parent", "symlink_parent", "fifo", "setuid",
                                  "duplicate", "hardlink_missing"])
def test_image_archive_rejects_unsafe_structure(tmp_path, fault):
    path = tmp_path / "fixture.tar"
    with tarfile.open(path, "w") as archive:
        name = {"absolute": "/outside", "parent": "../outside"}.get(fault, "entry")
        member = tarfile.TarInfo(name)
        if fault == "fifo":
            member.type = tarfile.FIFOTYPE
        elif fault == "setuid":
            member.mode = 0o4755
        elif fault in ("symlink_parent", "hardlink_missing"):
            member.type = tarfile.SYMTYPE if fault == "symlink_parent" else tarfile.LNKTYPE
            member.linkname = "outside"
        archive.addfile(member, io.BytesIO(b""))
        if fault == "symlink_parent":
            archive.addfile(tarfile.TarInfo("entry/child"), io.BytesIO(b""))
        elif fault == "duplicate":
            archive.addfile(member, io.BytesIO(b""))
    with pytest.raises(SupervisorError):
        inspect_tar(path)


def test_guest_symlink_and_non_privilege_directory_mode_are_not_extracted(tmp_path):
    path = tmp_path / "fixture.tar"
    with tarfile.open(path, "w") as archive:
        member = tarfile.TarInfo("bin")
        member.type, member.linkname = tarfile.SYMTYPE, "/usr/bin"
        archive.addfile(member)
        member = tarfile.TarInfo("mail")
        member.type, member.mode = tarfile.DIRTYPE, 0o2775
        archive.addfile(member)
    assert inspect_tar(path)["entries"] == 2
    assert not (tmp_path / "bin").exists()
