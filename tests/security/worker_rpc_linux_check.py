"""Real local mTLS + supervisor fixture integration; never executes candidate/image bytes."""

import hashlib
import json
import os
import shutil
import socket
import ssl
import struct
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from supervisor_linux_check import TrustedFixtureRuntime, request, wait_active  # noqa: E402

from orchestrator.worker_client import WorkerClient  # noqa: E402
from worker.protocol import SupervisorError, runtime_identity_digest  # noqa: E402
from worker.service import WorkerServer, WorkerService  # noqa: E402
from worker.staging import Staging, mount_inventory  # noqa: E402
from worker.supervisor import Supervisor  # noqa: E402
from worker.wire import ALPN, MAX_FRAME, authenticate, receive, send, tls_context  # noqa: E402


def openssl(*args):
    subprocess.run(["/usr/bin/openssl", *map(str, args)], check=True,  # noqa: S603
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)


def certificates(root):
    openssl("req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1",
            "-nodes", "-keyout", root / "ca.key", "-out", root / "ca.pem", "-days", "2",
            "-subj", "/CN=ProofFlow ephemeral fixture CA",
            "-addext", "basicConstraints=critical,CA:TRUE",
            "-addext", "keyUsage=critical,keyCertSign,cRLSign")
    for serial, name in enumerate(("worker", "controller", "unapproved"), start=1):
        openssl("req", "-new", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1",
                "-nodes", "-keyout", root / (name + ".key"), "-out", root / (name + ".csr"),
                "-subj", "/CN=" + name)
        extension = "basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\n"
        extension += "extendedKeyUsage=" + ("serverAuth" if name == "worker" else "clientAuth")
        extension += "\nsubjectAltName=DNS:worker.proofflow.internal\n"
        (root / "extension.txt").write_text(extension)
        openssl("x509", "-req", "-in", root / (name + ".csr"), "-CA", root / "ca.pem",
                "-CAkey", root / "ca.key", "-set_serial", serial, "-days", "2",
                "-extfile", root / "extension.txt", "-out", root / (name + ".pem"))


def fingerprint(path):
    return hashlib.sha256(ssl.PEM_cert_to_DER_cert(path.read_text())).hexdigest()


class LocalFixtureClient(WorkerClient):
    def __init__(self, context, pin):
        # Test-only loopback addressing; production client rejects loopback.
        self.address, self.context, self.pin = "127.0.0.1", context, pin
        self.runtime_digest = runtime_identity_digest(TrustedFixtureRuntime().identity())


def main():
    os.umask(0o077)
    root = Path(tempfile.mkdtemp(prefix="proofflow-rpc-check-"))
    runtime = TrustedFixtureRuntime()
    supervisor = server = thread = None
    owned = []
    checks = []
    try:
        certificates(root)
        server_context = tls_context(root / "ca.pem", root / "worker.pem", root / "worker.key",
                                     server=True)
        client_context = tls_context(root / "ca.pem", root / "controller.pem",
                                     root / "controller.key", server=False)
        pin = fingerprint(root / "worker.pem")
        assert client_context.keylog_filename is None and client_context.check_hostname
        state = root / "state"
        state.mkdir(mode=0o700)
        supervisor = Supervisor(state, runtime)
        supervisor.recover()
        server = WorkerServer(("127.0.0.1", 9443), server_context,
                              fingerprint(root / "controller.pem"), WorkerService(supervisor))
        thread = threading.Thread(target=server.serve)
        thread.start()
        client = LocalFixtureClient(client_context, pin)
        assert client.call({"v": 1, "op": "identity"})["sha256"] == client.runtime_digest
        for name in ("unapproved", "absent"):
            if name == "absent":
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                context.minimum_version = ssl.TLSVersion.TLSv1_3
                context.load_verify_locations(str(root / "ca.pem"))
                context.set_alpn_protocols([ALPN])
            else:
                context = tls_context(root / "ca.pem", root / "unapproved.pem",
                                      root / "unapproved.key", server=False)
            try:
                LocalFixtureClient(context, pin).call({"v": 1, "op": "fence",
                                                       "job": uuid4().hex, "generation": 1})
            except SupervisorError:
                pass
            else:
                raise AssertionError("Unauthorized certificate accepted")
        assert not supervisor.journal.unfinished()
        with supervisor.journal._db() as database:
            assert database.execute("SELECT count(*) FROM fences").fetchone()[0] == 0
        checks.append("missing_and_same_CA_unapproved_client_certificates_rejected")
        try:
            LocalFixtureClient(client_context, "0" * 64).call({"v": 1, "op": "fence"})
        except SupervisorError:
            pass
        else:
            raise AssertionError("Wrong server pin accepted")
        checks.append("client_server_certificate_pin_rejection")

        pending = []
        try:
            for _ in range(8):
                pending.append(socket.create_connection(("127.0.0.1", 9443), timeout=2))
            deadline = time.monotonic() + 2
            while len(server.threads) != 8 and time.monotonic() < deadline:
                time.sleep(0.02)
            assert len(server.threads) == 8
            with socket.create_connection(("127.0.0.1", 9443), timeout=2) as ninth:
                assert ninth.recv(1) == b""
        finally:
            for connection in pending:
                connection.close()
        deadline = time.monotonic() + 2
        while server.threads and time.monotonic() < deadline:
            time.sleep(0.02)
        assert not server.threads
        checks.append("unauthenticated_handshakes_bounded_to_eight_and_slots_reclaimed")

        for payload in (struct.pack("!I", MAX_FRAME + 1),
                        struct.pack("!I", 13) + b'{"v":1,"v":1}'):
            with socket.create_connection(("127.0.0.1", 9443), timeout=3) as raw:
                with client_context.wrap_socket(
                        raw, server_hostname="worker.proofflow.internal") as tls:
                    authenticate(tls, pin)
                    tls.sendall(payload)
                    assert receive(tls)["ok"] is False
        checks.append("authorized_oversize_and_duplicate_JSON_rejected_before_dispatch")

        wrong_runtime = LocalFixtureClient(client_context, pin)
        wrong_runtime.runtime_digest = "0" * 64
        try:
            wrong_runtime.create(request())
        except SupervisorError:
            pass
        else:
            raise AssertionError("Changed runtime accepted")
        assert not supervisor.journal.unfinished()
        checks.append("exact_controller_runtime_expectation_rejects_changed_worker")

        item = request()
        owned.append(item.execution_id)
        receipt = client.create(item)
        assert receipt["cleanup"] == "confirmed" and receipt["collected"] is True
        assert client.create(item) == receipt
        scope = {"v": 1, "op": "status", "execution": item.execution_id.hex,
                 "job": item.job_id.hex, "generation": 1}
        assert client.call(scope)["receipt"] == receipt
        try:
            client.call(dict(scope, job=uuid4().hex))
        except SupervisorError:
            pass
        else:
            raise AssertionError("Wrong job scope returned receipt")
        capture = root / "controller-captures"
        capture.mkdir(mode=0o700)
        saved = client.capture_to(capture, item.execution_id, item.job_id, 1, item.manifest_hash())
        assert (saved / "ledger.jsonl").read_bytes() == b'{"fixture":true}\n'
        assert not (state / "results" / item.execution_id.hex).exists()
        checks.append("real_TLS_create_replay_scoped_status_durable_capture_and_ack")

        item = request()
        owned.append(item.execution_id)
        client.create(item)
        class LostAckClient(LocalFixtureClient):
            def call(self, message):
                result = super().call(message)
                if message["op"] == "ack":
                    raise SupervisorError("FIXTURE_ACK_RESPONSE_LOST")
                return result
        try:
            LostAckClient(client_context, pin).capture_to(
                capture, item.execution_id, item.job_id, 1, item.manifest_hash())
        except SupervisorError as error:
            assert str(error) == "FIXTURE_ACK_RESPONSE_LOST"
        else:
            raise AssertionError("ACK loss fixture did not run")
        assert not (state / "results" / item.execution_id.hex).exists()
        saved = client.capture_to(capture, item.execution_id, item.job_id, 1, item.manifest_hash())
        (saved / "ledger.jsonl").write_bytes(b"tampered")
        try:
            client.capture_to(capture, item.execution_id, item.job_id, 1, item.manifest_hash())
        except SupervisorError:
            pass
        else:
            raise AssertionError("Corrupt durable capture accepted")
        checks.append("lost_ack_reconciled_from_local_bytes_and_tampered_capture_rejected")

        # Submit trusted sleep fixture, disconnect controller, cancel over a fresh connection.
        runtime.mode = "sleep"
        item = request()
        owned.append(item.execution_id)
        class MessageOnlyClient(LocalFixtureClient):
            def call(self, message):
                return message
        message = MessageOnlyClient(client_context, pin).create(item)
        with socket.create_connection(("127.0.0.1", 9443), timeout=3) as raw:
            with client_context.wrap_socket(
                    raw, server_hostname="worker.proofflow.internal") as tls:
                authenticate(tls, pin)
                send(tls, message)
        wait_active(runtime, item.execution_id)
        scope = {"v": 1, "op": "cancel", "execution": item.execution_id.hex,
                 "job": item.job_id.hex, "generation": 1}
        assert client.call(scope)["cancel_requested"]
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            status = client.call(dict(scope, op="status"))
            if status["state"] == "CLEANED":
                break
            time.sleep(0.05)
        assert status["receipt"]["outcome"] == "cancelled"
        runtime.confirm_stopped(item.execution_id)
        checks.append("controller_disconnect_then_authenticated_cancel_kills_fixture_descendants")
        message = MessageOnlyClient(client_context, pin).create(request())
        with socket.create_connection(("127.0.0.1", 9443), timeout=3) as raw:
            with client_context.wrap_socket(
                    raw, server_hostname="worker.proofflow.internal") as tls:
                authenticate(tls, pin)
                server.stop.set()
                supervisor.pause_admission()
                send(tls, message)
                assert receive(tls) == {"ok": False, "error": "SERVICE_STOPPING"}
        assert not supervisor.journal.unfinished()
        checks.append("shutdown_denies_already_connected_but_not_admitted_request")
    finally:
        if server:
            server.stop.set()
        if thread:
            thread.join(timeout=3)
        for identifier in owned:
            runtime.stop_and_confirm(identifier)
        if server:
            server.drain()
        if supervisor:
            supervisor.close()
        for identifier in owned:
            Staging(root / "state").cleanup(identifier)
            runtime.forget(identifier)
        assert not any(p.startswith(str(root) + "/") for p in mount_inventory())
        assert root.parent == Path(tempfile.gettempdir())
        assert root.name.startswith("proofflow-rpc-check-")
        shutil.rmtree(root)  # Exact generated fixture tree; no live mounts/writers remain.
    print(json.dumps({"scope": "local_real_TLS_trusted_supervisor_fixtures_no_candidates",
                      "checks": checks, "cleanup": "fixture_certs_units_mounts_files_removed"}))


if __name__ == "__main__":
    main()
