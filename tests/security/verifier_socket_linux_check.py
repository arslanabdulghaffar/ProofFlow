"""Root Linux Unix-socket authorization tests using trusted data only."""

import argparse
import json
import os
import signal
import socket
import struct
import time
from pathlib import Path

from orchestrator.verifier_client import VerifierClient
from verifier.protocol import MAX_REQUEST
from verifier.socket_service import serve
from worker.protocol import SupervisorError


def client_check(image_hash):
    client = VerifierClient(image_hash)
    receipt = client(b'{}')
    assert receipt["report"]["status"] == "rejected" and receipt["cleanup_confirmed"] is True
    try:
        VerifierClient("0" * 64)(b'{}')
    except SupervisorError as error:
        assert str(error) == "VERIFIER_RESPONSE_BINDING_INVALID"
    else:
        raise AssertionError("wrong verifier image accepted")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
        channel.settimeout(8)
        channel.connect("/run/proofflow-verifier/verify.sock")
        channel.sendall(struct.pack("!I", MAX_REQUEST + 1))
        header = channel.recv(4)
        size = struct.unpack("!I", header)[0]
        data = b""
        while len(data) < size:
            data += channel.recv(size - len(data))
        assert json.loads(data) == {"ok": False, "code": "VERIFIER_REQUEST_LIMIT"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    assert os.geteuid() == 0
    directory = Path("/run/proofflow-verifier")
    directory.mkdir(mode=0o750)  # Refuse collision with any live service.
    os.chown(directory, 0, 10003)
    target = directory / "verify.sock"
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server = None
    try:
        listener.bind(str(target))
        os.chown(target, 10003, 10003)
        os.chmod(target, 0o600)
        listener.listen(4)
        server = os.fork()
        if server == 0:
            try:
                serve(listener, image=args.image, image_sha256=args.sha256)
            finally:
                os._exit(1)
        listener.close()
        # Root can open any file but is not the authorized transport peer UID.
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as unauthorized:
            unauthorized.settimeout(2)
            unauthorized.connect(str(target))
            assert unauthorized.recv(1) == b""
        child = os.fork()
        if child == 0:
            try:
                os.setgroups([])
                os.setgid(10003)
                os.setuid(10003)
                client_check(args.sha256)
                os._exit(0)
            except Exception:
                os._exit(1)
        deadline = time.monotonic() + 40
        while True:
            pid, status = os.waitpid(child, os.WNOHANG)
            if pid:
                assert os.waitstatus_to_exitcode(status) == 0, "authorized client check failed"
                break
            if time.monotonic() >= deadline:
                os.kill(child, signal.SIGKILL)
                os.waitpid(child, 0)
                raise AssertionError("client exceeded bound")
            time.sleep(0.1)
        print(json.dumps({"checks": ["kernel_peer_uid_denies_root", "unprivileged_fixed_data_call",
                                      "root_peer_and_image_report_binding",
                                      "oversize_frame_denied"],
                          "passed": 4, "candidate_execution": False}))
    finally:
        listener.close()
        if server:
            os.kill(server, signal.SIGTERM)
            os.waitpid(server, 0)
        target.unlink(missing_ok=True)
        directory.rmdir()


if __name__ == "__main__":
    main()
