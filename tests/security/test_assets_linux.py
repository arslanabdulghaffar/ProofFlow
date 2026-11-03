"""Trusted Linux storage fixtures only. No candidate executes on this host."""

import hashlib
import os
import stat
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from api.app.assets import AssetError, put_asset, read_asset


@unittest.skipUnless(sys.platform == "linux", "real Linux descriptor/flock semantics required")
class AssetStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="proofflow-asset-test-")
        self.root = Path(self.temp.name)
        self.fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)

    def tearDown(self):
        os.close(self.fd)
        self.temp.cleanup()

    def test_durable_exact_roundtrip_empty_and_idempotent(self):
        for content in (b"", b"synthetic\x00bytes", b"x" * 131073):
            digest = put_asset(self.fd, content)
            self.assertEqual(digest, hashlib.sha256(content).hexdigest())
            self.assertEqual(read_asset(self.fd, digest), content)
            inode = (self.root / digest).stat().st_ino
            self.assertEqual(put_asset(self.fd, content), digest)
            self.assertEqual((self.root / digest).stat().st_ino, inode)
            self.assertEqual(stat.S_IMODE((self.root / digest).stat().st_mode), 0o400)
        self.assertFalse(list(self.root.glob(".pending-*")))

    def test_directory_permissions_paths_and_size_are_rejected(self):
        for digest in ("../x", "a" * 63, "A" * 64, True):
            with self.assertRaisesRegex(AssetError, "ASSET_DIGEST_INVALID"):
                read_asset(self.fd, digest)
        with self.assertRaisesRegex(AssetError, "ASSET_BYTE_LIMIT"):
            put_asset(self.fd, b"x" * (10 * 1024 * 1024 + 1))
        os.chmod(self.root, 0o750)  # noqa: S103 - deliberately unsafe fixture must be rejected
        with self.assertRaisesRegex(AssetError, "ASSET_DIRECTORY_UNSAFE"):
            put_asset(self.fd, b"x")

    def test_symlink_fifo_directory_and_hardlink_never_read(self):
        digest = hashlib.sha256(b"x").hexdigest()
        path = self.root / digest
        target = self.root / "fixture"
        target.write_bytes(b"x")
        target.chmod(0o400)
        for kind in ("symlink", "fifo", "directory", "hardlink"):
            if kind == "symlink":
                path.symlink_to(target)
            elif kind == "fifo":
                os.mkfifo(path, 0o400)
            elif kind == "directory":
                path.mkdir(mode=0o400)
            else:
                os.link(target, path)
            with self.assertRaisesRegex(AssetError, "ASSET_OBJECT_UNSAFE"):
                read_asset(self.fd, digest)
            with self.assertRaisesRegex(AssetError, "ASSET_OBJECT_UNSAFE"):
                put_asset(self.fd, b"x")
            if kind == "directory":
                path.rmdir()
            else:
                path.unlink()

    def test_corruption_is_not_trusted_by_filename_or_reuse(self):
        digest = put_asset(self.fd, b"correct")
        path = self.root / digest
        path.chmod(0o600)
        path.write_bytes(b"corrupt")
        path.chmod(0o400)
        for operation in (lambda: read_asset(self.fd, digest),
                          lambda: put_asset(self.fd, b"correct")):
            with self.assertRaisesRegex(AssetError, "ASSET_DIGEST_MISMATCH"):
                operation()
        self.assertEqual(path.read_bytes(), b"corrupt")

    def test_short_writes_complete_and_failure_has_no_returned_digest(self):
        real_write = os.write
        with patch("api.app.assets.os.write",
                   side_effect=lambda fd, value: real_write(fd, value[:3])):
            digest = put_asset(self.fd, b"longer than three bytes")
        self.assertEqual(read_asset(self.fd, digest), b"longer than three bytes")
        with patch("api.app.assets.os.write", side_effect=OSError("private native detail")):
            with self.assertRaisesRegex(AssetError, "^ASSET_IO_FAILED$"):
                put_asset(self.fd, b"new")
        self.assertFalse(list(self.root.glob(".pending-*")))

    def test_fsync_failure_before_publication_leaves_no_blob(self):
        with patch("api.app.assets.os.fsync", side_effect=OSError("synthetic disk fault")):
            with self.assertRaisesRegex(AssetError, "ASSET_IO_FAILED"):
                put_asset(self.fd, b"new")
        self.assertEqual(list(self.root.iterdir()), [])

    def test_directory_sync_failure_cannot_claim_durability(self):
        original = os.fsync

        def fail_directory(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError("synthetic directory fault")
            original(fd)

        with patch("api.app.assets.os.fsync", side_effect=fail_directory):
            with self.assertRaisesRegex(AssetError, "ASSET_IO_FAILED"):
                put_asset(self.fd, b"new")
        # The orphan is acceptable; only a successful retry may reference it.
        digest = put_asset(self.fd, b"new")
        self.assertEqual(read_asset(self.fd, digest), b"new")

    def test_concurrent_reuse_is_serialized_and_keeps_one_inode(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: put_asset(self.fd, b"same" * 16384), range(24)))
        self.assertEqual(len(set(results)), 1)
        self.assertEqual(len(list(self.root.iterdir())), 1)
        self.assertEqual(read_asset(self.fd, results[0]), b"same" * 16384)


if __name__ == "__main__":
    unittest.main()
