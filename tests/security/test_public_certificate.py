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
