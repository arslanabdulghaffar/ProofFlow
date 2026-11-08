"""Inert HTTP transport doubles for the read-only release smoke tool."""

import httpx
import pytest

from scripts.probe_public_ingress_http import bounded, probe


@pytest.mark.parametrize("failure", [None, "redirect", "cookie", "cache", "forged"])
def test_read_only_smoke_rejects_unsafe_edge_response(failure):
    requests = []

    def respond(request):
        requests.append(request)
        forged = (request.headers["host"] == "unrelated.invalid"
                  or "forwarded" in request.headers or "x-forwarded-proto" in request.headers)
        codes = {"/": 200, "/health/live": 200, "/v1/session": 403,
                 "/openapi.json": 404, "/static/missing.js": 404}
        code = 400 if forged else codes[request.url.path]
        headers = {"cache-control": "no-store", "referrer-policy": "no-referrer",
                   "x-content-type-options": "nosniff",
                   "content-security-policy": "frame-ancestors 'none'"}
        if failure == "redirect":
            code = 302
        elif failure == "cookie":
            headers["set-cookie"] = "unexpected=inert"
        elif failure == "cache":
            headers["cache-control"] = "public"
        elif failure == "forged" and forged:
            code = 200
        return httpx.Response(code, headers=headers, stream=httpx.ByteStream(b"inert"))

    with httpx.Client(base_url="https://demo.example", transport=httpx.MockTransport(respond)) as c:
        if failure:
            with pytest.raises(RuntimeError):
                probe(c)
        else:
            assert probe(c)["forged_authorities_denied"] == 3
    assert all(r.method == "GET" and not r.content for r in requests)
    assert all("authorization" not in r.headers and "cookie" not in r.headers for r in requests)


def test_oversized_response_is_bounded_without_decoding():
    response = httpx.Response(200, stream=httpx.ByteStream(b"x" * (1024 * 1024 + 1)))
    with pytest.raises(RuntimeError, match="EDGE_RESPONSE_LIMIT"):
        list(bounded(response))
