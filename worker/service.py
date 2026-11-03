"""Authenticated worker RPC; executable composition is only in entrypoint.py."""

import base64
import binascii
import re
import socket
import ssl
import threading
from uuid import UUID

from worker.protocol import ExecutionRequest, SupervisorError
from worker.wire import authenticate, check_context, digest, keys, receive, send


def identifier(value: object) -> UUID:
    if type(value) is not str or not re.fullmatch("[0-9a-f]{32}", value):
        raise SupervisorError("INVALID_EXECUTION_ID")
    return UUID(hex=value)


def generation(value: object) -> int:
    if type(value) is not int or not 1 <= value <= 2147483647:
        raise SupervisorError("INVALID_EXECUTION_GENERATION")
    return value


def decode_input(value: object, limit: int) -> bytes:
    if type(value) is not str or len(value) > 4 * ((limit + 2) // 3):
        raise SupervisorError("STAGED_INPUT_LIMIT")
    try:
        result = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error):
        raise SupervisorError("INVALID_INPUT_ENCODING") from None
    if len(result) > limit or base64.b64encode(result).decode() != value:
        raise SupervisorError("INVALID_INPUT_ENCODING")
    return result


class WorkerService:
    def __init__(self, supervisor):
        self.supervisor = supervisor

    def dispatch(self, message: dict) -> dict:
        if type(message.get("v")) is not int or message["v"] != 1:
            raise SupervisorError("UNSUPPORTED_WIRE_VERSION")
        op = message.get("op")
        if op == "identity":
            keys(message, {"v", "op"})
            return self.supervisor.describe()
        common = {"v", "op", "execution", "job", "generation"}
        if op == "create":
            keys(message, common | {"inputs", "rollups", "manifest", "runtime"})
            inputs = message["inputs"]
            if type(inputs) is not dict:
                raise SupervisorError("INVALID_MESSAGE")
            names = ("pipeline", "transactions", "customers", "requirements")
            keys(inputs, set(names))
            values = [decode_input(inputs[name], limit) for name, limit in
                      zip(names, (16384, 10485760, 10485760, 32768), strict=True)]
            request = ExecutionRequest(
                identifier(message["execution"]), identifier(message["job"]),
                generation(message["generation"]), *values, message["rollups"])
            if request.manifest_hash() != digest(message["manifest"]):
                raise SupervisorError("REQUEST_MANIFEST_MISMATCH")
            return self.supervisor.execute(request, expected_runtime=digest(message["runtime"]))
        if op == "fence":
            keys(message, {"v", "op", "job", "generation"})
            job, version = identifier(message["job"]), generation(message["generation"])
            self.supervisor.journal.fence(job, version)
            return {"fenced": True}
        if op not in ("status", "cancel", "capture", "ack"):
            raise SupervisorError("UNSUPPORTED_OPERATION")
        keys(message, common | ({"manifest"} if op in ("capture", "ack") else set()))
        execution, job = identifier(message["execution"]), identifier(message["job"])
        version = generation(message["generation"])
        status = self.supervisor.journal.scoped_status(execution, job, version)
        if op == "status":
            return status
        if op == "cancel":
            self.supervisor.journal.cancel(execution, job, version)
            return {"cancel_requested": True}
        manifest = digest(message["manifest"])
        if op == "capture":
            return self.supervisor.capture(execution, manifest)
        self.supervisor.acknowledge(execution, manifest)
        return {"acknowledged": True}


class WorkerServer:
    """Eight bounded connection slots; handshake is never on the accept thread."""

    def __init__(self, address: tuple[str, int], context: ssl.SSLContext, peer_pin: str,
                 service: WorkerService):
        self.context, self.peer_pin, self.service = context, digest(peer_pin), service
        check_context(context, server=True)
        self.stop = threading.Event()
        self.slots = threading.BoundedSemaphore(8)
        self.threads: set[threading.Thread] = set()
        self.guard = threading.Lock()
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener.bind(address)
        self.listener.listen(8)
        self.listener.settimeout(0.25)

    def serve(self) -> None:
        try:
            while not self.stop.is_set():
                try:
                    raw, _ = self.listener.accept()
                except TimeoutError:
                    continue
                if not self.slots.acquire(blocking=False):
                    raw.close()
                    continue
                thread = threading.Thread(target=self._connection, args=(raw,), daemon=True)
                with self.guard:
                    self.threads.add(thread)
                thread.start()
        finally:
            self.listener.close()

    def _connection(self, raw: socket.socket) -> None:
        try:
            raw.settimeout(5)
            with self.context.wrap_socket(raw, server_side=True) as channel:
                authenticate(channel, self.peer_pin)  # No parsing before certificate authorization.
                try:
                    message = receive(channel)
                    if self.stop.is_set():
                        raise SupervisorError("SERVICE_STOPPING")
                    result = self.service.dispatch(message)
                    response = {"ok": True, "result": result}
                except SupervisorError as error:
                    code = str(error)
                    if not re.fullmatch("[A-Z_]{1,80}", code):
                        code = "WORKER_FAILURE"
                    response = {"ok": False, "error": code}
                except Exception:
                    response = {"ok": False, "error": "WORKER_FAILURE"}
                send(channel, response)
        except (OSError, SupervisorError):
            pass  # Authentication/transport failure: no body, paths, secrets or raw logging.
        finally:
            raw.close()
            self.slots.release()
            with self.guard:
                self.threads.discard(threading.current_thread())

    def drain(self) -> None:
        # One shared shutdown deadline, not a timeout multiplied by connection count.
        import time
        deadline = time.monotonic() + 40
        with self.guard:
            threads = list(self.threads)
        for thread in threads:
            thread.join(max(0, deadline - time.monotonic()))
        if any(thread.is_alive() for thread in threads):
            raise SupervisorError("SERVICE_DRAIN_UNCERTAIN")
