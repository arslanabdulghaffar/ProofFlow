"""Vault policy and crash fixtures; ACL/DPAPI/OS locking are explicit doubles here."""

import base64
import importlib
import json
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest


@pytest.fixture
def vault(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    module = importlib.import_module("asset_backup_vault")
    monkeypatch.setattr(module, "PRIVATE", tmp_path)
    monkeypatch.setattr(module, "exclusive", nullcontext)
    monkeypatch.setattr(module, "crypt", lambda raw, decrypt=False: raw)
    current = {"now": datetime(2026, 11, 7, tzinfo=UTC)}

    class Clock(datetime):
        @classmethod
        def now(cls, zone):
            return current["now"]

    def command(program, raw, expected):
        if program == module.WRITE:
            value = json.loads(raw)
            with (tmp_path / value["name"]).open("xb") as output:
                output.write(base64.b64decode(value["bytes"]))
        else:
            assert program == module.CHECK
            if (tmp_path / raw.decode()).is_symlink():
                raise RuntimeError("UNSAFE_FIXTURE_LINK")

    monkeypatch.setattr(module, "datetime", Clock)
    monkeypatch.setattr(module, "command", command)
    return module, current


def saved(vault, seconds=30):
    module, clock = vault
    return module.save(b"inert encrypted bytes fixture", b"k" * 32,
                       clock["now"] + timedelta(seconds=seconds))


def test_clock_rollback_cannot_reopen_observed_expired_key(vault):
    module, clock = vault
    identifier = saved(vault)
    clock["now"] += timedelta(seconds=31)
    with pytest.raises(RuntimeError, match="EXPIRED"):
        module.recover(identifier)
    clock["now"] -= timedelta(seconds=30)
    with pytest.raises(RuntimeError, match="EXPIRED"):
        module.recover(identifier)
    module.expire()
    assert not list(module.PRIVATE.glob("asset-backup-*.key.dpapi"))


@pytest.mark.parametrize("part", ["key", "cipher", "partial_key", "partial_cipher"])
def test_interrupted_publication_or_retirement_is_cleaned(vault, part):
    module, _ = vault
    identifier = saved(vault)
    key = module.PRIVATE / module.filename(identifier, "key.dpapi")
    cipher = module.PRIVATE / module.filename(identifier, "pfenc")
    if part == "key":
        cipher.unlink()  # Key published, ciphertext not yet published.
    elif part == "cipher":
        key.unlink()  # Key-first retirement interrupted.
    else:
        path = key if part == "partial_key" else cipher
        if part == "partial_key":
            cipher.unlink()
        path.rename(path.with_name(path.name + ".pending"))
        path.with_name(path.name + ".pending").write_bytes(b"")
    module.expire()
    assert not list(module.PRIVATE.glob("asset-backup-" + identifier + "*"))


def test_unpublished_clock_write_is_discarded_without_losing_committed_floor(vault):
    module, clock = vault
    identifier = saved(vault)
    clock["now"] += timedelta(seconds=31)
    with pytest.raises(RuntimeError, match="EXPIRED"):
        module.recover(identifier)
    (module.PRIVATE / "asset-backup-clock.json.pending").write_bytes(b'{"observed_')
    clock["now"] -= timedelta(seconds=30)
    with pytest.raises(RuntimeError, match="EXPIRED"):
        module.recover(identifier)


@pytest.mark.parametrize("kind", ["missing", "corrupt"])
def test_missing_or_corrupt_clock_with_retained_key_denies_recovery(vault, kind):
    module, _ = vault
    identifier = saved(vault)
    path = module.PRIVATE / "asset-backup-clock.json"
    if kind == "missing":
        path.unlink()
    else:
        path.write_bytes(b"corrupt")
    with pytest.raises(RuntimeError, match="CLOCK"):
        module.recover(identifier)
    assert (module.PRIVATE / module.filename(identifier, "key.dpapi")).exists()


def test_damaged_record_does_not_defer_another_authenticated_expiry(vault):
    module, clock = vault
    bad, good = saved(vault), saved(vault)
    (module.PRIVATE / module.filename(bad, "key.dpapi")).write_bytes(b"damaged")
    clock["now"] += timedelta(seconds=31)
    with pytest.raises(RuntimeError, match="RECONCILIATION"):
        module.expire()
    assert (module.PRIVATE / module.filename(bad, "key.dpapi")).exists()
    assert not (module.PRIVATE / module.filename(good, "key.dpapi")).exists()
    with pytest.raises(RuntimeError, match="RECONCILIATION"):
        saved(vault)


def test_hardlinked_pending_file_is_not_removed(vault):
    module, _ = vault
    saved(vault)
    outside = module.PRIVATE / "outside"
    outside.write_bytes(b"private fixture")
    pending = module.PRIVATE / (module.filename(uuid4().hex, "pfenc") + ".pending")
    pending.hardlink_to(outside)
    with pytest.raises(RuntimeError, match="FILE_INVALID"):
        module.expire()
    assert pending.exists() and outside.read_bytes() == b"private fixture"


def test_ciphertext_tampering_fails_before_returning_key(vault):
    module, _ = vault
    identifier = saved(vault)
    (module.PRIVATE / module.filename(identifier, "pfenc")).write_bytes(b"changed")
    with pytest.raises(RuntimeError, match="CIPHERTEXT_CHANGED"):
        module.recover(identifier)


def test_key_expiring_during_file_read_is_not_returned(vault, monkeypatch):
    module, clock = vault
    identifier = saved(vault)
    original = module.read

    def delayed_read(identity, suffix):
        value = original(identity, suffix)
        if suffix == "pfenc":
            clock["now"] += timedelta(seconds=31)
        return value

    monkeypatch.setattr(module, "read", delayed_read)
    with pytest.raises(RuntimeError, match="EXPIRED"):
        module.recover(identifier)
    monkeypatch.setattr(module, "read", original)
    clock["now"] -= timedelta(seconds=30)
    with pytest.raises(RuntimeError, match="EXPIRED"):
        module.recover(identifier)


def test_capacity_failure_never_evicts_an_unexpired_key(vault):
    module, _ = vault
    identifiers = [saved(vault) for _ in range(8)]
    with pytest.raises(RuntimeError, match="CAPACITY"):
        saved(vault)
    assert all(module.recover(i)[1] == b"k" * 32 for i in identifiers)
