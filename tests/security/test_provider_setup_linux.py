"""Trusted disposable credential-file fixtures; never real provider credentials."""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator.provider_setup import SetupError, load_provider_secrets

FIXTURE = "synthetic-not-a-provider-key-" * 2


@unittest.skipUnless(sys.platform == "linux", "Linux descriptor policy")
class ProviderSetupTests(unittest.TestCase):
    def setUp(self):
        # /run has trusted ancestors; /tmp's writable ancestor is unacceptable.
        self.path = Path(tempfile.mkdtemp(prefix="proofflow-secret-test-", dir="/run"))
        for name in ("budget-password", "vultr-api-key"):
            file = self.path / name
            file.write_text(FIXTURE + "\n", encoding="ascii")
            file.chmod(0o600)

    def tearDown(self):
        assert self.path.resolve().parent == Path("/run")
        assert self.path.name.startswith("proofflow-secret-test-") and not self.path.is_symlink()
        shutil.rmtree(self.path)

    def test_load_redaction_and_no_descriptor_leak(self):
        before = len(os.listdir("/proc/self/fd"))
        result = load_provider_secrets(str(self.path))
        assert result.database_password == FIXTURE and result.vultr_api_key == FIXTURE
        assert FIXTURE not in repr(result)
        assert len(os.listdir("/proc/self/fd")) == before

    def test_unsafe_files(self):
        for kind in ("symlink", "hardlink", "fifo", "directory", "permissions", "oversized",
                     "nonascii", "nul", "missing", "owner"):
            with self.subTest(kind=kind):
                file = self.path / "vultr-api-key"
                if file.exists() or file.is_symlink():
                    file.unlink()
                if kind == "symlink":
                    file.symlink_to(self.path / "budget-password")
                elif kind == "hardlink":
                    os.link(self.path / "budget-password", file)
                elif kind == "fifo":
                    os.mkfifo(file, 0o600)
                elif kind == "directory":
                    file.mkdir(mode=0o700)
                elif kind != "missing":
                    file.write_bytes({"oversized": b"x" * 514, "nonascii": b"\xff" * 40,
                                      "nul": b"x" * 40 + b"\x00"}.get(kind, FIXTURE.encode()))
                    file.chmod(0o640 if kind == "permissions" else 0o600)
                    if kind == "owner":
                        os.chown(file, 65534, 65534)
                before = len(os.listdir("/proc/self/fd"))
                with self.assertRaises(SetupError) as rejected:
                    load_provider_secrets(str(self.path))
                assert str(self.path) not in str(rejected.exception)
                assert FIXTURE not in str(rejected.exception)
                assert len(os.listdir("/proc/self/fd")) == before
                if kind == "directory":
                    file.rmdir()

    def test_writable_secret_directory(self):
        for mode in (0o770, 0o777):
            self.path.chmod(mode)
            with self.assertRaisesRegex(SetupError, "SECRET_DIRECTORY_UNSAFE"):
                load_provider_secrets(str(self.path))

    def test_symlink_directory_and_writable_ancestor(self):
        alias = self.path / "alias"
        alias.symlink_to(self.path, target_is_directory=True)
        with self.assertRaises(SetupError):
            load_provider_secrets(str(alias))
        with self.assertRaisesRegex(SetupError, "SECRET_DIRECTORY_UNSAFE"):
            load_provider_secrets("/tmp/anything")  # noqa: S108 - rejected attack fixture

    def test_file_changed_during_read(self):
        original = os.read

        def tamper(fd, count):
            raw = original(fd, count)
            (self.path / "budget-password").write_text("x" * 64, encoding="ascii")
            return raw

        with patch("os.read", side_effect=tamper):
            with self.assertRaisesRegex(SetupError, "SECRET_FILE_CHANGED"):
                load_provider_secrets(str(self.path))


if __name__ == "__main__":
    unittest.main()
