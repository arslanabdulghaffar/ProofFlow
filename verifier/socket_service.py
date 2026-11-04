"""Socket-activated root helper. Only dispatcher UID may submit fixed data requests.

No network listener, user path, command or runtime selection. The separately
managed systemd verifier owns its deadline if this transport is terminated.
"""

import os
import re
import socket
import struct
import time
from pathlib import Path

from contracts.codec import canonical_bytes
from verifier.host import run
from verifier.protocol import MAX_REQUEST, MAX_RESPONSE
from worker.protocol import SupervisorError
from worker.wire import _read

DISPATCH_UID = 10003
MAX_RECEIPT = MAX_RESPONSE + 65536


def serve(listener, *, image: Path, image_sha256: str):
    while True:
        channel, _ = listener.accept()
        with channel:
            credentials = channel.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
            _, uid, _ = struct.unpack("3i", credentials)
            if uid != DISPATCH_UID:
                continue  # No input is read before kernel-verified peer authorization.
            try:
                deadline = time.monotonic() + 5
                size = struct.unpack("!I", _read(channel, 4, deadline))[0]
                if not 1 <= size <= MAX_REQUEST:
                    raise SupervisorError("VERIFIER_REQUEST_LIMIT")
                raw = _read(channel, size, deadline)
                receipt = run(raw, image=image, image_sha256=image_sha256)
                response = {"ok": True, "receipt": receipt}
            except (OSError, SupervisorError) as error:
                code = str(error)
                if not re.fullmatch(r"[A-Z_]{1,80}", code):
                    code = "VERIFIER_SERVICE_FAILED"
                response = {"ok": False, "code": code}
            raw_response = canonical_bytes(response, max_bytes=MAX_RECEIPT)
            channel.settimeout(5)
            try:
                channel.sendall(struct.pack("!I", len(raw_response)) + raw_response)
            except OSError:
                # Request outcome is uncertain to the caller. Never retry it here.
                pass


def activated_socket():
    if (os.geteuid() != 0 or os.environ.get("LISTEN_PID") != str(os.getpid())
            or os.environ.get("LISTEN_FDS") != "1"):
        raise SupervisorError("VERIFIER_SOCKET_ACTIVATION_REQUIRED")
    listener = socket.fromfd(3, socket.AF_UNIX, socket.SOCK_STREAM)
    os.close(3)
    if (listener.family != socket.AF_UNIX
            or listener.getsockname() != "/run/proofflow-verifier/verify.sock"):
        raise SupervisorError("VERIFIER_SOCKET_IDENTITY_INVALID")
    return listener
