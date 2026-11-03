"""Synchronous worker core. Private mTLS service composition is a deployment gate.

Durable admission precedes staging/launch. Existing IDs never rerun. The service
manager watchdog is independent of this process and controller connections.
"""

import hashlib
import json
import os
import threading
from pathlib import Path
from uuid import UUID

from worker.collector import CollectionError, collect_stopped_outputs
from worker.journal import Journal
from worker.protocol import ExecutionRequest, SupervisorError
from worker.runtime import SystemdRunsc
from worker.staging import Staging


class Supervisor:
    def __init__(self, root: Path, runtime: SystemdRunsc):
        import fcntl  # Linux host only; no import/launch side effect on development host.
        self.journal = Journal(root)
        self.staging = Staging(root)
        self.runtime = runtime
        self._lock = os.open(root / "supervisor.lock",
                             os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        try:
            fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            os.close(self._lock)
            raise SupervisorError("SUPERVISOR_ALREADY_RUNNING") from None
        self._recovered = False
        self._guard = threading.RLock()
        self._active: set[UUID] = set()
        self._stop = threading.Event()
        self._maintenance_thread: threading.Thread | None = None
        self._maintenance_failed = False
        self._closing = False

    def close(self) -> None:
        with self._guard:
            if self._active:
                raise SupervisorError("ACTIVE_EXECUTIONS_REMAIN")
            self._closing = True
            self._stop.set()
            self._recovered = False
        if self._maintenance_thread is not None:
            self._maintenance_thread.join(timeout=5)
            if self._maintenance_thread.is_alive():
                raise SupervisorError("MAINTENANCE_STOP_UNCERTAIN")
        with self._guard:
            if self._lock is not None:
                os.close(self._lock)
                self._lock = None

    def maintain(self) -> None:
        """Also callable by trusted service health checks; protects unfinished captures."""
        with self._guard:
            if not self._recovered:
                raise SupervisorError("RECOVERY_REQUIRED")
            self.staging.prune_results(set(self.journal.unfinished()))

    def _housekeeping(self) -> None:
        while not self._stop.wait(1):
            with self._guard:
                if not self._recovered:
                    continue
                try:
                    self.maintain()
                except Exception:
                    # Fail closed even on an unexpected maintenance fault. Keep the
                    # thread alive so explicit recovery can resume safe maintenance.
                    self._maintenance_failed = True
                    self._recovered = False

    def _cleanup(self, identifier: UUID) -> dict:
        proof = self.runtime.stop_and_confirm(identifier)
        path = self.staging.path(identifier)
        if path.exists():
            self.runtime.delete_state(identifier, path)
        self.runtime.confirm_stopped(identifier)
        self.staging.cleanup(identifier)
        self.runtime.forget(identifier)
        return proof

    def recover(self) -> None:
        with self._guard:
            if self._closing:
                raise SupervisorError("SUPERVISOR_CLOSED")
            if self._active:
                raise SupervisorError("ACTIVE_EXECUTIONS_REMAIN")
            self._recovered = False
            self._recover()
            self._maintenance_failed = False
            if self._maintenance_thread is None:
                self._maintenance_thread = threading.Thread(
                    target=self._housekeeping, name="proofflow-capture-maintenance", daemon=True)
                self._maintenance_thread.start()

    def _recover(self) -> None:
        if self._lock is None:
            raise SupervisorError("SUPERVISOR_CLOSED")
        self.runtime.validate()
        for identifier in self.journal.unfinished():
            receipt = {"execution": identifier.hex, "outcome": "interrupted", "collected": False,
                       "verification": "NOT_PERFORMED"}
            try:
                receipt["termination"] = self._cleanup(identifier)
                receipt["cleanup"] = "confirmed"
                self.journal.finish(identifier, receipt, cleaned=True)
            except (SupervisorError, OSError):
                receipt["cleanup"] = "uncertain"
                self.journal.finish(identifier, receipt, cleaned=False)
                raise SupervisorError("RECOVERY_QUARANTINED") from None
        self.staging.prune_results(set(self.journal.unfinished()))
        self._recovered = True

    def execute(self, request: ExecutionRequest) -> dict:
        with self._guard:
            if not self._recovered:
                raise SupervisorError("WORKER_MAINTENANCE_FAILED" if self._maintenance_failed
                                      else "RECOVERY_REQUIRED")
            self.runtime.validate()
            identity = self.runtime.identity()
            digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
            retained = self.staging.prune_results(set(self.journal.unfinished()))
            if not self.journal.admit(request, digest, retained_slots=retained):
                return self.journal.receipt(request.execution_id) or {
                    "execution": request.execution_id.hex, "outcome": "existing_in_progress"}
            self._active.add(request.execution_id)
        identifier = request.execution_id
        receipt = {"execution": identifier.hex, "job": request.job_id.hex,
                   "generation": request.generation, "manifest": request.manifest_hash(),
                   "runtime": identity,
                   "outcome": "infrastructure_failure", "collected": False,
                   "verification": "NOT_PERFORMED", "cleanup": "uncertain"}
        output_fd = None
        try:
            path = self.staging.prepare(request)
            output_fd = self.staging.open_output(identifier)
            self.runtime.write_config(request, path)
            self.journal.running(identifier)
            execution, logs = self.runtime.execute(identifier, path,
                                                    lambda: self.journal.cancelled(identifier))
            receipt.update(execution)
            receipt["termination"] = self.runtime.confirm_stopped(identifier)
            files = collect_stopped_outputs(output_fd, include_rollups=request.include_rollups)
            self.runtime.confirm_stopped(identifier)
            receipt["files"] = [{"name": f.name, "sha256": f.sha256, "bytes": len(f.content),
                                  "lines": f.lines} for f in files]
            receipt["logs"] = [{"stream": log.name, "retained": len(log.content),
                                 "received": log.received_bytes, "truncated": log.truncated}
                                for log in logs]
            self.staging.persist(identifier, files, logs, receipt)
            receipt["collected"] = True
        except (SupervisorError, CollectionError, OSError) as error:
            receipt["outcome"] = "output_rejected" if isinstance(error, CollectionError) \
                else "infrastructure_failure"
            receipt["error"] = str(error) if isinstance(error, (SupervisorError, CollectionError)) \
                else "HOST_IO_FAILURE"
        finally:
            if output_fd is not None:
                os.close(output_fd)  # Close retained mount handle before normal unmount.
            try:
                receipt["termination"] = self._cleanup(identifier)
                receipt["cleanup"] = "confirmed"
            except (SupervisorError, OSError):
                receipt["cleanup"] = "uncertain"
                receipt["outcome"] = "infrastructure_failure"
            try:
                self.journal.finish(identifier, receipt, cleaned=receipt["cleanup"] == "confirmed")
            finally:
                with self._guard:
                    self._active.discard(identifier)
        return receipt

    def acknowledge(self, identifier: UUID, manifest: str) -> None:
        with self._guard:
            receipt = self.journal.receipt(identifier)
            if (not receipt or receipt.get("manifest") != manifest
                    or receipt.get("cleanup") != "confirmed" or not receipt.get("collected")):
                raise SupervisorError("INVALID_CAPTURE_ACKNOWLEDGEMENT")
            self.staging.remove_result(identifier)
