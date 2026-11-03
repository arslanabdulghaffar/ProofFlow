"""Linux filesystem/SQLite checks with inert data, no mounts or execution."""

import os
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from worker.journal import Journal
from worker.protocol import ExecutionRequest, SupervisorError
from worker.staging import Staging


def request():
    return ExecutionRequest(uuid4(), uuid4(), 1, b"# inert", b"", b"", b"{}")


@unittest.skipUnless(sys.platform == "linux", "Linux ownership and descriptor semantics")
class JournalChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="proofflow-journal-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.journal = Journal(self.root)

    def test_concurrent_admission_exactly_two_slots(self):
        def admit(_):
            try:
                return self.journal.admit(request(), "a" * 64)
            except SupervisorError as error:
                self.assertEqual(str(error), "WORKER_CAPACITY_EXHAUSTED")
                return False
        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(list(pool.map(admit, range(20))).count(True), 2)

    def test_exact_replay_and_runtime_change_conflict(self):
        item = request()
        self.assertTrue(self.journal.admit(item, "a" * 64))
        self.assertFalse(self.journal.admit(item, "a" * 64))
        for changed, identity in ((replace(item, pipeline=b"changed"), "a" * 64),
                                  (item, "b" * 64)):
            with self.assertRaisesRegex(SupervisorError, "EXECUTION_CONFLICT"):
                self.journal.admit(changed, identity)

    def test_fence_cancels_and_rejects_old_generation(self):
        item = request()
        self.journal.admit(item, "a" * 64)
        self.journal.fence(item.job_id, 2)
        self.assertTrue(self.journal.cancelled(item.execution_id))
        with self.assertRaisesRegex(SupervisorError, "STALE_EXECUTION_GENERATION"):
            self.journal.admit(replace(item, execution_id=uuid4()), "a" * 64)

    def test_cancel_scope_and_terminal_state(self):
        item = request()
        self.journal.admit(item, "a" * 64)
        with self.assertRaisesRegex(SupervisorError, "EXECUTION_SCOPE_MISMATCH"):
            self.journal.cancel(item.execution_id, uuid4(), 1)
        self.journal.cancel(item.execution_id, item.job_id, 1)
        receipt = {"outcome": "exited"}
        self.journal.finish(item.execution_id, receipt, cleaned=True)
        self.assertEqual(receipt["outcome"], "cancelled")
        with self.assertRaisesRegex(SupervisorError, "EXECUTION_SCOPE_MISMATCH"):
            self.journal.cancel(item.execution_id, item.job_id, 1)

    def test_quarantine_survives_reopen(self):
        item = request()
        self.journal.admit(item, "a" * 64)
        self.journal.finish(item.execution_id, {"cleanup": "uncertain"}, cleaned=False)
        reopened = Journal(self.root)
        self.assertEqual(reopened.unfinished(), [item.execution_id])
        with self.assertRaisesRegex(SupervisorError, "WORKER_QUARANTINED"):
            reopened.admit(request(), "a" * 64)

    def test_newer_generation_waits_for_previous_cleanup(self):
        item = request()
        self.journal.admit(item, "a" * 64)
        with self.assertRaisesRegex(SupervisorError, "JOB_ALREADY_RUNNING"):
            self.journal.admit(replace(item, execution_id=uuid4(), generation=2), "a" * 64)
        self.journal.finish(item.execution_id, {}, cleaned=True)
        self.assertTrue(self.journal.admit(replace(item, execution_id=uuid4(), generation=2),
                                           "a" * 64))

    def test_retention_cap_and_expired_exact_directory_prune(self):
        staging = Staging(self.root)
        identifiers = [uuid4() for _ in range(20)]
        for identifier in identifiers:
            target = self.root / "results" / identifier.hex
            target.mkdir(mode=0o700)
            (target / "ledger.jsonl").write_bytes(b"inert fixture")
        self.assertEqual(staging.prune_results(set()), 20)
        with self.assertRaisesRegex(SupervisorError, "RESULT_RETENTION_CAPACITY"):
            self.journal.admit(request(), "a" * 64, retained_slots=20)
        # Replay remains available even when no new retention slot is available.
        item = request()
        self.journal.admit(item, "a" * 64)
        self.assertFalse(self.journal.admit(item, "a" * 64, retained_slots=20))
        self.assertEqual(staging.prune_results({item.execution_id}), 21)
        for identifier in identifiers:
            os.utime(self.root / "results" / identifier.hex, (1, 1))
        staging.prune_results({identifiers[0]})
        self.assertEqual(list((self.root / "results").iterdir()),
                         [self.root / "results" / identifiers[0].hex])

    def test_symlink_execution_cleanup_does_not_follow_target(self):
        staging = Staging(self.root)
        outside = self.root / "must-survive"
        outside.mkdir(mode=0o700)
        identifier = uuid4()
        staging.path(identifier).symlink_to(outside)
        with self.assertRaisesRegex(SupervisorError, "UNSAFE_WORKER_DIRECTORY"):
            staging.cleanup(identifier)
        self.assertTrue(outside.is_dir())


if __name__ == "__main__":
    unittest.main()
