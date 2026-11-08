"""Root-only fixed ACME deploy hook; validate before replacing guest TLS files."""

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
    changed = any(not (DEST / n).exists() or (DEST / n).read_bytes() != b
                  for n, b in values.items())
    installed = Path('/etc/systemd/system/proofflow-public-api.service').exists()
    if changed:
        if installed:
            subprocess.run(['/usr/bin/systemctl', 'stop', 'proofflow-public-api.service'],
                           check=True, timeout=30)  # noqa: S603
        for name, value in values.items():
            temp = DEST / (name + '.pending')
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
            with os.fdopen(fd, 'wb') as output:
                output.write(value)
                output.flush()
                os.fchown(output.fileno(), 10003, 10003)
                os.fsync(output.fileno())
            os.replace(temp, DEST / name)
        directory = os.open(DEST, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        if installed:
            subprocess.run(['/usr/bin/systemctl', 'start', 'proofflow-public-api.service'],
                           check=True, timeout=30)  # noqa: S603
    print(json.dumps({'trusted_ip_certificate': True, 'expires_at': expiry,
                      'replaced': changed, 'private_operator_tls_changed': False}))


if __name__ == '__main__':
    main()
