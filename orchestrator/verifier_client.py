"""Unprivileged dispatcher to fixed local verifier socket, with root peer pin."""

import socket
import struct
import time
from dataclasses import dataclass

from contracts.codec import InputError, canonical_bytes, parse_object
from verifier.protocol import MAX_REQUEST, MAX_RESPONSE, VERSION, sha
from worker.protocol import SupervisorError
from worker.wire import _read


@dataclass(frozen=True)
class VerifierClient:
    rootfs_sha256: str

    def __call__(self, raw: bytes):
        if type(raw) is not bytes or not 1 <= len(raw) <= MAX_REQUEST:
            raise SupervisorError("VERIFIER_REQUEST_LIMIT")
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
                channel.settimeout(5)
                channel.connect("/run/proofflow-verifier/verify.sock")
                _, uid, _ = struct.unpack("3i", channel.getsockopt(
                    socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                if uid != 0:
                    raise SupervisorError("VERIFIER_PEER_UNTRUSTED")
                channel.sendall(struct.pack("!I", len(raw)) + raw)
                deadline = time.monotonic() + 25
                size = struct.unpack("!I", _read(channel, 4, deadline))[0]
                if not 1 <= size <= MAX_RESPONSE + 65536:
                    raise SupervisorError("VERIFIER_RESPONSE_LIMIT")
                response = parse_object(_read(channel, size, deadline),
                                        max_bytes=MAX_RESPONSE + 65536)
            if response.get("ok") is not True or set(response) != {"ok", "receipt"}:
                raise SupervisorError("VERIFIER_SERVICE_REJECTED")
            receipt = response["receipt"]
            if (type(receipt) is not dict or set(receipt) != {
                    "report", "report_sha256", "rootfs_sha256", "cleanup_confirmed"}
                    or receipt["cleanup_confirmed"] is not True
                    or receipt["rootfs_sha256"] != self.rootfs_sha256
                    or receipt["report"]["version"] != VERSION
                    or receipt["report"]["request_sha256"] != sha(raw)
                    or receipt["report_sha256"] != sha(canonical_bytes(
                        receipt["report"], max_bytes=MAX_RESPONSE))):
                raise SupervisorError("VERIFIER_RESPONSE_BINDING_INVALID")
            return receipt
        except (OSError, InputError, KeyError, TypeError, ValueError):
            raise SupervisorError("VERIFIER_RESPONSE_UNCERTAIN") from None
