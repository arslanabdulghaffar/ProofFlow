"""Synthetic ephemeral credentials, never user/account/provider secrets."""

import pytest

from api.app.auth import AuthError, SessionSecrets, csrf_digest, request_digests, session_digest

ORIGIN = "https://127.0.0.1:8443"


def headers(secret):
    return [(b"cookie", ("__Host-proofflow=" + secret.token).encode()),
            (b"origin", ORIGIN.encode()), (b"x-proofflow-csrf", secret.csrf.encode()),
            (b"sec-fetch-site", b"same-origin")]


def test_secrets_are_random_domain_separated_and_not_in_repr():
    first, second = SessionSecrets.create(), SessionSecrets.create()
    assert first.token != second.token and first.csrf != second.csrf
    assert first.token not in repr(first) and first.csrf not in repr(first)
    assert len(session_digest(first.token)) == 64
    assert session_digest(first.token) != csrf_digest(first.csrf)
    cookie = first.cookie(max_age=3600)
    for required in ("__Host-proofflow=", "Path=/", "Max-Age=3600", "Secure", "HttpOnly",
                     "SameSite=Strict"):
        assert required in cookie
    assert "Domain=" not in cookie


def test_read_write_credentials_are_only_hashes_and_require_database_later():
    secret = SessionSecrets.create()
    assert request_digests(headers(secret), expected_origin=ORIGIN, writing=True) == (
        session_digest(secret.token), csrf_digest(secret.csrf))
    assert request_digests(headers(secret)[:1], expected_origin=ORIGIN, writing=False) == (
        session_digest(secret.token), None)


@pytest.mark.parametrize("index,value,code", [
    (0, b"__Host-proofflow=bad", "AUTH_REQUIRED"),
    (1, b"https://evil.invalid", "ORIGIN_REQUIRED"),
    (1, b"null", "ORIGIN_REQUIRED"),
    (1, b"https://127.0.0.1:8443.evil.invalid", "ORIGIN_REQUIRED"),
    (2, b"bad", "CSRF_REQUIRED"),
    (3, b"cross-site", "CROSS_SITE_REQUEST"),
    (3, b"same-site", "CROSS_SITE_REQUEST"),
])
def test_browser_forgery_is_rejected(index, value, code):
    request = headers(SessionSecrets.create())
    request[index] = (request[index][0], value)
    with pytest.raises(AuthError, match=f"^{code}$"):
        request_digests(request, expected_origin=ORIGIN, writing=True)


def test_duplicate_headers_and_cookies_cannot_override_first_value():
    secret = SessionSecrets.create()
    original = headers(secret)
    for entry in original:
        with pytest.raises(AuthError, match="AUTH_HEADERS_INVALID"):
            request_digests(original + [entry], expected_origin=ORIGIN, writing=True)
    original[0] = (b"cookie", original[0][1] + b"; " + original[0][1])
    with pytest.raises(AuthError, match="AUTH_REQUIRED"):
        request_digests(original, expected_origin=ORIGIN, writing=True)


@pytest.mark.parametrize("origin", ["http://localhost", "https://x/path", "https://user@x",
                                    "https://x?y", "https://x#y", "https://x:bad", "null",
                                    "https://x\n", "https://x\\evil", "https://x:0"])
def test_origin_configuration_never_comes_from_unvalidated_proxy_headers(origin):
    with pytest.raises(AuthError, match="ORIGIN_CONFIGURATION_INVALID"):
        request_digests([], expected_origin=origin, writing=False)


def test_wrong_token_domain_and_expiry_limits_fail():
    secret = SessionSecrets.create()
    with pytest.raises(AuthError, match="AUTH_REQUIRED"):
        session_digest(secret.csrf)
    with pytest.raises(AuthError, match="CSRF_REQUIRED"):
        csrf_digest(secret.token)
    for age in (0, 43201, True, 3600.0):
        with pytest.raises(AuthError, match="SESSION_EXPIRY_INVALID"):
            secret.cookie(max_age=age)


def test_header_limits_and_control_bytes():
    secret = SessionSecrets.create()
    for request in (headers(secret) + [(b"a", b"x")] * 65,
                    headers(secret) + [(b"a", b"x" * 8193)],
                    [(b"cookie", b"x\r\ny")], [(b"cookie", b"\xff")]):
        with pytest.raises(AuthError, match="AUTH_HEADERS_INVALID"):
            request_digests(request, expected_origin=ORIGIN, writing=True)
