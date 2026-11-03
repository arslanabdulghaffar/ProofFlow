"""Private, one-request TLS RPC framing. No HTTP, URLs, proxies or tool dispatcher."""

import hashlib
import ipaddress
import json
import re
import socket
import ssl
import struct
import time
from pathlib import Path

from worker.protocol import SupervisorError

MAX_FRAME = 15 * 1024 * 1024
ALPN = "proofflow-worker/1"
RFC1918 = tuple(ipaddress.ip_network(value) for value in
               ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))


def private_address(value: str) -> str:
    if type(value) is not str:
        raise SupervisorError("PRIVATE_WORKER_ADDRESS_REQUIRED")
    try:
        address = ipaddress.IPv4Address(value)
    except (ValueError, TypeError):
        raise SupervisorError("PRIVATE_WORKER_ADDRESS_REQUIRED") from None
    if not any(address in network for network in RFC1918):
        raise SupervisorError("PRIVATE_WORKER_ADDRESS_REQUIRED")
    return str(address)


def digest(value: object) -> str:
    if type(value) is not str or not re.fullmatch("[0-9a-f]{64}", value):
        raise SupervisorError("INVALID_DIGEST")
    return value


def strict_json(data: bytes) -> dict:
    def invalid_constant(_):
        raise ValueError("nonfinite")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate")
            result[key] = value
        return result
    try:
        # Bound structure before allocating a recursive JSON tree; string contents
        # do not affect depth. Encoding remains strict UTF-8 below.
        depth = 0
        quoted = escaped = False
        for byte in data:
            if quoted:
                if escaped:
                    escaped = False
                elif byte == 92:
                    escaped = True
                elif byte == 34:
                    quoted = False
            elif byte == 34:
                quoted = True
            elif byte in (91, 123):
                depth += 1
                if depth > 12:
                    raise ValueError("depth")
            elif byte in (93, 125):
                depth -= 1
        value = json.loads(data.decode("utf-8"), object_pairs_hook=pairs,
                           parse_constant=invalid_constant)
        if type(value) is not dict:
            raise ValueError("object")
        return value
    except (UnicodeError, ValueError, RecursionError):
        raise SupervisorError("INVALID_MESSAGE") from None


def keys(message: dict, expected: set[str]) -> None:
    if set(message) != expected:
        raise SupervisorError("INVALID_MESSAGE_FIELDS")


def _remaining(sock: socket.socket, deadline: float) -> None:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise SupervisorError("WIRE_DEADLINE")
    sock.settimeout(remaining)


def _read(sock: socket.socket, size: int, deadline: float) -> bytes:
    data = bytearray()
    while len(data) < size:
        _remaining(sock, deadline)
        chunk = sock.recv(min(65536, size - len(data)))
        if not chunk:
            raise SupervisorError("WIRE_TRUNCATED")
        data.extend(chunk)
    return bytes(data)


def receive(sock: socket.socket, *, seconds: float = 10) -> dict:
    deadline = time.monotonic() + seconds
    size = struct.unpack("!I", _read(sock, 4, deadline))[0]
    if not 1 <= size <= MAX_FRAME:
        raise SupervisorError("WIRE_SIZE_LIMIT")
    result = strict_json(_read(sock, size, deadline))
    _remaining(sock, deadline)
    return result


def send(sock: socket.socket, message: dict, *, seconds: float = 10) -> None:
    data = json.dumps(message, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if len(data) > MAX_FRAME:
        raise SupervisorError("WIRE_SIZE_LIMIT")
    deadline = time.monotonic() + seconds
    view = memoryview(struct.pack("!I", len(data)) + data)
    while view:
        _remaining(sock, deadline)
        written = sock.send(view[:65536])
        if not written:
            raise SupervisorError("WIRE_TRUNCATED")
        view = view[written:]


def tls_context(ca: Path, certificate: Path, key: Path, *, server: bool) -> ssl.SSLContext:
    # Explicit context avoids environment SSLKEYLOGFILE and system trust roots.
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER if server else ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_verify_locations(cafile=str(ca))
    context.load_cert_chain(str(certificate), str(key))
    context.set_alpn_protocols([ALPN])
    if server:
        context.num_tickets = 0
    return context


def check_context(context: ssl.SSLContext, *, server: bool) -> None:
    if (context.verify_mode != ssl.CERT_REQUIRED
            or context.minimum_version < ssl.TLSVersion.TLSv1_3
            or context.keylog_filename is not None or (not server and not context.check_hostname)):
        raise SupervisorError("UNSAFE_TLS_CONTEXT")


def authenticate(sock: ssl.SSLSocket, expected: str) -> None:
    digest(expected)
    certificate = sock.getpeercert(binary_form=True)
    if (not certificate or sock.selected_alpn_protocol() != ALPN
            or hashlib.sha256(certificate).hexdigest() != expected):
        raise SupervisorError("PEER_NOT_AUTHORIZED")
