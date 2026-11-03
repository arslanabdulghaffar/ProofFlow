"""Root-owned inert file fixtures, no real runtime install or guest execution."""

import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from worker import runtime_bundle
from worker.protocol import SupervisorError


@unittest.skipUnless(sys.platform == "linux", "Linux file ownership policy")
class BundleFilesTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="proofflow-bundle-test-", dir="/run"))
        self.binaries = self.root / "bin"
        self.binaries.mkdir()
        (self.binaries / "gvisor-bin").mkdir()
        manifest = json.loads(Path("infra/gvisor/runsc-release.json").read_text())
        for name in runtime_bundle.MEMBERS:
            raw = ("inert fixture " + name).encode()
            target = self.binaries / name
            target.write_bytes(raw)
            target.chmod(0o755)
            manifest["members"][name] = {
                "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
            }
        self.runsc = manifest["members"]["runsc"]["sha256"]
        self.manifest = self.root / "manifest.json"
        self.manifest.write_text(json.dumps(manifest))
        self.expected = hashlib.sha256(self.manifest.read_bytes()).hexdigest()
        self.mapping = patch.object(runtime_bundle, "Path", side_effect=lambda value: {
            "/etc/proofflow-worker/runtime.json": self.manifest,
            "/usr/local/bin": self.binaries,
        }[value])
        self.mapping.start()

    def tearDown(self):
        self.mapping.stop()
        assert self.root.resolve().parent == Path("/run")
        assert self.root.name.startswith("proofflow-bundle-test-")
        shutil.rmtree(self.root)

    def verify(self):
        runtime_bundle.validate_bundle(self.expected, self.runsc)

    def test_all_members_rechecked(self):
        self.verify()

    def test_changed_companion_rejected(self):
        (self.binaries / "gvisor-bin/gvisor_sentry").write_bytes(b"changed")
        with self.assertRaises(SupervisorError):
            self.verify()

    def test_unreviewed_companion_rejected(self):
        (self.binaries / "gvisor-bin/extra").write_bytes(b"inert")
        with self.assertRaisesRegex(SupervisorError, "UNEXPECTED_RUNTIME_SIDECAR"):
            self.verify()

    def test_writable_or_setid_companion_rejected(self):
        target = self.binaries / "gvisor-bin/gvisor_sentry"
        for mode in (0o777, 0o4755):
            target.chmod(mode)
            with self.assertRaises(SupervisorError):
                self.verify()

    def test_symlink_and_hardlink_companions_rejected(self):
        target = self.binaries / "gvisor-bin/gvisor_sentry"
        target.unlink()
        target.symlink_to(self.binaries / "runsc")
        with self.assertRaises(SupervisorError):
            self.verify()
        target.unlink()
        os.link(self.binaries / "runsc", target)
        with self.assertRaises(SupervisorError):
            self.verify()

    def test_manifest_mutation_rejected(self):
        self.manifest.write_bytes(self.manifest.read_bytes() + b"\n")
        with self.assertRaisesRegex(SupervisorError, "RUNTIME_BUNDLE_DIGEST_MISMATCH"):
            self.verify()
