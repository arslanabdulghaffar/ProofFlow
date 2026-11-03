"""Verify a locally built immutable filesystem as data only. Never executes its files."""

import argparse
import errno
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from worker.host import command  # noqa: E402
from worker.protocol import SupervisorError  # noqa: E402
from worker.rootfs import mount_image, validate_import, verify_mount  # noqa: E402
from worker.staging import mount_inventory  # noqa: E402


def main(directory):
    assert directory.parent == Path("/var/tmp")  # noqa: S108 - explicit private build fixture
    assert directory.name.startswith("proofflow-rootfs-")
    assert directory.resolve() == directory and os.geteuid() == 0
    receipt = json.loads((directory / "import.json").read_text())
    image, blob = receipt["docker_image_sha256"], receipt["rootfs_sha256"]
    target = directory / "rootfs"
    checks = []
    validate_import(directory, image, blob)
    try:
        validate_import(directory, image, "0" * 64)
    except SupervisorError:
        pass
    else:
        raise AssertionError("Wrong release pin accepted")
    # Tamper and restore only our new unmounted build artifact; no user files.
    with (directory / "rootfs.squashfs").open("r+b") as file:
        original = file.read(1)
        try:
            file.seek(0)
            file.write(bytes([original[0] ^ 1]))
            file.flush()
            os.fsync(file.fileno())
            try:
                validate_import(directory, image, blob)
            except SupervisorError:
                pass
            else:
                raise AssertionError("Modified filesystem accepted")
        finally:
            file.seek(0)
            file.write(original)
            file.flush()
            os.fsync(file.fileno())
    checks.append("wrong_release_pin_and_modified_blob_rejected")
    try:
        mount_image(directory, image, blob)
        verify_mount(directory, image, blob)
        checks.append("real_readonly_squashfs_loop_backing_identity_verified")
        try:
            (target / "proofflow-write-probe").write_bytes(b"inert fixture")
        except OSError as error:
            assert error.errno == errno.EROFS
        else:
            raise AssertionError("Root filesystem was writable")
        # Read known trusted bootstrap bytes only, never import or execute them.
        imported = target / "opt/proofflow/launcher.py"
        expected = Path(__file__).resolve().parents[2] / "worker/launcher.py"
        assert hashlib.sha256(imported.read_bytes()).digest() == hashlib.sha256(
            expected.read_bytes()).digest()
        checks.append("host_write_denied_and_bootstrap_bytes_match_without_execution")
    finally:
        if str(target) in mount_inventory():
            command(["/usr/bin/umount", str(target)])
        assert str(target) not in mount_inventory()
        assert not command(["/usr/sbin/losetup", "-j", str(directory / "rootfs.squashfs")]).strip()
    print(json.dumps({"scope": "local_image_import_and_mount_only_no_image_execution",
                      "checks": checks, "import": receipt,
                      "cleanup": "mount_and_loop_absent_build_artifact_retained_private"}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    main(parser.parse_args().directory)
