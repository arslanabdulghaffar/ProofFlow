"""Linux installer probes on isolated temporary paths with command doubles. No services touched."""

import base64
import io
import json
import os
import stat
import sys
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest

from integrations.github_app import GitHubConfig
from scripts import install_github_app as installer

pytestmark = pytest.mark.skipif(
    sys.platform != "linux" or not hasattr(os, "geteuid") or os.geteuid() != 0,
    reason="Disposable root-owned Linux fixture only",
)


def test_fixed_installer_idempotent_private_files_and_no_key_rotation(tmp_path, monkeypatch):
    root = tmp_path / "integration"
    root.mkdir(mode=0o700)
    os.chown(root, 10003, 10003)
    monkeypatch.setattr(
        installer, "Path", lambda value: root if value == "/etc/proofflow-github" else Path(value)
    )
    calls = []

    def command(argv, raw=None):
        calls.append((argv, raw))
        if raw and raw.startswith(b"SELECT"):
            return b"t"
        if raw:
            return b"a" * 64
        return b""

    monkeypatch.setattr(installer, "command", command)
    pem = b"-----BEGIN PRIVATE KEY-----\n" + b"fixture-only" * 64
    config = asdict(GitHubConfig("Iv1.fixture", 12, 34))

    def execute(key=pem):
        raw = json.dumps(
            {"configuration": config, "private_key_base64": base64.b64encode(key).decode()}
        ).encode()
        monkeypatch.setattr(installer.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(raw)))
        installer.main()

    execute()
    require_paths = {p.name for p in root.iterdir()}
    assert require_paths == {"private-key.pem", "configuration.json"}
    for path in root.iterdir():
        info = path.lstat()
        assert info.st_uid == 10003 and stat.S_IMODE(info.st_mode) == 0o400 and info.st_nlink == 1
    first = (root / "private-key.pem").stat().st_ino
    execute()
    assert (root / "private-key.pem").stat().st_ino == first
    with pytest.raises(RuntimeError, match="GITHUB_EXISTING_SECRET_CHANGED"):
        execute(pem + b"changed")
    assert (root / "private-key.pem").read_bytes() == pem
    assert all("private-key.pem" not in " ".join(argv) for argv, _ in calls)
