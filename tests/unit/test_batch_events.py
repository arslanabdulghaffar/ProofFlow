"""Exact-body signature and HTTP ordering; no external services or candidate execution."""

import asyncio
import hashlib
import hmac
import json
import time
from uuid import uuid4

import httpx
import pytest

from api.app import batch_events
from api.app.batch_events import SignatureFailure, authenticate, connection_key
from tests.unit.test_product_http import ORIGIN, fixture


def signed(master, connection, event, raw, stamp):
    stamp = str(stamp).encode()
    event = str(event).encode()
    digest = hmac.digest(
        connection_key(master, connection), stamp + b"\n" + event + b"\n" + raw, "sha256"
    ).hex()
    return [
        (b"x-proofflow-event-id", event),
        (b"x-proofflow-timestamp", stamp),
        (b"x-proofflow-signature", b"sha256=" + digest.encode()),
    ]


@pytest.mark.parametrize(
    "change",
    [
        "body",
        "connection",
        "event",
        "stale",
        "future",
        "duplicate",
        "cookie",
        "origin",
        "encoding",
        "case",
    ],
)
def test_signature_fails_closed_before_any_parser(change):
    master = b"x" * 32
    connection, event = uuid4(), uuid4()
    raw = b'{"inert":"bytes"}'
    stamp = 1800000000
    headers = signed(master, connection, event, raw, stamp)
    assert authenticate(headers, raw, connection, master, stamp) == (
        event,
        stamp,
        hashlib.sha256(raw).hexdigest(),
    )
    if change == "body":
        raw += b" "
    elif change == "connection":
        connection = uuid4()
    elif change == "event":
        headers[0] = (headers[0][0], str(uuid4()).encode())
    elif change == "stale":
        stamp += 301
    elif change == "future":
        stamp -= 301
    elif change == "duplicate":
        headers.append(headers[0])
    elif change == "cookie":
        headers.append((b"cookie", b"anything"))
    elif change == "origin":
        headers.append((b"origin", ORIGIN.encode()))
    elif change == "encoding":
        headers.append((b"content-encoding", b"gzip"))
    else:
        headers[-1] = (headers[-1][0], headers[-1][1].upper())
    with pytest.raises(SignatureFailure):
        authenticate(headers, raw, connection, master, stamp)


def test_http_invalid_signature_precedes_json_and_valid_scope_rejects_extra_fields(monkeypatch):
    master = b"x" * 32
    monkeypatch.setattr(batch_events, "load_batch_master", lambda: master)

    async def check():
        store, _, browser = fixture()
        client = httpx.AsyncClient(transport=browser._transport, base_url=ORIGIN)
        prior = store.call
        seen = []

        async def call(op, *args):
            if op == "batch_event":
                seen.append(args)
                return (
                    {"batch_id": str(uuid4()), "event_id": str(args[1]), "already_accepted": False},
                )
            return await prior(op, *args)

        store.call = call
        connection, event = uuid4(), uuid4()
        path = "/v1/connections/" + str(connection) + "/batch-events"
        async with client:
            raw = b"not json"
            headers = signed(master, connection, event, raw, int(time.time()))
            assert (await client.post(path, content=raw + b"x", headers=headers)).status_code == 403
            assert not seen
            raw = json.dumps(
                {
                    "transactions_id": str(uuid4()),
                    "customers_id": str(uuid4()),
                    "version_id": str(uuid4()),
                }
            ).encode()
            headers = signed(master, connection, event, raw, int(time.time()))
            assert (await client.post(path, content=raw, headers=headers)).status_code == 400
            assert not seen
            raw = json.dumps(
                {"transactions_id": str(uuid4()), "customers_id": str(uuid4())}
            ).encode()
            headers = signed(master, connection, event, raw, int(time.time()))
            assert (await client.post(path, content=raw, headers=headers)).status_code == 202
            assert len(seen) == 1 and seen[0][0] == connection and seen[0][1] == event
        await browser.aclose()

    asyncio.run(check())
