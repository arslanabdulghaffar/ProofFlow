"""Current-user Windows off-VM encrypted backup storage, outside Git.

AES keys have their own DPAPI envelope and explicit owner-only ACL. This is not
cross-profile disaster recovery; no key is printed, placed in argv, or in a dump.
"""

import base64
import hashlib
import json
import os
import re
import stat
import subprocess
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from check_product_integrity import crypt
from vultr_phase1 import PRIVATE

WRITE = r"""
$ErrorActionPreference='Stop'
$root=Join-Path $env:USERPROFILE '.proofflow\deployment'
$sid=[Security.Principal.WindowsIdentity]::GetCurrent().User
$value=[Console]::In.ReadToEnd()|ConvertFrom-Json
$pattern='^asset-backup-([a-f0-9]{32}\.(key\.dpapi|pfenc)(\.pending)?|'+
 'vault\.lock|clock\.json(\.pending)?)$'
if($value.name -notmatch $pattern){throw 'name'}
foreach($path in @((Split-Path -Parent $root),$root)){
 $i=Get-Item -LiteralPath $path -Force
 if(-not $i.PSIsContainer -or ($i.Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'path'}
}
$parentAcl=[IO.Directory]::GetAccessControl($root)
if($parentAcl.GetOwner([Security.Principal.SecurityIdentifier]).Value -ne $sid.Value){throw 'owner'}
foreach($r in $parentAcl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])){
 if($r.IdentityReference.Value -notin @($sid.Value,'S-1-5-18')){throw 'scope'}
}
$acl=[Security.AccessControl.FileSecurity]::new()
$acl.SetOwner($sid);$acl.SetAccessRuleProtection($true,$false)
foreach($s in @($sid,[Security.Principal.SecurityIdentifier]::new('S-1-5-18'))){
 $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new($s,'FullControl','Allow'))
}
$bytes=[Convert]::FromBase64String($value.bytes)
$f=[IO.FileStream]::new((Join-Path $root $value.name),[IO.FileMode]::CreateNew,
 [Security.AccessControl.FileSystemRights]::Write,[IO.FileShare]::None,4096,[IO.FileOptions]::None,$acl)
try{$f.Write($bytes,0,$bytes.Length);$f.Flush($true)}finally{$f.Dispose()}
[Console]::Write('stored')
"""
CHECK = r"""
$ErrorActionPreference='Stop'
$root=Join-Path $env:USERPROFILE '.proofflow\deployment'
$sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$name=[Console]::In.ReadToEnd()
$pattern='^asset-backup-([a-f0-9]{32}\.(key\.dpapi|pfenc)(\.pending)?|'+
 'vault\.lock|clock\.json(\.pending)?)$'
if($name -notmatch $pattern){throw 'name'}
foreach($p in @((Split-Path -Parent $root),$root,(Join-Path $root $name))){
 $i=Get-Item -LiteralPath $p -Force
 if($i.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'path'}
 if($i.PSIsContainer){$acl=[IO.Directory]::GetAccessControl($p)}
 else{$acl=[IO.File]::GetAccessControl($p)}
 $allowed=@($sid,'S-1-5-18');$owners=@($sid)
 if($p -eq (Split-Path -Parent $root)){
  $allowed+= 'S-1-5-32-544';$owners+= 'S-1-5-32-544'
 }
 if($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -notin $owners){throw 'owner'}
 foreach($r in $acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])){
  if($r.IdentityReference.Value -notin $allowed){throw 'scope'}
 }
}
[Console]::Write('safe')
"""


def command(script, raw, expected):
    result = subprocess.run(  # noqa: S603 - fixed ACL program; secret bytes via stdin only
        [
            "C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-EncodedCommand",
            base64.b64encode(script.encode("utf-16le")).decode(),
        ],
        input=raw,
        capture_output=True,
        timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if result.returncode or result.stdout != expected:
        raise RuntimeError("ASSET_BACKUP_PRIVATE_STORAGE_FAILED")


def filename(identifier, suffix):
    if not re.fullmatch(r"[a-f0-9]{32}", identifier) or suffix not in ("key.dpapi", "pfenc"):
        raise RuntimeError("ASSET_BACKUP_NAME_INVALID")
    return "asset-backup-" + identifier + "." + suffix


def checked_path(name, limit, *, empty=False):
    command(CHECK, name.encode(), b"safe")
    path = PRIVATE / name
    info = path.lstat()
    minimum = 0 if empty else 1
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not minimum <= info.st_size <= limit:
        raise RuntimeError("ASSET_BACKUP_FILE_INVALID")
    return path


def read(identifier, suffix):
    limit = 8192 if suffix == "key.dpapi" else 64 * 1024 * 1024
    path = checked_path(filename(identifier, suffix), limit)
    return path.read_bytes()


def write_private(name, raw):
    command(
        WRITE,
        json.dumps({"name": name, "bytes": base64.b64encode(raw).decode()}).encode(),
        b"stored",
    )


@contextmanager
def exclusive():
    """Shared by every vault operation; OS releases this lock after process death."""
    import msvcrt

    name = "asset-backup-vault.lock"
    if not (PRIVATE / name).exists():
        try:
            write_private(name, b"0")
        except RuntimeError:
            if not (PRIVATE / name).exists():
                raise
    path = checked_path(name, 1)
    with path.open("r+b") as handle:
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise RuntimeError("ASSET_BACKUP_VAULT_BUSY") from None
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def atomic_write(name, raw, *, replace=False):
    pending = name + ".pending"
    write_private(pending, raw)  # CreateNew + private ACL + Flush(true).
    source = checked_path(pending, max(8192, len(raw)))
    destination = PRIVATE / name
    if replace:
        if destination.exists():
            checked_path(name, 8192)
        os.replace(source, destination)
    else:
        # On Windows rename refuses an existing destination; never overwrite a key.
        source.rename(destination)


def observed_time():
    """Persistent floor prevents a clock rollback reviving an observed-expired key.

    The file is not a disaster checkpoint: do not restore/roll it back with a backup.
    Missing/corrupt floor with any retained backup fails closed.
    """
    name = "asset-backup-clock.json"
    pending = PRIVATE / (name + ".pending")
    if pending.exists():
        # No key is returned/expired until atomic publication of this floor.
        # An unpublished interrupted update therefore conferred no authority.
        checked_path(pending.name, 8192, empty=True).unlink()
    now = datetime.now(UTC)
    if (PRIVATE / name).exists():
        try:
            value = json.loads(checked_path(name, 8192).read_bytes())
            if type(value) is not dict or set(value) != {"observed_at"}:
                raise ValueError
            prior = datetime.fromisoformat(value["observed_at"])
            if prior.tzinfo is None:
                raise ValueError
        except (ValueError, TypeError, KeyError):
            raise RuntimeError("ASSET_BACKUP_CLOCK_INVALID") from None
        now = max(prior, now)
    elif any(PRIVATE.glob("asset-backup-*.key.dpapi*")) or any(
        PRIVATE.glob("asset-backup-*.pfenc*")
    ):
        raise RuntimeError("ASSET_BACKUP_CLOCK_REQUIRED")
    atomic_write(name, json.dumps({"observed_at": now.isoformat()}).encode(), replace=True)
    return now


def key_record(identifier):
    try:
        value = json.loads(crypt(read(identifier, "key.dpapi"), True))
    except (ValueError, UnicodeError):
        raise RuntimeError("ASSET_BACKUP_KEY_RECORD_INVALID") from None
    if (
        type(value) is not dict
        or set(value) != {"kind", "id", "created", "expires", "sha256", "key"}
        or any(type(v) is not str for v in value.values())
        or value["kind"] != "ProofFlowAssetKeyV1"
        or value["id"] != identifier
        or not re.fullmatch(r"[a-f0-9]{64}", value["sha256"])
    ):
        raise RuntimeError("ASSET_BACKUP_KEY_RECORD_INVALID")
    try:
        created, expires = (datetime.fromisoformat(value[k]) for k in ("created", "expires"))
        if len(base64.b64decode(value["key"], validate=True)) != 32:
            raise ValueError
    except ValueError:
        raise RuntimeError("ASSET_BACKUP_KEY_RECORD_INVALID") from None
    if (
        created.tzinfo is None
        or expires.tzinfo is None
        or not created < expires <= created + timedelta(hours=24)
    ):
        raise RuntimeError("ASSET_BACKUP_KEY_EXPIRY_INVALID")
    return value


def _save(envelope, key, expires, now):
    if len(key) != 32 or not 0 < len(envelope) <= 64 * 1024 * 1024:
        raise RuntimeError("ASSET_BACKUP_LIMIT")
    _expire(now)
    if len(list(PRIVATE.glob("asset-backup-*.key.dpapi"))) >= 8:
        raise RuntimeError("ASSET_BACKUP_CAPACITY")
    identifier = uuid4().hex
    if expires.tzinfo is None or not now < expires <= now + timedelta(hours=24):
        raise RuntimeError("ASSET_BACKUP_KEY_EXPIRY_INVALID")
    record = {
        "kind": "ProofFlowAssetKeyV1",
        "id": identifier,
        "created": now.isoformat(),
        "expires": expires.isoformat(),
        "sha256": hashlib.sha256(envelope).hexdigest(),
        "key": base64.b64encode(key).decode(),
    }
    for suffix, raw in (("key.dpapi", crypt(json.dumps(record).encode())), ("pfenc", envelope)):
        atomic_write(filename(identifier, suffix), raw)
    return identifier


def _recover(identifier, now):
    record = key_record(identifier)
    if (
        not datetime.fromisoformat(record["created"])
        <= now
        < datetime.fromisoformat(record["expires"])
    ):
        raise RuntimeError("ASSET_BACKUP_EXPIRED")
    envelope = read(identifier, "pfenc")
    if hashlib.sha256(envelope).hexdigest() != record["sha256"]:
        raise RuntimeError("ASSET_BACKUP_CIPHERTEXT_CHANGED")
    key = base64.b64decode(record["key"], validate=True)
    if len(key) != 32:
        raise RuntimeError("ASSET_BACKUP_KEY_INVALID")
    # DPAPI and file reads take time. A valid-at-entry key may have expired while
    # those operations ran; persist that observation before denying the return.
    if max(now, datetime.now(UTC)) >= datetime.fromisoformat(record["expires"]):
        observed_time()
        raise RuntimeError("ASSET_BACKUP_EXPIRED")
    return envelope, key


def _retire(identifier):
    # Scoped file deletion only, no recursion; key first, encrypted bytes second.
    for suffix in ("key.dpapi", "pfenc"):
        path = PRIVATE / filename(identifier, suffix)
        if path.exists():
            limit = 8192 if suffix == "key.dpapi" else 64 * 1024 * 1024
            checked_path(path.name, limit).unlink()


def _expire(now):
    pending = list(PRIVATE.glob("asset-backup-*.pending"))
    if len(pending) > 16:
        raise RuntimeError("ASSET_BACKUP_INVENTORY_INVALID")
    for path in pending:
        if not re.fullmatch(r"asset-backup-[a-f0-9]{32}\.(key\.dpapi|pfenc)\.pending", path.name):
            raise RuntimeError("ASSET_BACKUP_PENDING_INVALID")
        limit = 8192 if ".key.dpapi." in path.name else 64 * 1024 * 1024
        checked_path(path.name, limit, empty=True).unlink()
    count = 0
    ciphertexts = list(PRIVATE.glob("asset-backup-*.pfenc"))
    if len(ciphertexts) > 8:
        raise RuntimeError("ASSET_BACKUP_INVENTORY_INVALID")
    for path in ciphertexts:
        match = re.fullmatch(r"asset-backup-([a-f0-9]{32})\.pfenc", path.name)
        if match is None:
            raise RuntimeError("ASSET_BACKUP_INVENTORY_INVALID")
        if not (PRIVATE / filename(match[1], "key.dpapi")).exists():
            # Interrupted key-first retirement. The encrypted orphan has no key
            # in this vault; finish only after the same ACL/file safety checks.
            read(match[1], "pfenc")
            path.unlink()
    damaged = False
    for path in sorted(PRIVATE.glob("asset-backup-*.key.dpapi")):
        match = re.fullmatch(r"asset-backup-([a-f0-9]{32})\.key\.dpapi", path.name)
        if match is None or count >= 8:
            raise RuntimeError("ASSET_BACKUP_INVENTORY_INVALID")
        identifier = match[1]
        try:
            if not (PRIVATE / filename(identifier, "pfenc")).exists():
                # Interrupted key-first save: the lock excludes a live writer.
                _retire(identifier)
            else:
                record = key_record(identifier)
                if now >= datetime.fromisoformat(record["expires"]):
                    _retire(identifier)
        except (RuntimeError, ValueError, TypeError, KeyError):
            # A damaged backup blocks new saves but must not defer unrelated,
            # authenticated expirations. Never erase its unknown key by guessing.
            damaged = True
        count += 1
    if damaged:
        raise RuntimeError("ASSET_BACKUP_RECORD_RECONCILIATION_REQUIRED")
    return count


def save(envelope, key, expires):
    with exclusive():
        return _save(envelope, key, expires, observed_time())


def recover(identifier):
    with exclusive():
        return _recover(identifier, observed_time())


def retire(identifier):
    with exclusive():
        _retire(identifier)


def expire():
    with exclusive():
        return _expire(observed_time())


if __name__ == "__main__":
    print(json.dumps({"asset_backup_expiry": "checked", "key_records_checked": expire()}))
