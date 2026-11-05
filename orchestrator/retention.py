"""Trusted Linux byte retirement. Never executes or follows stored content.

Caller must hold a DB deletion plan after revocation and confirmed worker cleanup.
Root descriptors and flock serialize with asset writers and execution journals.
Markers survive DB/byte restores and prevent reuse until separately audited pruning.
"""

import fcntl
import json
import os
import re
import stat
import sys
from pathlib import Path
from uuid import UUID

ASSETS = Path("/var/lib/proofflow-product/assets")
JOBS = Path("/var/lib/proofflow-product/jobs")


class RetentionError(Exception):
    pass


def root(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    info = os.fstat(fd)
    if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
        os.close(fd)
        raise RetentionError("RETENTION_ROOT_UNSAFE")
    return fd


def marker(fd, name):
    names = os.listdir(fd)
    if name not in names and sum(n.startswith(".deleted-") for n in names) >= 512:
        raise RetentionError("RETENTION_MARKER_CAPACITY")
    try:
        out = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400, dir_fd=fd)
    except FileExistsError:
        info = os.stat(name, dir_fd=fd, follow_symlinks=False)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o400):
            raise RetentionError("RETENTION_MARKER_UNSAFE") from None
    else:
        try:
            remaining = b"deleted\n"
            while remaining:
                written = os.write(out, remaining)
                if written <= 0:
                    raise RetentionError("RETENTION_MARKER_WRITE_FAILED")
                remaining = remaining[written:]
            os.fsync(out)
        finally:
            os.close(out)
        os.fsync(fd)


def inspect_tree(fd, device, depth=0, counter=None):
    counter = counter if counter is not None else [0]
    if depth > 3:
        raise RetentionError("RETENTION_TREE_LIMIT")
    for name in os.listdir(fd):
        counter[0] += 1
        if counter[0] > 4096 or len(name) > 160 or "/" in name:
            raise RetentionError("RETENTION_TREE_LIMIT")
        info = os.stat(name, dir_fd=fd, follow_symlinks=False)
        if info.st_uid != os.geteuid() or info.st_dev != device:
            raise RetentionError("RETENTION_OWNER_OR_DEVICE_CHANGED")
        if stat.S_ISDIR(info.st_mode):
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            try:
                inspect_tree(child, device, depth+1, counter)
            finally:
                os.close(child)
        elif not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise RetentionError("RETENTION_UNSAFE_ENTRY")


def empty_tree(fd):
    # Called only on an already validated, locked private tree. Recheck types
    # while unlinking; never follow links or recursively pass paths to a shell.
    for name in os.listdir(fd):
        info = os.stat(name, dir_fd=fd, follow_symlinks=False)
        if stat.S_ISDIR(info.st_mode):
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            try:
                empty_tree(child)
            finally:
                os.close(child)
            os.rmdir(name, dir_fd=fd)
        elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
            os.unlink(name, dir_fd=fd)
        else:
            raise RetentionError("RETENTION_UNSAFE_ENTRY")
    os.fsync(fd)


def remove_tree(parent, name):
    try:
        fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    except FileNotFoundError:
        return
    try:
        info = os.fstat(fd)
        if (info.st_uid != os.geteuid() or info.st_dev != os.fstat(parent).st_dev
                or stat.S_IMODE(info.st_mode) != 0o700):
            raise RetentionError("RETENTION_DIRECTORY_UNSAFE")
        inspect_tree(fd, os.fstat(parent).st_dev)
        empty_tree(fd)
    finally:
        os.close(fd)
    os.rmdir(name, dir_fd=parent)
    os.fsync(parent)


def retire(plan, assets=ASSETS, jobs=JOBS):
    if type(plan) is not dict or set(plan) != {"workspace", "jobs", "manifest_sha256"}:
        raise RetentionError("RETENTION_PLAN_INVALID")
    workspace = UUID(plan["workspace"])
    if (str(workspace) != plan["workspace"] or type(plan["jobs"]) is not list
            # Existing database caps are16 originals plus16 repairs globally.
            # Their union can legitimately contain32 identities in one workspace.
            or len(plan["jobs"]) > 32 or len(set(plan["jobs"])) != len(plan["jobs"])
            or re.fullmatch(r"[0-9a-f]{64}", plan["manifest_sha256"]) is None):
        raise RetentionError("RETENTION_PLAN_INVALID")
    job_ids = {UUID(j).hex for j in plan["jobs"]}
    a, j = root(assets), None
    try:
        j = root(jobs)
        # Nonblocking: active work retains its lease/files. The timer will try
        # later; no controller is killed to make deletion appear successful.
        fcntl.flock(a, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(j, fcntl.LOCK_EX | fcntl.LOCK_NB)
        marker(a, ".deleted-" + workspace.hex)
        for job in job_ids:
            marker(j, ".deleted-" + job)
        names = os.listdir(j)
        if len(names) > 600:
            raise RetentionError("RETENTION_JOURNAL_LIMIT")
        retired = ".retiring-" + workspace.hex + "-"
        for name in names:
            if re.fullmatch(r"[0-9a-f]{32}", name):
                fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=j)
                try:
                    try:
                        raw_fd = os.open("intent.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                         dir_fd=fd)
                    except FileNotFoundError:
                        continue  # Unknown pre-intent directory is never attributed or removed.
                    try:
                        info = os.fstat(raw_fd)
                        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                                or info.st_nlink != 1 or info.st_size > 32768):
                            raise RetentionError("RETENTION_INTENT_UNSAFE")
                        intent = json.loads(os.read(raw_fd, 32769))
                    finally:
                        os.close(raw_fd)
                    if intent.get("job") not in job_ids:
                        continue
                    inspect_tree(fd, os.fstat(j).st_dev)
                finally:
                    os.close(fd)
                os.rename(name, retired + name, src_dir_fd=j, dst_dir_fd=j)
                os.fsync(j)
                remove_tree(j, retired + name)
            elif name.startswith(retired) and re.fullmatch(r"[0-9a-f]{32}", name[len(retired):]):
                remove_tree(j, name)
        remove_tree(a, workspace.hex)
        return {"workspace": str(workspace), "manifest_sha256": plan["manifest_sha256"],
                "bytes_removed": True, "restore_markers": True}
    finally:
        os.close(a)
        if j is not None:
            os.close(j)


if __name__ == "__main__":
    try:
        if os.geteuid() != 10003:
            raise RetentionError("RETENTION_IDENTITY_INVALID")
        raw = sys.stdin.buffer.read(32769)
        if len(raw) > 32768:
            raise RetentionError("RETENTION_PLAN_LIMIT")
        print(json.dumps(retire(json.loads(raw), Path("/run/proofflow-retention-assets"),
                                Path("/run/proofflow-retention-jobs"))))
    except (OSError, ValueError, KeyError, TypeError, RetentionError):
        print("RETENTION_INCOMPLETE", file=sys.stderr)
        raise SystemExit(1) from None
