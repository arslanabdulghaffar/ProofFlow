"""ASGI transport doubles; verify slow-reader capacity release without real sockets."""

import asyncio

from api.app import product


def test_slow_response_readers_cannot_hold_all_http_capacity_forever(monkeypatch):
    monkeypatch.setattr(product, "RESPONSE_DEADLINE_SECONDS", 0.05)

    async def exercise():
        blocked = asyncio.Event()
        started = []

        async def app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"bounded inert bytes"})

        boundary = product.CapacityBoundary(app)

        async def receive():
            return {"type": "http.request", "body": b""}

        async def slow_send(message):
            if message["type"] == "http.response.start":
                started.append(message["status"])
            else:
                await blocked.wait()

        async def fast_send(message):
            responses.append(message)

        pending = [asyncio.create_task(boundary(
            {"type": "http", "path": "/v1/assets/example"}, receive, slow_send,
        )) for _ in range(4)]
        while len(started) != 4:
            await asyncio.sleep(0)
        responses = []
        await boundary({"type": "http", "path": "/"}, receive, fast_send)
        assert responses[0]["status"] == 429
        await asyncio.wait_for(asyncio.gather(*pending), timeout=0.5)
        assert not blocked.is_set() and started == [200] * 4
        responses.clear()
        await boundary({"type": "http", "path": "/"}, receive, fast_send)
        assert responses[0]["status"] == 200
        assert responses[-1]["type"] == "http.response.body"

    asyncio.run(exercise())


def test_capacity_rejection_is_also_bounded(monkeypatch):
    monkeypatch.setattr(product, "RESPONSE_DEADLINE_SECONDS", 0.05)

    async def exercise():
        async def unreachable(*args):
            raise AssertionError("capacity-full request reached application")

        boundary = product.CapacityBoundary(unreachable)
        for _ in range(4):
            await boundary.slots.acquire()
        statuses = []

        async def slow_send(message):
            if message["type"] == "http.response.start":
                statuses.append(message["status"])
            await asyncio.Event().wait()

        await asyncio.wait_for(boundary(
            {"type": "http", "path": "/"}, unreachable, slow_send,
        ), timeout=0.5)
        assert statuses == [429]

    asyncio.run(exercise())
