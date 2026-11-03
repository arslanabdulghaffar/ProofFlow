"""Trusted Linux file fixtures only; no uploaded/generated code is executed.

Run with python3 -m unittest discover -s tests/security -v on local Linux.
These are component checks, NOT worker termination or sandbox acceptance.
"""

import hashlib
import os
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from worker.collector import MAX_OUTPUT_BYTES, MAX_OUTPUT_LINES, CollectionError
from worker.collector import collect_stopped_outputs as collect


@unittest.skipUnless(sys.platform == "linux", "Linux descriptor semantics required")
class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="proofflow-trusted-collector-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / "output"
        self.output.mkdir()
        self.ledger = self.output / "ledger.jsonl"
        self.unresolved = self.output / "unresolved.jsonl"
        self.ledger.write_bytes(b'{"synthetic":true}\n')
        self.unresolved.write_bytes(b"")
        self.fd = os.open(self.output, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, self.fd)

    def rejected(self, code, rollups=False):
        with self.assertRaisesRegex(CollectionError, "^" + code + "$"):
            collect(self.fd, include_rollups=rollups)

    def test_exact_bytes_hash_and_empty_file(self):
        result = collect(self.fd, include_rollups=False)
        self.assertEqual([f.name for f in result], ["ledger.jsonl", "unresolved.jsonl"])
        for item in result:
            self.assertEqual(item.content, (self.output / item.name).read_bytes())
            self.assertEqual(item.sha256, hashlib.sha256(item.content).hexdigest())
        self.assertEqual([f.lines for f in result], [1, 0])
        os.fstat(self.fd)  # Caller still owns its descriptor.

    def test_optional_rollup_is_required_and_otherwise_forbidden(self):
        self.rejected("MISSING_OUTPUT_FILE", rollups=True)
        (self.output / "rollups.jsonl").write_bytes(b"{}")
        self.rejected("UNEXPECTED_OUTPUT_ENTRY")
        self.assertEqual(collect(self.fd, include_rollups=True)[2].lines, 1)

    def test_missing_file(self):
        self.ledger.unlink()
        self.rejected("MISSING_OUTPUT_FILE")

    def test_extra_filename_is_not_reflected_in_error(self):
        (self.output / "<script>secret</script>".replace("/", "_")).write_bytes(b"PASS")
        self.rejected("UNEXPECTED_OUTPUT_ENTRY")

    def test_symlink_never_follows_external_target(self):
        outside = self.root / "private"
        outside.write_bytes(b"synthetic-host-marker")
        self.ledger.unlink()
        self.ledger.symlink_to(outside)
        self.rejected("UNSAFE_OUTPUT_TYPE_OR_LINK")
        self.assertEqual(outside.read_bytes(), b"synthetic-host-marker")

    def test_hardlink_rejected(self):
        os.link(self.ledger, self.root / "alias")
        self.rejected("UNSAFE_OUTPUT_TYPE_OR_LINK")

    def test_directory_rejected(self):
        self.ledger.unlink()
        self.ledger.mkdir()
        self.rejected("UNSAFE_OUTPUT_TYPE_OR_LINK")

    def test_fifo_not_opened_for_io(self):
        self.ledger.unlink()
        os.mkfifo(self.ledger)
        real_open = os.open
        def checked_open(path, flags, *args, **kwargs):
            if path == "ledger.jsonl":
                self.assertTrue(flags & os.O_PATH)
            if str(path).startswith("/proc/self/fd/"):
                self.fail("Nonregular inode must not be reopened for I/O")
            return real_open(path, flags, *args, **kwargs)
        with patch("worker.collector.os.open", side_effect=checked_open):
            self.rejected("UNSAFE_OUTPUT_TYPE_OR_LINK")

    def test_socket_rejected(self):
        self.ledger.unlink()
        with socket.socket(socket.AF_UNIX) as sock:
            sock.bind(str(self.ledger))
            self.rejected("UNSAFE_OUTPUT_TYPE_OR_LINK")

    def test_device_inode_is_rejected_without_device_io(self):
        # Trusted fault injection supplies an existing device O_PATH descriptor;
        # this does not create a device or open it for reading/writing.
        real_open = os.open
        def device_open(path, flags, *args, **kwargs):
            if path == "ledger.jsonl":
                return real_open("/dev/null", os.O_PATH | os.O_CLOEXEC)
            if str(path).startswith("/proc/self/fd/"):
                self.fail("Device inode must not be reopened for I/O")
            return real_open(path, flags, *args, **kwargs)
        with patch("worker.collector.os.open", side_effect=device_open):
            self.rejected("UNSAFE_OUTPUT_TYPE_OR_LINK")

    def test_combined_byte_limit_exact_then_plus_one(self):
        self.ledger.write_bytes(b"x" * (MAX_OUTPUT_BYTES - 1))
        self.unresolved.write_bytes(b"x")
        self.assertEqual(sum(len(f.content) for f in collect(self.fd, include_rollups=False)),
                         MAX_OUTPUT_BYTES)
        self.unresolved.write_bytes(b"xx")
        self.rejected("OUTPUT_BYTES_EXCEEDED")

    def test_sparse_oversized_file_rejected_without_read(self):
        with self.ledger.open("wb") as stream:
            stream.truncate(MAX_OUTPUT_BYTES + 1)
        with patch("worker.collector.os.read", side_effect=AssertionError("Must not read")):
            self.rejected("OUTPUT_BYTES_EXCEEDED")

    def test_combined_line_limit_and_unterminated_final_line(self):
        self.ledger.write_bytes(b"\n" * (MAX_OUTPUT_LINES - 1))
        self.unresolved.write_bytes(b"x")
        self.assertEqual(sum(f.lines for f in collect(self.fd, include_rollups=False)),
                         MAX_OUTPUT_LINES)
        self.unresolved.write_bytes(b"\nx")
        self.rejected("OUTPUT_LINES_EXCEEDED")

    def test_opaque_data_is_not_a_verdict_or_executed(self):
        payload = b"PASS\x00\xff\nimport os; raise RuntimeError('do not execute')"
        self.ledger.write_bytes(payload)
        self.assertEqual(collect(self.fd, include_rollups=False)[0].content, payload)

    def test_retained_directory_handle_survives_path_swap(self):
        moved = self.root / "moved"
        self.output.rename(moved)
        self.output.mkdir()
        (self.output / "ledger.jsonl").write_bytes(b"wrong directory")
        self.assertEqual(collect(self.fd, include_rollups=False)[0].content,
                         (moved / "ledger.jsonl").read_bytes())

    def test_replacement_during_read_rejected(self):
        replacement = self.root / "replacement"
        replacement.write_bytes(self.ledger.read_bytes())
        real_read = os.read
        changed = False
        def replacing_read(fd, size):
            nonlocal changed
            data = real_read(fd, size)
            if not changed:
                changed = True
                os.replace(replacement, self.ledger)
            return data
        with patch("worker.collector.os.read", side_effect=replacing_read):
            self.rejected("OUTPUT_CHANGED")

    def test_same_size_mutation_with_restored_mtime_rejected(self):
        before = self.ledger.stat()
        real_read = os.read
        changed = False
        def mutating_read(fd, size):
            nonlocal changed
            data = real_read(fd, size)
            if not changed:
                changed = True
                self.ledger.write_bytes(b"x" * before.st_size)
                os.utime(self.ledger, ns=(before.st_atime_ns, before.st_mtime_ns))
            return data
        with patch("worker.collector.os.read", side_effect=mutating_read):
            self.rejected("OUTPUT_CHANGED")

    def test_extra_entry_during_read_rejected(self):
        real_read = os.read
        def adding_read(fd, size):
            data = real_read(fd, size)
            (self.output / "unexpected").touch()
            return data
        with patch("worker.collector.os.read", side_effect=adding_read):
            self.rejected("UNEXPECTED_OUTPUT_ENTRY")

    def test_first_file_changed_while_reading_second_is_rejected(self):
        self.unresolved.write_bytes(b"second")
        real_read = os.read
        def late_write(fd, size):
            data = real_read(fd, size)
            if data == b"second":
                self.ledger.write_bytes(b"late writer")
            return data
        with patch("worker.collector.os.read", side_effect=late_write):
            self.rejected("OUTPUT_CHANGED")

    def test_read_error_is_redacted_and_descriptors_closed(self):
        before = len(os.listdir("/proc/self/fd"))
        with patch("worker.collector.os.read", side_effect=OSError("sensitive/path")):
            self.rejected("OUTPUT_IO_ERROR")
        self.assertEqual(len(os.listdir("/proc/self/fd")), before)

    def test_regular_file_cannot_be_collection_root(self):
        fd = os.open(self.ledger, os.O_RDONLY)
        try:
            with self.assertRaisesRegex(CollectionError, "^OUTPUT_IO_ERROR$"):
                collect(fd, include_rollups=False)
        finally:
            os.close(fd)

    def test_descriptors_closed_after_success_and_failure(self):
        before = len(os.listdir("/proc/self/fd"))
        for _ in range(20):
            collect(self.fd, include_rollups=False)
        self.ledger.unlink()
        os.mkfifo(self.ledger)
        for _ in range(20):
            self.rejected("UNSAFE_OUTPUT_TYPE_OR_LINK")
        self.assertEqual(len(os.listdir("/proc/self/fd")), before)

    def test_invalid_descriptor_is_redacted(self):
        with self.assertRaisesRegex(CollectionError, "^OUTPUT_IO_ERROR$"):
            collect(-1, include_rollups=False)

    def test_rollup_flag_is_not_coerced(self):
        with self.assertRaisesRegex(CollectionError, "^INVALID_COLLECTOR_ARGUMENT$"):
            collect(self.fd, include_rollups="false")


if __name__ == "__main__":
    unittest.main()
