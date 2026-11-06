"""Linux isolated asset materialization. Uploaded code stays inert, non-executable data."""

import os
import stat
from uuid import UUID

from api.app.assets import put_asset, read_asset
from orchestrator.asset_backup import select_recovery
from orchestrator.restore_guard import RestoreError


def materialize(directory_fd, payload, current, *, now):
    """Requires a newly created empty private staging directory, never a live root.

    No sessions or approvals are issued. Caller rechecks live authority after this
    operation and discards staging on failure; it must never promote this root.
    """
    info = os.fstat(directory_fd)
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o700 or os.listdir(directory_fd)):
        raise RestoreError("RECOVERY_TARGET_NOT_EMPTY_PRIVATE_DIRECTORY")
    plan, assets = select_recovery(payload, current, now=now)
    created, report = set(), []
    for workspace, digest, raw in assets:
        name = UUID(workspace).hex
        if name not in created:
            os.mkdir(name, 0o700, dir_fd=directory_fd)
            created.add(name)
        fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory_fd)
        try:
            if put_asset(fd, raw) != digest or read_asset(fd, digest) != raw:
                raise RestoreError("RECOVERY_BYTE_MISMATCH")
        finally:
            os.close(fd)
        report.append({"workspace": workspace, "sha256": digest, "byte_size": len(raw)})
    os.fsync(directory_fd)
    return {"plan": plan, "assets": report, "mode": "INERT_DATA_ONLY_NO_PROMOTION"}
