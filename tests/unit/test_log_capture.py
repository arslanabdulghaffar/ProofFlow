"""Trusted diagnostic fixtures; no subprocess or candidate execution."""

import pytest

from worker.log_capture import MAX_LOG_BYTES, BoundedLogCapture


def test_empty_streams_are_not_truncated():
    assert all(s.content == b"" and not s.truncated and s.received_bytes == 0
               for s in BoundedLogCapture().snapshot())


def test_streams_share_one_limit_and_report_dropped_bytes():
    logs = BoundedLogCapture()
    logs.feed("stderr", b"e" * (MAX_LOG_BYTES - 2))
    logs.feed("stdout", b"1234")
    out, err = logs.snapshot()
    assert out.content == b"12" and out.received_bytes == 4 and out.truncated
    assert len(err.content) == MAX_LOG_BYTES - 2 and not err.truncated
    logs.feed("stderr", b"last")
    out, err = logs.snapshot()
    assert err.truncated and err.received_bytes == MAX_LOG_BYTES + 2
    assert sum(len(s.content) for s in (out, err)) == MAX_LOG_BYTES


def test_exact_limit_then_empty_chunk_then_one_byte():
    logs = BoundedLogCapture()
    logs.feed("stdout", b"x" * MAX_LOG_BYTES)
    logs.feed("stdout", b"")
    assert not logs.snapshot()[0].truncated
    logs.feed("stdout", b"y")
    assert logs.snapshot()[0].truncated
    assert logs.snapshot()[0].content == b"x" * MAX_LOG_BYTES


def test_large_chunk_retains_only_prefix():
    logs = BoundedLogCapture()
    logs.feed("stdout", b"x" * (4 * MAX_LOG_BYTES))
    out = logs.snapshot()[0]
    assert out.content == b"x" * MAX_LOG_BYTES
    assert out.received_bytes == 4 * MAX_LOG_BYTES and out.truncated


def test_snapshots_do_not_change_and_bytes_stay_inert():
    logs = BoundedLogCapture()
    payload = b"\xff\x00<script>PASS</script>\x1b[2J"
    logs.feed("stderr", payload)
    earlier = logs.snapshot()
    logs.feed("stderr", b"more")
    assert earlier[1].content == payload
    assert logs.snapshot()[1].content == payload + b"more"


@pytest.mark.parametrize("stream,chunk", [
    ("../secret", b"data"), ("stdout", "text"), ("stderr", bytearray(b"data")),
])
def test_invalid_chunk_does_not_change_capture(stream, chunk):
    logs = BoundedLogCapture()
    before = logs.snapshot()
    with pytest.raises(ValueError, match="^INVALID_LOG_CHUNK$"):
        logs.feed(stream, chunk)
    assert logs.snapshot() == before
