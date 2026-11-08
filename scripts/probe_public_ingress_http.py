"""Read-only HTTPS edge smoke. No login, provider call, upload or provisioning."""

import argparse
import json
import ssl
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api.app.ingress import authority  # noqa: E402


def probe(client):
    checks = []
    for path, wanted in (("/", 200), ("/health/live", 200), ("/v1/session", 403),
                         ("/openapi.json", 404), ("/static/missing.js", 404)):
        with client.stream("GET", path) as response:
            total = sum(len(chunk) for chunk in bounded(response))
            if response.status_code != wanted or total > 1024 * 1024:
                raise RuntimeError("EDGE_STATUS_OR_SIZE_INVALID")
            if (response.headers.get("cache-control") != "no-store"
                    or response.headers.get("x-content-type-options") != "nosniff"
                    or response.headers.get("referrer-policy") != "no-referrer"
                    or "frame-ancestors 'none'" not in response.headers.get(
                        "content-security-policy", "")
                    or response.headers.get_list("set-cookie")):
                raise RuntimeError("EDGE_HEADERS_OR_ANONYMOUS_COOKIE_INVALID")
        checks.append(path)
    for headers in ({"Host": "unrelated.invalid"}, {"X-Forwarded-Proto": "https"},
                    {"Forwarded": "host=unrelated.invalid;proto=https"}):
        with client.stream("GET", "/health/live", headers=headers) as response:
            for _ in bounded(response):
                pass
            if response.status_code != 400:
                raise RuntimeError("EDGE_FORGED_AUTHORITY_ALLOWED")
    return {"anonymous_routes_checked": checks, "forged_authorities_denied": 3,
            "writes": 0, "provider_calls": 0, "public_network_path": "caller must identify"}


def bounded(response):
    total = 0
    for chunk in response.iter_raw():
        total += len(chunk)
        if total > 1024 * 1024:
            raise RuntimeError("EDGE_RESPONSE_LIMIT")
        yield chunk


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--ca", type=Path,
                        help="Explicit trusted test/private CA; never disables TLS")
    args = parser.parse_args()
    authority(args.origin)
    with httpx.Client(base_url=args.origin, trust_env=False, follow_redirects=False,
                      timeout=10, verify=ssl.create_default_context(cafile=args.ca)) as client:
        print(json.dumps(probe(client)))


if __name__ == "__main__":
    main()
