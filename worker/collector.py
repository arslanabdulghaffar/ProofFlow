"""Bounded byte collection from a supervisor-owned, quiescent Linux directory.

The future supervisor MUST prove all writers terminated before calling this
function. Metadata checks detect some races; they cannot establish quiescence.
The caller supplies its retained directory descriptor, never an uploaded path.
No execution, parsing, verdict, persistence, network, cleanup or approval occurs.
"""

import hashlib
import os
import stat
import sys
from contextlib import ExitStack
from dataclasses import dataclass

MAX_OUTPUT_BYTES = 10 * 1024 * 1024
MAX_OUTPUT_LINES = 20_000
CHUNK_BYTES = 64 * 1024


class CollectionError(Exception):
    """A fixed diagnostic code, without untrusted filenames or file contents."""


@dataclass(frozen=True)
class CollectedFile:
    name: str
    content: bytes
    sha256: str
    lines: int


def _identity(info: os.stat_result) -> tuple[int, ...]:
    # Reading changes atime. Deliberately exclude it, but include ctime so a
    # same-size rewrite followed by restored mtime is still detectable.
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _regular(info: os.stat_result, device: int) -> None:
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_dev != device:
        raise CollectionError("UNSAFE_OUTPUT_TYPE_OR_LINK")
    if info.st_size > MAX_OUTPUT_BYTES:
        raise CollectionError("OUTPUT_BYTES_EXCEEDED")


def _entries(directory_fd: int, allowed: tuple[str, ...]) -> None:
    # Never materialize an unbounded directory listing; a fourth entry fails.
    found = set()
    with os.scandir(directory_fd) as entries:
        for entry in entries:
            if entry.name not in allowed or entry.name in found:
                raise CollectionError("UNEXPECTED_OUTPUT_ENTRY")
            found.add(entry.name)
    if found != set(allowed):
        raise CollectionError("MISSING_OUTPUT_FILE")


def collect_stopped_outputs(
    directory_fd: int, *, include_rollups: bool,
) -> tuple[CollectedFile, ...]:
    """Collect fixed allowed names only; return nothing on any collection error.

    Linux O_PATH pins each inode without activating a FIFO/device. After checking
    its type, a trusted /proc/self/fd reference opens that pinned regular inode.
    All descriptors remain open through final identity checks. A trusted procfs
    and a local supervisor-owned bounded filesystem are deployment prerequisites.
    include_rollups is derived from the approved contract by trusted integration;
    it is not an API parameter or permission granted by candidate output.
    """
    if sys.platform != "linux":
        raise CollectionError("UNSUPPORTED_COLLECTOR_PLATFORM")
    if type(directory_fd) is not int or type(include_rollups) is not bool:
        raise CollectionError("INVALID_COLLECTOR_ARGUMENT")
    allowed = ("ledger.jsonl", "unresolved.jsonl")
    if include_rollups:
        allowed += ("rollups.jsonl",)
    try:
        with ExitStack() as stack:
            # Independent directory description; do not change caller's offset
            # or close its retained handle. No parent path is resolved here.
            root = os.open(".", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC,
                           dir_fd=directory_fd)
            stack.callback(os.close, root)
            root_info = os.fstat(root)
            _entries(root, allowed)
            opened = []
            for name in allowed:
                pin = os.open(name, os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=root)
                stack.callback(os.close, pin)
                info = os.fstat(pin)
                _regular(info, root_info.st_dev)
                # No attacker-controlled pathname component. O_NOFOLLOW would
                # reject this intentional descriptor reference, so it is used
                # on the initial directory-relative O_PATH open instead.
                reader = os.open(f"/proc/self/fd/{pin}",
                                 os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
                stack.callback(os.close, reader)
                if _identity(os.fstat(reader)) != _identity(info):
                    raise CollectionError("OUTPUT_CHANGED")
                opened.append((name, pin, reader, info))
            if sum(info.st_size for _, _, _, info in opened) > MAX_OUTPUT_BYTES:
                raise CollectionError("OUTPUT_BYTES_EXCEEDED")
            collected = []
            total_bytes = total_lines = 0
            for name, _, reader, info in opened:
                chunks = []
                size = lines = 0
                last = b""
                digest = hashlib.sha256()
                while True:
                    chunk = os.read(reader, min(CHUNK_BYTES, MAX_OUTPUT_BYTES - total_bytes + 1))
                    if not chunk:
                        break
                    total_bytes += len(chunk)
                    size += len(chunk)
                    if total_bytes > MAX_OUTPUT_BYTES:
                        raise CollectionError("OUTPUT_BYTES_EXCEEDED")
                    lines += chunk.count(b"\n")
                    if total_lines + lines > MAX_OUTPUT_LINES:
                        raise CollectionError("OUTPUT_LINES_EXCEEDED")
                    digest.update(chunk)
                    chunks.append(chunk)
                    last = chunk[-1:]
                if last and last != b"\n":
                    lines += 1
                total_lines += lines
                if total_lines > MAX_OUTPUT_LINES:
                    raise CollectionError("OUTPUT_LINES_EXCEEDED")
                if size != info.st_size:
                    raise CollectionError("OUTPUT_CHANGED")
                collected.append(CollectedFile(name, b"".join(chunks), digest.hexdigest(), lines))
            # Check every file again after ALL reads, not just after its own read.
            for name, pin, reader, info in opened:
                for current in (os.fstat(pin), os.fstat(reader),
                                os.stat(name, dir_fd=root, follow_symlinks=False)):
                    if _identity(current) != _identity(info):
                        raise CollectionError("OUTPUT_CHANGED")
            _entries(root, allowed)
            if _identity(os.fstat(root)) != _identity(root_info):
                raise CollectionError("OUTPUT_DIRECTORY_CHANGED")
            return tuple(collected)
    except OSError:
        # Keep raw paths/contents out of application diagnostics.
        raise CollectionError("OUTPUT_IO_ERROR") from None
