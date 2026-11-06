"""Current-user Windows off-VM encrypted backup storage, outside Git.

AES keys have their own DPAPI envelope and explicit owner-only ACL. This is not
cross-profile disaster recovery; no key is printed, placed in argv, or in a dump.
"""

import base64
import hashlib
import json
import re
import stat
import subprocess
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from check_product_integrity import crypt
from vultr_phase1 import PRIVATE

WRITE = r"""
$ErrorActionPreference='Stop'
$root=Join-Path $env:USERPROFILE '.proofflow\deployment'
$sid=[Security.Principal.WindowsIdentity]::GetCurrent().User
$value=[Console]::In.ReadToEnd()|ConvertFrom-Json
if($value.name -notmatch '^asset-backup-[a-f0-9]{32}\.(key\.dpapi|pfenc)$'){throw 'name'}
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
if($name -notmatch '^asset-backup-[a-f0-9]{32}\.(key\.dpapi|pfenc)$'){throw 'name'}
foreach($p in @($root,(Join-Path $root $name))){
 $i=Get-Item -LiteralPath $p -Force
 if($i.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'path'}
 if($i.PSIsContainer){$acl=[IO.Directory]::GetAccessControl($p)}
 else{$acl=[IO.File]::GetAccessControl($p)}
 if($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -ne $sid){throw 'owner'}
 foreach($r in $acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])){
  if($r.IdentityReference.Value -notin @($sid,'S-1-5-18')){throw 'scope'}
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


def read(identifier, suffix):
    name = filename(identifier, suffix)
    command(CHECK, name.encode(), b"safe")
    path = PRIVATE / name
    info = path.lstat()
    limit = 8192 if suffix == "key.dpapi" else 64 * 1024 * 1024
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not 0 < info.st_size <= limit:
        raise RuntimeError("ASSET_BACKUP_FILE_INVALID")
    return path.read_bytes()


def key_record(identifier):
    value = json.loads(crypt(read(identifier, "key.dpapi"), True))
    if (
        set(value) != {"kind", "id", "created", "expires", "sha256", "key"}
        or value["kind"] != "ProofFlowAssetKeyV1"
        or value["id"] != identifier
    ):
        raise RuntimeError("ASSET_BACKUP_KEY_RECORD_INVALID")
    created, expires = (datetime.fromisoformat(value[k]) for k in ("created", "expires"))
    if (
        created.tzinfo is None
        or expires.tzinfo is None
        or not created < expires <= created + timedelta(hours=24)
    ):
        raise RuntimeError("ASSET_BACKUP_KEY_EXPIRY_INVALID")
    return value


def save(envelope, key, expires):
    if len(key) != 32 or not 0 < len(envelope) <= 64 * 1024 * 1024:
        raise RuntimeError("ASSET_BACKUP_LIMIT")
    expire()
    if len(list(PRIVATE.glob("asset-backup-*.key.dpapi"))) >= 8:
        raise RuntimeError("ASSET_BACKUP_CAPACITY")
    identifier, now = uuid4().hex, datetime.now(UTC)
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
        command(
            WRITE,
            json.dumps(
                {"name": filename(identifier, suffix), "bytes": base64.b64encode(raw).decode()}
            ).encode(),
            b"stored",
        )
    return identifier


def recover(identifier):
    record = key_record(identifier)
    now = datetime.now(UTC)
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
    return envelope, key


def retire(identifier):
    # Scoped file deletion only, no recursion; key first, encrypted bytes second.
    for suffix in ("key.dpapi", "pfenc"):
        path = PRIVATE / filename(identifier, suffix)
        if path.exists():
            read(identifier, suffix)  # Revalidate ACL/type/link/size immediately before unlink.
            path.unlink()


def expire():
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
    for path in sorted(PRIVATE.glob("asset-backup-*.key.dpapi")):
        match = re.fullmatch(r"asset-backup-([a-f0-9]{32})\.key\.dpapi", path.name)
        if match is None or count >= 8:
            raise RuntimeError("ASSET_BACKUP_INVENTORY_INVALID")
        identifier = match[1]
        record = key_record(identifier)
        if datetime.now(UTC) >= datetime.fromisoformat(record["expires"]):
            retire(identifier)
        count += 1
    return count


if __name__ == "__main__":
    print(json.dumps({"asset_backup_expiry": "checked", "key_records_checked": expire()}))
