"""Short-lived guest credentials: CurrentUser DPAPI and existing owner-only ACL helpers."""

import base64
import json
import re
import sys
from datetime import UTC, datetime
from uuid import UUID

from asset_backup_vault import CHECK, WRITE, command
from check_product_integrity import crypt
from vultr_phase1 import PRIVATE, ROOT

sys.path.insert(0, str(ROOT))
from api.app.auth import csrf_digest, session_digest  # noqa: E402


def validate(value, now):
    if (
        set(value) != {"window_id", "workspace_id", "expires_at", "origin", "token", "csrf"}
        or value["origin"] != "https://158.247.227.66:8443"
        or any(str(UUID(value[k])) != value[k] for k in ("window_id", "workspace_id"))
        or value["token"] == value["csrf"]
        or datetime.fromisoformat(value["expires_at"]) <= now
    ):
        raise RuntimeError("GUEST_ACCESS_INVALID_OR_EXPIRED")
    session_digest(value['token'])
    csrf_digest(value['csrf'])


def save(value):
    validate(value, datetime.now(UTC))
    name = "guest-demo-" + UUID(value["window_id"]).hex + ".key.dpapi"
    encrypted = crypt(json.dumps(value).encode())
    command(
        WRITE.replace("asset-backup-", "guest-demo-"),
        json.dumps({"name": name, "bytes": base64.b64encode(encrypted).decode()}).encode(),
        b"stored",
    )
    load(name)
    return name


def load(name):
    if re.fullmatch(r"guest-demo-[a-f0-9]{32}\.key\.dpapi", name) is None:
        raise RuntimeError("GUEST_ACCESS_FILENAME_INVALID")
    command(CHECK.replace("asset-backup-", "guest-demo-"), name.encode(), b"safe")
    path = PRIVATE / name
    if not 1 <= path.stat().st_size <= 8192:
        raise RuntimeError("GUEST_ACCESS_SIZE_INVALID")
    value = json.loads(crypt(path.read_bytes(), decrypt=True))
    validate(value, datetime.now(UTC))
    return value
