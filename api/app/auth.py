"""Opaque browser credentials and strict request extraction; no cached authority.

Database authorization/expiry/revocation is required for every operation after
these checks. No public route, role promotion or login bootstrap is created here.
"""

import hashlib
import re
import secrets
from dataclasses import dataclass, field
from urllib.parse import urlsplit

COOKIE_NAME = "__Host-proofflow"
TOKEN = re.compile(r"pf_s_[0-9a-f]{64}", re.ASCII)
CSRF = re.compile(r"pf_c_[0-9a-f]{64}", re.ASCII)


class AuthError(Exception):
    """Fixed public diagnostic without cookie, token or request-header bytes."""


def session_digest(value: str) -> str:
    if type(value) is not str or TOKEN.fullmatch(value) is None:
        raise AuthError("AUTH_REQUIRED")
    return hashlib.sha256(b"proofflow/session/v1\x00" + value.encode("ascii")).hexdigest()


def csrf_digest(value: str) -> str:
    if type(value) is not str or CSRF.fullmatch(value) is None:
        raise AuthError("CSRF_REQUIRED")
    return hashlib.sha256(b"proofflow/csrf/v1\x00" + value.encode("ascii")).hexdigest()


@dataclass(frozen=True)
class SessionSecrets:
    token: str = field(repr=False)
    csrf: str = field(repr=False)

    @classmethod
    def create(cls):
        return cls("pf_s_" + secrets.token_hex(32), "pf_c_" + secrets.token_hex(32))

    def cookie(self, *, max_age: int) -> str:
        session_digest(self.token)
        if type(max_age) is not int or not 1 <= max_age <= 43200:
            raise AuthError("SESSION_EXPIRY_INVALID")
        # __Host forbids Domain and requires Secure and Path=/.
        return (f"{COOKIE_NAME}={self.token}; Path=/; Max-Age={max_age}; "
                "Secure; HttpOnly; SameSite=Strict")


def _origin(value):
    if type(value) is not str or not 1 <= len(value) <= 256:
        raise AuthError("ORIGIN_CONFIGURATION_INVALID")
    if not value.isascii() or any(char.isspace() or ord(char) < 32 for char in value):
        raise AuthError("ORIGIN_CONFIGURATION_INVALID")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise AuthError("ORIGIN_CONFIGURATION_INVALID") from None
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.path or parsed.query or parsed.fragment
            or (port is not None and not 1 <= port <= 65535) or "\\" in value):
        raise AuthError("ORIGIN_CONFIGURATION_INVALID")


def request_digests(headers: list[tuple[bytes, bytes]], *, expected_origin: str,
                    writing: bool) -> tuple[str, str | None]:
    """Use raw ASGI headers so duplicates cannot disappear before validation.

    expected_origin is fixed trusted deployment config, never Host/Forwarded.
    This checks possession/CSRF framing only; it does NOT authorize a workspace.
    """
    _origin(expected_origin)
    if type(writing) is not bool or type(headers) is not list or len(headers) > 64:
        raise AuthError("AUTH_HEADERS_INVALID")
    found = {}
    total = 0
    for pair in headers:
        if (type(pair) is not tuple or len(pair) != 2
                or type(pair[0]) is not bytes or type(pair[1]) is not bytes):
            raise AuthError("AUTH_HEADERS_INVALID")
        name, value = pair
        total += len(name) + len(value)
        if total > 16384 or len(value) > 8192:
            raise AuthError("AUTH_HEADERS_INVALID")
        name = name.lower()
        if name in (b"cookie", b"origin", b"x-proofflow-csrf", b"sec-fetch-site"):
            if name in found or b"\r" in value or b"\n" in value or b"\x00" in value:
                raise AuthError("AUTH_HEADERS_INVALID")
            found[name] = value
    if found.get(b"sec-fetch-site", b"same-origin") not in (b"same-origin", b"none"):
        raise AuthError("CROSS_SITE_REQUEST")
    raw_cookie = found.get(b"cookie", b"")
    if len(raw_cookie) > 4096:
        raise AuthError("AUTH_HEADERS_INVALID")
    try:
        cookies = {}
        for part in raw_cookie.decode("ascii", errors="strict").split(";"):
            name, separator, value = part.strip().partition("=")
            if not separator or not name or name in cookies:
                raise AuthError("AUTH_REQUIRED")
            cookies[name] = value
        token = cookies.get(COOKIE_NAME, "")
        csrf = found.get(b"x-proofflow-csrf", b"").decode("ascii", errors="strict")
    except UnicodeError:
        raise AuthError("AUTH_HEADERS_INVALID") from None
    digest = session_digest(token)
    if writing:
        if found.get(b"origin") != expected_origin.encode("ascii"):
            raise AuthError("ORIGIN_REQUIRED")
        return digest, csrf_digest(csrf)
    return digest, None
