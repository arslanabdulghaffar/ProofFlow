"""Password-protected transport for synthetic recovery, independent of Windows DPAPI.

No password/DEK persistence. Current deletion authority is still mandatory. Offline
copies cannot promise cryptographic erasure by a remote scheduler: custody/expiry of
exported kits is the operator's responsibility, not a guest-retention guarantee.
"""

import hashlib
import os
from datetime import datetime

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from orchestrator.asset_backup import MAX_ENVELOPE, open_backup, select_recovery
from orchestrator.restore_guard import RestoreError, inventory, timestamp

MAGIC = b"ProofFlow-portable-v1\x00"
HEADER = len(MAGIC) + 16 + 12 + 48


def derive(password, salt):
    if type(password) is not bytes or not 24 <= len(password) <= 256:
        raise RestoreError("PORTABLE_PASSWORD_LENGTH")
    return Scrypt(salt=salt, length=32, n=2**17, r=8, p=1).derive(password)


def export_portable(envelope: bytes, key: bytes, password: bytes, *, now: datetime) -> bytes:
    open_backup(envelope, key, now=now)
    salt, nonce = os.urandom(16), os.urandom(12)
    associated = MAGIC + hashlib.sha256(envelope).digest()
    wrapped = AESGCM(derive(password, salt)).encrypt(nonce, key, associated)
    return MAGIC + salt + nonce + wrapped + envelope


def recover_portable(package: bytes, password: bytes, current: dict, *, now: datetime):
    # A portable file is never itself proof that deletion/revocation did not occur.
    inventory(current)
    age = (now - timestamp(current["observed_at"])).total_seconds()
    if not 0 <= age <= 60:
        raise RestoreError("PORTABLE_CURRENT_AUTHORITY_STALE")
    if (type(package) is not bytes or not HEADER < len(package) <= HEADER + MAX_ENVELOPE
            or not package.startswith(MAGIC)):
        raise RestoreError("PORTABLE_FORMAT_INVALID")
    offset = len(MAGIC)
    salt, nonce = package[offset:offset+16], package[offset+16:offset+28]
    wrapped, envelope = package[offset+28:HEADER], package[HEADER:]
    try:
        key = AESGCM(derive(password, salt)).decrypt(
            nonce, wrapped, MAGIC + hashlib.sha256(envelope).digest())
    except InvalidTag:
        raise RestoreError("PORTABLE_AUTHENTICATION_FAILED") from None
    payload = open_backup(envelope, key, now=now)
    plan, assets = select_recovery(payload, current, now=now)
    return payload, plan, assets
