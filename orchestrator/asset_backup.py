"""Bounded authenticated data-only backup; no SQL/code execution or live promotion.

The trusted coordinator supplies a consistent registry/byte snapshot and a fresh
256-bit key per backup. Keys are stored separately, never inside this envelope.
Current restore authority must come from the live authenticated control plane.
"""

import base64
import hashlib
import json
import os
from datetime import datetime, timedelta

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from orchestrator.restore_guard import RestoreError, check_dump, inventory, plan_restore, timestamp

MAGIC = b"ProofFlow-asset-backup-v1\x00"
MAX_ENVELOPE = 64 * 1024 * 1024
MAX_OBJECTS = 256
MAX_ASSET = 10 * 1024 * 1024


def _key(key):
    if type(key) is not bytes or len(key) != 32:
        raise RestoreError("BACKUP_KEY_INVALID")
    return AESGCM(key)


def _decode(value, maximum):
    if type(value) is not str or len(value) > (maximum + 2) // 3 * 4:
        raise RestoreError("BACKUP_OBJECT_LIMIT")
    try:
        raw = base64.b64decode(value, validate=True)
    except ValueError:
        raise RestoreError("BACKUP_ENCODING_INVALID") from None
    if not 0 < len(raw) <= maximum:
        raise RestoreError("BACKUP_OBJECT_LIMIT")
    return raw


def _validate(payload, now):
    if type(payload) is not dict or set(payload) != {
        "snapshot", "expires_at", "database", "database_sha256", "assets"
    }:
        raise RestoreError("BACKUP_MANIFEST_INVALID")
    workspaces = inventory(payload["snapshot"])
    captured = timestamp(payload["snapshot"]["observed_at"])
    expiry = timestamp(payload["expires_at"])
    if now.tzinfo is None or not captured <= now < expiry <= captured + timedelta(hours=24):
        raise RestoreError("BACKUP_EXPIRED_OR_CLOCK_INVALID")
    dump = _decode(payload["database"], 16 * 1024 * 1024)
    check_dump(dump, payload["database_sha256"])
    assets, seen, decoded = payload["assets"], set(), []
    if type(assets) is not list or len(assets) > MAX_OBJECTS:
        raise RestoreError("BACKUP_ASSET_COUNT_LIMIT")
    for asset in assets:
        if type(asset) is not dict or set(asset) != {
            "workspace", "sha256", "created_at", "bytes"
        }:
            raise RestoreError("BACKUP_ASSET_INVALID")
        workspace, digest = asset["workspace"], asset["sha256"]
        if type(workspace) is not str or workspace not in workspaces or type(digest) is not str:
            raise RestoreError("BACKUP_ASSET_SCOPE_INVALID")
        key = (workspace, digest)
        if key in seen:
            raise RestoreError("BACKUP_ASSET_DUPLICATE")
        seen.add(key)
        raw = _decode(asset["bytes"], MAX_ASSET)
        if hashlib.sha256(raw).hexdigest() != digest:
            raise RestoreError("BACKUP_ASSET_DIGEST_INVALID")
        created = timestamp(asset["created_at"])
        if not workspaces[workspace][0] <= created <= captured:
            raise RestoreError("BACKUP_ASSET_TIMESTAMP_INVALID")
        if expiry > created + timedelta(hours=48):
            raise RestoreError("BACKUP_RAW_EXPOSURE_LIMIT")
        decoded.append((workspace, digest, raw))
    return dump, decoded


def seal(snapshot: dict, assets: list[dict], database: bytes, key: bytes,
         *, now: datetime) -> bytes:
    """Assets contain raw bytes and registry timestamps, never caller-selected paths."""
    if type(database) is not bytes or not 0 < len(database) <= 16 * 1024 * 1024:
        raise RestoreError("BACKUP_DATABASE_LIMIT")
    if type(assets) is not list or len(assets) > MAX_OBJECTS:
        raise RestoreError("BACKUP_ASSET_COUNT_LIMIT")
    total = len(database)
    entries = []
    expiry = timestamp(snapshot["observed_at"]) + timedelta(hours=24)
    for asset in assets:
        if type(asset) is not dict or set(asset) != {"workspace", "sha256", "created_at", "bytes"}:
            raise RestoreError("BACKUP_ASSET_INVALID")
        raw = asset["bytes"]
        if type(raw) is not bytes or not 0 < len(raw) <= MAX_ASSET:
            raise RestoreError("BACKUP_OBJECT_LIMIT")
        total += len(raw)
        if total > MAX_ENVELOPE // 2:
            raise RestoreError("BACKUP_TOTAL_LIMIT")
        expiry = min(expiry, timestamp(asset["created_at"]) + timedelta(hours=48))
        entries.append({**asset, "bytes": base64.b64encode(raw).decode("ascii")})
    payload = {"snapshot": snapshot, "expires_at": expiry.isoformat(),
               "database": base64.b64encode(database).decode("ascii"),
               "database_sha256": hashlib.sha256(database).hexdigest(), "assets": entries}
    _validate(payload, now)
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    if len(raw) > MAX_ENVELOPE - len(MAGIC) - 28:
        raise RestoreError("BACKUP_TOTAL_LIMIT")
    nonce = os.urandom(12)
    return MAGIC + nonce + _key(key).encrypt(nonce, raw, MAGIC)


def open_backup(envelope: bytes, key: bytes, *, now: datetime) -> dict:
    """Authenticate before parsing; return no bytes on corruption or expiry."""
    if (type(envelope) is not bytes or not len(MAGIC) + 28 < len(envelope) <= MAX_ENVELOPE
            or not envelope.startswith(MAGIC)):
        raise RestoreError("BACKUP_ENVELOPE_INVALID")
    offset = len(MAGIC)
    try:
        raw = _key(key).decrypt(envelope[offset:offset+12], envelope[offset+12:], MAGIC)
        payload = json.loads(raw)
    except (InvalidTag, ValueError, UnicodeError, RecursionError):
        raise RestoreError("BACKUP_AUTHENTICATION_OR_FORMAT_FAILED") from None
    _validate(payload, now)
    return payload


def select_recovery(payload: dict, current: dict, *, now: datetime) -> tuple[dict, list]:
    """Data-only selection; a coordinator must revalidate authority before export."""
    _, assets = _validate(payload, now)
    plan = plan_restore(payload["snapshot"], current, now=now)
    return plan, [(w, digest, raw) for w, digest, raw in assets if w in plan["keep"]]
