"""Root-only fixed ACME deploy hook; validate before replacing guest TLS files."""

import hashlib
import ipaddress
import json
import os
import stat
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import serialization

BASE = Path('/etc/proofflow-acme/production')
DEST = Path('/etc/proofflow-public-api/tls')


def read_file(path, uid):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    with os.fdopen(fd, 'rb') as source:
        info = os.fstat(source.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != uid or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != 0o400 or not 1 <= info.st_size <= 65536):
            raise RuntimeError('PUBLIC_ROTATION_FILE_INVALID')
        return source.read(65537)


def sync_directory():
    fd = os.open(DEST, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def stage(path, value, uid):
    saved = read_file(path, uid)
    if saved is not None:
        if saved != value:
            raise RuntimeError('PUBLIC_ROTATION_PENDING_CHANGED')
        return
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
    with os.fdopen(fd, 'wb') as output:
        output.write(value)
        output.flush()
        os.fchown(output.fileno(), uid, uid)
        os.fsync(output.fileno())
    sync_directory()


def service(action):
    if action not in ('stop', 'start', 'is-active'):
        raise RuntimeError('PUBLIC_ROTATION_ACTION_INVALID')
    subprocess.run(  # noqa: S603 - allowlisted action and fixed service
        ['/usr/bin/systemctl', action, 'proofflow-public-api.service'],
        check=True, capture_output=True, timeout=30)


def install_pair(values, installed):
    """Caller validates chain/IP/key first. Durable roll-forward, never mixed-pair start."""
    import fcntl

    if set(values) != {'health.pem', 'health.key'}:
        raise RuntimeError('PUBLIC_ROTATION_PAIR_INVALID')
    lock = os.open(DEST / '.rotation.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(lock)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != 0o600):
            raise RuntimeError('PUBLIC_ROTATION_LOCK_INVALID')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        marker = DEST / '.rotation.json'
        target = json.dumps({n: hashlib.sha256(b).hexdigest() for n, b in values.items()},
                            sort_keys=True).encode()
        saved = read_file(marker, 0)
        if saved is not None and saved != target:
            raise RuntimeError('PUBLIC_ROTATION_TARGET_CHANGED')
        existing = {n: read_file(DEST / n, 10003) for n in values}
        pending = {n: read_file(DEST / (n + '.pending'), 10003) for n in values}
        if any(raw is not None and raw != values[n] for n, raw in pending.items()):
            raise RuntimeError('PUBLIC_ROTATION_PENDING_CHANGED')
        changed = existing != values
        if not changed and saved is None:
            if any(raw is not None for raw in pending.values()):
                raise RuntimeError('PUBLIC_ROTATION_ORPHAN_PENDING')
            return False
        stage(marker, target, 0)
        if installed:
            service('stop')
        for name, value in values.items():
            temp = DEST / (name + '.pending')
            stage(temp, value, 10003)
            os.replace(temp, DEST / name)
            sync_directory()
        if any(read_file(DEST / n, 10003) != b for n, b in values.items()):
            raise RuntimeError('PUBLIC_ROTATION_READBACK_FAILED')
        if installed:
            service('start')
            service('is-active')
        marker.unlink()
        sync_directory()
        return changed
    finally:
        os.close(lock)


def validate_pair(cert_raw, key_raw, address, now):
    cert = x509.load_pem_x509_certificate(cert_raw)
    key = serialization.load_pem_private_key(key_raw, password=None)
    def public(k):
        return k.public_bytes(serialization.Encoding.DER,
                              serialization.PublicFormat.SubjectPublicKeyInfo)
    if (public(cert.public_key()) != public(key.public_key())
            or cert.not_valid_before_utc > now
            or cert.not_valid_after_utc < now + timedelta(hours=24)
            or cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
            .value.get_values_for_type(x509.IPAddress) != [ipaddress.ip_address(address)]):
        raise RuntimeError('PUBLIC_CERTIFICATE_INVALID')
    return cert.not_valid_after_utc.isoformat()


def main():
    if os.geteuid() != 0:
        raise RuntimeError('ADMINISTRATOR_REQUIRED')
    os.umask(0o077)
    config = json.loads(Path('/etc/proofflow-public/config.json').read_bytes())
    address = str(ipaddress.IPv4Address(config['address']))
    raw = {}
    for name in ('cert.pem', 'chain.pem', 'fullchain.pem', 'privkey.pem'):
        path = (BASE / 'live/proofflow-ip' / name).resolve(strict=True)
        if not path.is_relative_to(BASE / 'archive/proofflow-ip'):
            raise RuntimeError('ACME_LINEAGE_INVALID')
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1
                or info.st_mode & 0o022 or not 1 <= info.st_size <= 32768):
            raise RuntimeError('ACME_FILE_INVALID')
        raw[name] = path.read_bytes()
    expiry = validate_pair(raw['cert.pem'], raw['privkey.pem'], address, datetime.now(UTC))
    if raw['fullchain.pem'] != raw['cert.pem'] + raw['chain.pem']:
        raise RuntimeError('ACME_CHAIN_MISMATCH')
    result = subprocess.run(  # noqa: S603 - fixed trusted certificate paths
        ['/usr/bin/openssl', 'verify', '-CAfile',
        '/etc/ssl/certs/ca-certificates.crt', '-untrusted',
        str(BASE / 'live/proofflow-ip/chain.pem'), str(BASE / 'live/proofflow-ip/cert.pem')],
        capture_output=True, timeout=10)  # noqa: S603 - fixed trusted certificate paths
    if result.returncode:
        raise RuntimeError('PUBLIC_CHAIN_UNTRUSTED')
    values = {'health.pem': raw['fullchain.pem'], 'health.key': raw['privkey.pem']}
    installed = Path('/etc/systemd/system/proofflow-public-api.service').exists()
    changed = install_pair(values, installed)
    print(json.dumps({'trusted_ip_certificate': True, 'expires_at': expiry,
                      'replaced': changed, 'private_operator_tls_changed': False}))


if __name__ == '__main__':
    main()
