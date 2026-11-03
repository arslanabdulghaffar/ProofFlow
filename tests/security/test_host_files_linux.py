"""Trusted inode/mode regression; no uploaded code or sandbox execution."""

import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

from worker.host import synced_write
from worker.protocol import SupervisorError


@unittest.skipUnless(sys.platform == "linux", "Linux descriptor permissions")
class HostFileTests(unittest.TestCase):
    def test_service_umask_does_not_make_guest_inputs_unreadable(self):
        old = os.umask(0o077)
        try:
            with tempfile.TemporaryDirectory() as temporary:
                source = Path(temporary) / "input.txt"
                secret = Path(temporary) / "private.txt"
                synced_write(source, b"inert fixture bytes", mode=0o444)
                synced_write(secret, b"private fixture bytes")
                self.assertEqual(stat.S_IMODE(source.stat().st_mode), 0o444)
                self.assertEqual(stat.S_IMODE(secret.stat().st_mode), 0o600)
                self.assertEqual(source.read_bytes(), b"inert fixture bytes")
                with self.assertRaises(FileExistsError):
                    synced_write(source, b"replacement", mode=0o444)
                self.assertEqual(source.read_bytes(), b"inert fixture bytes")
        finally:
            os.umask(old)

    def test_unreviewed_mode_is_rejected_before_creation(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "no-file"
            with self.assertRaisesRegex(SupervisorError, "UNAPPROVED_DURABLE_FILE_MODE"):
                synced_write(target, b"fixture", mode=0o777)
            self.assertFalse(target.exists())
