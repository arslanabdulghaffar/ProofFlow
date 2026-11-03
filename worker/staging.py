"""Private staging, bounded host mounts, durable capture and exact owned cleanup."""

import json
import os
import re
import shutil
import stat
import time
from pathlib import Path
from uuid import UUID

from worker.collector import CollectedFile
from worker.host import command, sync_directory, synced_write
from worker.journal import private_directory
from worker.log_capture import CapturedStream
from worker.protocol import INPUT_NAMES, ExecutionRequest, SupervisorError


def _unescape(value: str) -> str:
    return re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), value)


def mount_inventory() -> dict[str, tuple[str, str, set[str]]]:
    mounts = {}
    with open("/proc/self/mountinfo", encoding="utf-8") as source:
        for line in source:
            before, after = line.rstrip().split(" - ", 1)
            fields, extra = before.split(), after.split()
            mounts[_unescape(fields[4])] = (extra[0], _unescape(extra[1]),
                                            set(fields[5].split(",") + extra[2].split(",")))
    return mounts


class Staging:
    def __init__(self, root: Path):
        private_directory(root)
        self.root = root
        for name in ("executions", "results"):
            (root / name).mkdir(mode=0o700, exist_ok=True)
            private_directory(root / name)

    def path(self, identifier: UUID) -> Path:
        if type(identifier) is not UUID:
            raise SupervisorError("INVALID_EXECUTION_ID")
        return self.root / "executions" / identifier.hex

    def prepare(self, request: ExecutionRequest) -> Path:
        path = self.path(request.execution_id)
        path.mkdir(mode=0o700)
        sync_directory(path.parent)
        synced_write(path / "owner.json", json.dumps({"execution": request.execution_id.hex,
                     "manifest": request.manifest_hash()}).encode())
        for directory in ("input", "output", "scratch", "state"):
            (path / directory).mkdir(mode=0o700)
        for name, data in zip(INPUT_NAMES, request.inputs(), strict=True):
            synced_write(path / "input" / name, data, mode=0o444)
        os.chmod(path / "input", 0o555)  # noqa: S103 - read-only guest input inside private host root
        sync_directory(path / "input")
        sync_directory(path)
        for name in ("output", "scratch"):
            # Reserve 64 KiB of the 64 MiB scratch budget for the guest /dev tmpfs.
            size = 67108864 if name == "output" else 67043328
            command(["/usr/bin/mount", "-t", "tmpfs", "-o",
                     f"size={size},nr_inodes=1024,mode=0700,uid=10001,gid=10001,nodev,nosuid,noexec",
                     "proofflow-" + request.execution_id.hex + "-" + name, str(path / name)])
            self.check_mount(request.execution_id, name)
        return path

    def check_mount(self, identifier: UUID, name: str) -> None:
        if name not in ("output", "scratch"):
            raise SupervisorError("INVALID_MOUNT_NAME")
        mount = mount_inventory().get(str(self.path(identifier) / name))
        sizes = {"size=65536k", "size=67108864", "size=64m"} if name == "output" \
            else {"size=65472k", "size=67043328"}
        if (not mount or mount[:2] != ("tmpfs", "proofflow-" + identifier.hex + "-" + name)
                or not {"rw", "nodev", "nosuid", "noexec", "nr_inodes=1024"} <= mount[2]
                or not (sizes & mount[2])):
            raise SupervisorError("UNSAFE_EXECUTION_MOUNT")

    def open_output(self, identifier: UUID) -> int:
        self.check_mount(identifier, "output")
        return os.open(self.path(identifier) / "output",
                       os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)

    def persist(self, identifier: UUID, files: tuple[CollectedFile, ...],
                logs: tuple[CapturedStream, ...], receipt: dict) -> None:
        target = self.root / "results" / identifier.hex
        target.mkdir(mode=0o700)
        for item in files:
            if item.name not in ("ledger.jsonl", "unresolved.jsonl", "rollups.jsonl"):
                raise SupervisorError("INVALID_COLLECTED_NAME")
            synced_write(target / item.name, item.content)
        for stream in logs:
            if stream.name not in ("stdout", "stderr"):
                raise SupervisorError("INVALID_CAPTURED_STREAM")
            synced_write(target / (stream.name + ".bin"), stream.content)
        metadata = {k: receipt[k] for k in ("execution", "manifest", "runtime", "files", "logs")}
        metadata["capture_status"] = "BYTES_PENDING_CLEANUP_NOT_VERIFIED"
        synced_write(target / "capture.json", json.dumps(metadata, sort_keys=True).encode())
        sync_directory(target)
        sync_directory(target.parent)

    def remove_result(self, identifier: UUID) -> None:
        target = self.root / "results" / identifier.hex
        if not target.exists() and not target.is_symlink():
            return
        private_directory(target)
        allowed = {"ledger.jsonl", "unresolved.jsonl", "rollups.jsonl", "stdout.bin",
                   "stderr.bin", "capture.json"}
        if not set(os.listdir(target)) <= allowed:
            raise SupervisorError("UNEXPECTED_RESULT_ENTRY")
        for name in os.listdir(target):
            os.unlink(target / name)  # Exact private registry directory, no link traversal.
        target.rmdir()
        sync_directory(target.parent)

    def prune_results(self, protected: set[UUID]) -> int:
        # Each unfinished execution reserves its future result slot, including
        # executions which have not written a result directory yet.
        remaining = set(protected)
        with os.scandir(self.root / "results") as entries:
            for entry in entries:
                try:
                    identifier = UUID(hex=entry.name)
                except ValueError:
                    raise SupervisorError("UNEXPECTED_RESULT_DIRECTORY") from None
                if identifier.hex != entry.name:
                    raise SupervisorError("UNEXPECTED_RESULT_DIRECTORY")
                private_directory(Path(entry.path))
                if identifier not in protected and time.time() - entry.stat().st_mtime >= 300:
                    self.remove_result(identifier)
                else:
                    remaining.add(identifier)
        return len(remaining)

    def cleanup(self, identifier: UUID) -> None:
        path = self.path(identifier)
        if not path.exists() and not path.is_symlink():
            return  # Journal intent can precede directory creation.
        private_directory(path)
        prefix = str(path) + "/"
        mounts = mount_inventory()
        allowed = {str(path / name) for name in ("output", "scratch")}
        if any(p.startswith(prefix) and p not in allowed for p in mounts):
            raise SupervisorError("UNEXPECTED_EXECUTION_MOUNT")
        for name in ("output", "scratch"):
            if str(path / name) in mounts:
                self.check_mount(identifier, name)
                command(["/usr/bin/umount", str(path / name)])  # Never lazy/forced.
        if any(p == str(path) or p.startswith(prefix) for p in mount_inventory()):
            raise SupervisorError("EXECUTION_MOUNT_REMAINS")
        # Only root-owned staging/state can be traversed after writers are proven gone.
        # Candidate-owned mount contents were discarded by normal unmount above.
        expected = {"owner.json", "config.json", "launch.ready", "input", "output",
                    "scratch", "state"}
        if not set(os.listdir(path)) <= expected:
            raise SupervisorError("UNEXPECTED_EXECUTION_ENTRY")
        for name in ("input", "output", "scratch", "state"):
            child = path / name
            if not child.exists() and not child.is_symlink():
                continue
            info = child.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid():
                raise SupervisorError("UNSAFE_STAGING_CLEANUP")
            if name == "input":
                if not set(os.listdir(child)) <= set(INPUT_NAMES):
                    raise SupervisorError("UNEXPECTED_STAGED_INPUT")
                for filename in os.listdir(child):
                    os.unlink(child / filename)  # Unlink entry, never follow a symlink.
            elif name == "state":
                if not shutil.rmtree.avoids_symlink_attacks:
                    raise SupervisorError("SAFE_TREE_CLEANUP_UNAVAILABLE")
                shutil.rmtree(child)  # Owned runtime state only, never mounted output/rootfs.
                continue
            child.rmdir()
        for name in ("owner.json", "config.json", "launch.ready"):
            if (path / name).exists() or (path / name).is_symlink():
                os.unlink(path / name)
        path.rmdir()
        sync_directory(path.parent)
