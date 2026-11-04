"""Real Linux descriptor/permission probes; generated test keys never leave this fixture."""

import json
import os
import sys
from dataclasses import asdict

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from api.app import batch_events
from integrations import github_setup
from integrations.github_app import GitHubConfig, GitHubFailure

pytestmark = pytest.mark.skipif(
    sys.platform != "linux", reason="Linux O_PATH/UID descriptor boundary"
)


@pytest.mark.parametrize(
    "attack", ["symlink", "hardlink", "fifo", "permissions", "directory_mode", "wrong_size"]
)
def test_batch_master_rejects_unsafe_objects_without_blocking(tmp_path, monkeypatch, attack):
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    monkeypatch.setattr(batch_events, "DIRECTORY", str(root))
    key = root / "master"
    key.write_bytes(b"x" * 32)
    key.chmod(0o400)
    assert batch_events.load_batch_master() == b"x" * 32
    if attack == "symlink":
        key.rename(root / "original")
        key.symlink_to(root / "original")
    elif attack == "hardlink":
        os.link(key, root / "alias")
    elif attack == "fifo":
        key.unlink()
        os.mkfifo(key, 0o400)
    elif attack == "permissions":
        key.chmod(0o644)
    elif attack == "directory_mode":
        root.chmod(0o755)
    else:
        key.chmod(0o600)
        key.write_bytes(b"x" * 33)
        key.chmod(0o400)
    with pytest.raises(batch_events.SignatureFailure):
        batch_events.load_batch_master()


def test_github_optional_empty_mount_then_exact_key_and_file_scope(tmp_path, monkeypatch):
    root = tmp_path / "github"
    root.mkdir(mode=0o700)
    monkeypatch.setattr(github_setup, "DIRECTORY", str(root))
    assert github_setup.load_github_app() is None
    config = GitHubConfig("Iv1.fixture", 12, 34)
    metadata = root / "configuration.json"
    metadata.write_text(json.dumps(asdict(config)))
    metadata.chmod(0o400)
    with pytest.raises(GitHubFailure, match="GITHUB_SETUP_INCOMPLETE"):
        github_setup.load_github_app()
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = root / "private-key.pem"
    pem.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    pem.chmod(0o400)
    app = github_setup.load_github_app()
    assert app.config == config and "PRIVATE KEY" not in repr(app)
    pem.chmod(0o644)
    with pytest.raises(GitHubFailure, match="GITHUB_SECRET_FILE_UNSAFE"):
        github_setup.load_github_app()
