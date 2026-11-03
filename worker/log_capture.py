"""Bounded raw diagnostic bytes, not a subprocess runner or HTML renderer.

The future supervisor drains both streams in bounded chunks under its watchdog.
These bytes remain untrusted: escape them at display time, never execute them or
interpret PASS/status text as authority. No stream is written to a host log file.
"""

from dataclasses import dataclass

MAX_LOG_BYTES = 100 * 1024


@dataclass(frozen=True)
class CapturedStream:
    name: str
    content: bytes
    received_bytes: int
    truncated: bool


class BoundedLogCapture:
    """Single-owner buffer; stdout and stderr share one first-arrival byte cap."""

    def __init__(self) -> None:
        self._content = {"stdout": bytearray(), "stderr": bytearray()}
        self._received = {"stdout": 0, "stderr": 0}
        self._retained = 0

    def feed(self, stream: str, chunk: bytes) -> None:
        if stream not in ("stdout", "stderr") or type(chunk) is not bytes:
            raise ValueError("INVALID_LOG_CHUNK")
        self._received[stream] += len(chunk)
        keep = min(len(chunk), MAX_LOG_BYTES - self._retained)
        self._content[stream].extend(chunk[:keep])
        self._retained += keep

    def snapshot(self) -> tuple[CapturedStream, ...]:
        return tuple(CapturedStream(
            name, bytes(content), self._received[name], self._received[name] > len(content),
        ) for name, content in self._content.items())
