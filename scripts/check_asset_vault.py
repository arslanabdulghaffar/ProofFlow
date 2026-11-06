"""Actual Windows private-ACL/DPAPI and natural short key-expiry fixture; no cloud."""

import hashlib
import json
import time
from datetime import UTC, datetime, timedelta

from asset_backup_vault import PRIVATE, expire, filename, recover, retire, save
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def main():
    identifier = None
    raw = b"INERT_SYNTHETIC_ENCRYPTED_ASSET_VAULT_FIXTURE"
    key = AESGCM.generate_key(bit_length=256)
    # Actual AES ciphertext, never a candidate program or account credential.
    nonce = b"single-use-test"[:12]
    ciphertext = AESGCM(key).encrypt(nonce, raw, b"vault-fixture-v1")
    try:
        deadline = datetime.now(UTC) + timedelta(seconds=8)
        identifier = save(ciphertext, key, deadline)
        returned, restored_key = recover(identifier)
        if returned != ciphertext or restored_key != key:
            raise RuntimeError("VAULT_ROUNDTRIP_CHANGED")
        if raw in (PRIVATE / filename(identifier, "pfenc")).read_bytes():
            raise RuntimeError("VAULT_PLAINTEXT_FOUND")
        if AESGCM(restored_key).decrypt(nonce, returned, b"vault-fixture-v1") != raw:
            raise RuntimeError("VAULT_DECRYPTION_CHANGED")
        while datetime.now(UTC) < deadline:
            time.sleep(0.2)
        try:
            recover(identifier)
        except RuntimeError as error:
            if str(error) != "ASSET_BACKUP_EXPIRED":
                raise
        else:
            raise RuntimeError("VAULT_EXPIRED_KEY_ACCEPTED")
        expire()
        if any(
            (PRIVATE / filename(identifier, suffix)).exists() for suffix in ("key.dpapi", "pfenc")
        ):
            raise RuntimeError("VAULT_EXPIRED_FILES_REMAIN")
        print(
            json.dumps(
                {
                    "scope": "actual_windows_private_acl_dpapi_inert_fixture",
                    "roundtrip": "passed",
                    "natural_expiry_seconds": 8,
                    "expired_recovery": "denied",
                    "key_and_ciphertext_removed": True,
                    "fixture_ciphertext_sha256": hashlib.sha256(ciphertext).hexdigest(),
                    "cloud_calls": 0,
                    "portable_key_recovery": "NOT_IMPLEMENTED",
                }
            )
        )
    finally:
        if identifier is not None:
            retire(identifier)


if __name__ == "__main__":
    main()
