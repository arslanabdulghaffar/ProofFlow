"""One trusted HTTPS authority; request headers never configure routing or origin."""

import ipaddress
import json
import os
import re
import stat
from pathlib import Path
from urllib.parse import urlsplit

from api.app.auth import AuthError, _origin

PRIVATE_ORIGIN = "https://127.0.0.1:18443"
ORIGIN_FILE = Path("/etc/proofflow-product/tls/origin.json")


def authority(origin):
    _origin(origin)
    parsed = urlsplit(origin)
    host = parsed.hostname
    try:
        address = ipaddress.ip_address(host)
        canonical = f"[{address}]" if address.version == 6 else str(address)
    except ValueError:
        if not all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                   for label in host.split(".")):
            raise AuthError("ORIGIN_CONFIGURATION_INVALID") from None
        canonical = host
    if parsed.port not in (None, 443):
        canonical += ":" + str(parsed.port)
    if origin != "https://" + canonical:
        raise AuthError("ORIGIN_CONFIGURATION_INVALID")
    return canonical.encode("ascii")


def load_origin(path=ORIGIN_FILE):
    """Optional admin-installed file on the existing read-only TLS mount.

    Absence preserves private mode. Invalid/symlink/writable configuration stops
    startup; it never silently falls back or reads an environment/request value.
    """
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return PRIVATE_ORIGIN
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid not in (0, 10003)
                or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o400
                or not 0 < info.st_size <= 512):
            raise AuthError("ORIGIN_FILE_INVALID")
        raw = os.read(fd, 513)
        value = json.loads(raw)
        if type(value) is not dict or set(value) != {"origin"}:
            raise AuthError("ORIGIN_FILE_INVALID")
        authority(value["origin"])
        return value["origin"]
    except (ValueError, UnicodeError):
        raise AuthError("ORIGIN_FILE_INVALID") from None
    finally:
        os.close(fd)


def check_ingress(scope, expected_authority):
    headers = scope.get("headers", [])
    if scope.get("scheme") != "https" or len(headers) > 64:
        return False
    hosts = []
    total = 0
    for name, value in headers:
        name = name.lower()
        total += len(name) + len(value)
        if (total > 16384 or len(value) > 8192
                or any(char in value for char in (b"\r", b"\n", b"\x00"))
                or name == b"forwarded" or name.startswith(b"x-forwarded-")):
            return False
        if name == b"host":
            hosts.append(value)
    return hosts == [expected_authority]
