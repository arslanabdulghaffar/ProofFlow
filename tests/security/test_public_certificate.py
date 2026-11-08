"""Critical certificate rejection tests use generated test keys, never real credentials."""

import ipaddress
from datetime import UTC, datetime, timedelta

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from scripts.install_public_certificate import validate_pair

NOW = datetime.now(UTC)


def pair(address="192.0.2.1", hours=100, future=False):
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, "test")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(NOW + timedelta(hours=1) if future else NOW - timedelta(hours=1))
        .not_valid_after(NOW + timedelta(hours=hours))
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(address))]), False
        )
        .sign(key, hashes.SHA256())
    )
    return (
        cert.public_bytes(serialization.Encoding.PEM),
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
    )


def test_valid_exact_ip_pair():
    cert, key = pair()
    assert validate_pair(cert, key, "192.0.2.1", NOW)


@pytest.mark.parametrize(
    "variant", ["wrong_ip", "wrong_key", "expiring", "not_yet_valid", "corrupt"]
)
def test_reject_before_install(variant):
    cert, key = pair(hours=23 if variant == "expiring" else 100, future=variant == "not_yet_valid")
    if variant == "wrong_key":
        _, key = pair()
    if variant == "corrupt":
        cert = b"not a certificate"
    with pytest.raises((ValueError, RuntimeError)):
        validate_pair(cert, key, "192.0.2.2" if variant == "wrong_ip" else "192.0.2.1", NOW)


@pytest.mark.skipif(__import__("sys").platform != "linux", reason="Linux rotation filesystem")
@pytest.mark.parametrize("fault", [None, "first_replace", "second_replace", "start", "active"])
def test_interrupted_rotation_rolls_forward_before_service_start(tmp_path, monkeypatch, fault):
    import os

    from scripts import install_public_certificate as hook

    if os.geteuid() != 0:
        pytest.skip("UID policy fixture requires local root")
    monkeypatch.setattr(hook, "DEST", tmp_path)
    old_cert, old_key = pair()
    new_cert, new_key = pair()
    old = {"health.pem": old_cert, "health.key": old_key}
    target = {"health.pem": new_cert, "health.key": new_key}
    for name, raw in old.items():
        hook.stage(tmp_path / name, raw, 10003)
    actions, writes = [], []
    real_replace = os.replace
    injected = []

    def replace(source, destination):
        real_replace(source, destination)
        writes.append(destination.name)
        if fault == {1: "first_replace", 2: "second_replace"}.get(len(writes)) and not injected:
            injected.append(True)
            raise RuntimeError("fixture interruption")

    def service(action):
        actions.append(action)
        if action in {"start", "is-active"}:
            # Never start even a test service with the old key and new certificate.
            assert all(hook.read_file(tmp_path / n, 10003) == raw for n, raw in target.items())
            hook.validate_pair(new_cert, new_key, "192.0.2.1", NOW)
        if action == {"start": "start", "active": "is-active"}.get(fault) and not injected:
            injected.append(True)
            raise RuntimeError("fixture service failure")

    monkeypatch.setattr(hook.os, "replace", replace)
    monkeypatch.setattr(hook, "service", service)
    if fault:
        with pytest.raises(RuntimeError, match="fixture"):
            hook.install_pair(target, True)
        assert (tmp_path / ".rotation.json").exists()
        hook.install_pair(target, True)
    else:
        assert hook.install_pair(target, True)
    assert actions[-2:] == ["start", "is-active"]
    assert not (tmp_path / ".rotation.json").exists()
    assert not list(tmp_path.glob("*.pending"))
    assert all(hook.read_file(tmp_path / n, 10003) == raw for n, raw in target.items())
    count = len(actions)
    assert hook.install_pair(target, True) is False
    assert len(actions) == count  # An ordinary no-op does not restart the live guest API.


@pytest.mark.skipif(__import__("sys").platform != "linux", reason="Linux rotation filesystem")
@pytest.mark.parametrize("fault", ["marker", "pending", "symlink", "hardlink", "mode", "lock"])
def test_rotation_rejects_changed_or_unsafe_files(tmp_path, monkeypatch, fault):
    import fcntl
    import os

    from scripts import install_public_certificate as hook

    if os.geteuid() != 0:
        pytest.skip("UID policy fixture requires local root")
    monkeypatch.setattr(hook, "DEST", tmp_path)
    cert, key = pair()
    values = {"health.pem": cert, "health.key": key}
    actions = []
    monkeypatch.setattr(hook, "service", actions.append)
    held = None
    if fault == "marker":
        hook.stage(tmp_path / ".rotation.json", b"different target", 0)
    elif fault == "pending":
        hook.stage(tmp_path / "health.key.pending", b"unknown staged key", 10003)
    elif fault == "symlink":
        (tmp_path / "health.key").symlink_to(tmp_path / "unrelated")
        (tmp_path / "unrelated").write_bytes(b"preserve unrelated")
    elif fault == "hardlink":
        hook.stage(tmp_path / "health.key", key, 10003)
        os.link(tmp_path / "health.key", tmp_path / "unrelated")
    elif fault == "mode":
        hook.stage(tmp_path / "health.key", key, 10003)
        (tmp_path / "health.key").chmod(0o600)
    else:
        held = os.open(tmp_path / ".rotation.lock", os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        with pytest.raises((RuntimeError, OSError)):
            hook.install_pair(values, True)
        assert "start" not in actions
    finally:
        if held is not None:
            os.close(held)


@pytest.mark.skipif(__import__("sys").platform != "linux", reason="Linux process crash fixture")
def test_actual_process_exit_between_pair_writes_is_recoverable(tmp_path, monkeypatch):
    import os
    import subprocess
    import sys

    from scripts import install_public_certificate as hook

    if os.geteuid() != 0:
        pytest.skip("UID policy fixture requires local root")
    monkeypatch.setattr(hook, "DEST", tmp_path)
    old_cert, old_key = pair()
    cert, key = pair()
    target = {"health.pem": cert, "health.key": key}
    hook.stage(tmp_path / "health.pem", old_cert, 10003)
    hook.stage(tmp_path / "health.key", old_key, 10003)
    # Generated disposable keys only; no deployment certificates or credentials.
    for name, value in target.items():
        (tmp_path / (name + ".fixture")).write_bytes(value)
    program = """
import os,sys
from pathlib import Path
from scripts import install_public_certificate as h
h.DEST=Path(sys.argv[1]);h.service=lambda action:None
values={n:(h.DEST/(n+'.fixture')).read_bytes() for n in ('health.pem','health.key')}
replace=os.replace
def crash(src,dst):
 replace(src,dst)
 os._exit(77)
h.os.replace=crash
h.install_pair(values,True)
"""
    result = subprocess.run([sys.executable, "-c", program, str(tmp_path)],  # noqa: S603
                            capture_output=True, timeout=15)
    assert result.returncode == 77
    assert (tmp_path / ".rotation.json").exists()
    assert hook.read_file(tmp_path / "health.pem", 10003) == cert
    assert hook.read_file(tmp_path / "health.key", 10003) == old_key
    actions = []
    monkeypatch.setattr(hook, "service", actions.append)
    assert hook.install_pair(target, True)
    assert actions == ["stop", "start", "is-active"]
    assert not (tmp_path / ".rotation.json").exists()
    assert hook.read_file(tmp_path / "health.key", 10003) == key
