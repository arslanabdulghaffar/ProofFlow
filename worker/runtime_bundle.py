"""Pin the complete multi-file gVisor runtime, not just its runsc launcher."""

import hashlib
import re
import stat
from pathlib import Path

from worker.protocol import SupervisorError
from worker.wire import keys, strict_json

MEMBERS = frozenset({
    "runsc", "containerd-shim-runsc-v1", "gvisor-bin/checkpointgofer",
    "gvisor-bin/gvisor-proc-umounter", "gvisor-bin/gvisor-sentry-prewarmer",
    "gvisor-bin/gvisor_sentry", "gvisor-bin/runsc-fd-parking", "gvisor-bin/runsc-metric-server",
})


def parse_manifest(raw: bytes, expected_sha256: str, expected_runsc: str) -> dict:
    if (type(raw) is not bytes or len(raw) > 16384
            or hashlib.sha256(raw).hexdigest() != expected_sha256):
        raise SupervisorError("RUNTIME_BUNDLE_DIGEST_MISMATCH")
    value = strict_json(raw)
    keys(value, {"schema", "release", "architecture", "archive_sha256", "archive_url", "members"})
    if (type(value["schema"]) is not int or value["schema"] != 1
            or value["architecture"] != "x86_64"
            or type(value["release"]) is not str
            or not re.fullmatch(r"release-[0-9]{8}\.[0-9]+", value["release"])
            or type(value["archive_sha256"]) is not str
            or not re.fullmatch("[0-9a-f]{64}", value["archive_sha256"])
            or value["archive_url"] != "https://github.com/google/gvisor/releases/download/"
            + value["release"] + "/gvisor-x86_64.tar.bz2"):
        raise SupervisorError("RUNTIME_BUNDLE_INVALID")
    keys(value["members"], MEMBERS)
    for member in value["members"].values():
        keys(member, {"sha256", "bytes"})
        if (type(member["bytes"]) is not int or not 1 <= member["bytes"] <= 60000000
                or type(member["sha256"]) is not str
                or not re.fullmatch("[0-9a-f]{64}", member["sha256"])):
            raise SupervisorError("RUNTIME_BUNDLE_INVALID")
    if value["members"]["runsc"]["sha256"] != expected_runsc:
        raise SupervisorError("RUNTIME_BUNDLE_LAUNCHER_MISMATCH")
    return value


def _protected(path: Path, *, regular: bool):
    info = path.lstat()
    if (info.st_uid != 0 or info.st_mode & 0o022
            or (regular and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1))
            or (not regular and not stat.S_ISDIR(info.st_mode))):
        raise SupervisorError("UNSAFE_RUNTIME_BUNDLE")
    return info


def validate_bundle(expected_sha256: str, expected_runsc: str) -> None:
    manifest = Path("/etc/proofflow-worker/runtime.json")
    for parent in manifest.parents:
        _protected(parent, regular=False)
    info = _protected(manifest, regular=True)
    if info.st_size > 16384:
        raise SupervisorError("RUNTIME_BUNDLE_INVALID")
    value = parse_manifest(manifest.read_bytes(), expected_sha256, expected_runsc)
    root = Path("/usr/local/bin")
    for directory in [root, *root.parents, root / "gvisor-bin"]:
        _protected(directory, regular=False)
    if {p.name for p in (root / "gvisor-bin").iterdir()} != {
        name.split("/")[1] for name in MEMBERS if name.startswith("gvisor-bin/")
    }:
        raise SupervisorError("UNEXPECTED_RUNTIME_SIDECAR")
    for name, recorded in value["members"].items():
        path = root / name
        info = _protected(path, regular=True)
        if info.st_size != recorded["bytes"] or stat.S_IMODE(info.st_mode) != 0o755:
            raise SupervisorError("UNSAFE_RUNTIME_BUNDLE")
        with path.open("rb") as source:
            if hashlib.file_digest(source, "sha256").hexdigest() != recorded["sha256"]:
                raise SupervisorError("RUNTIME_SIDECAR_DIGEST_MISMATCH")
