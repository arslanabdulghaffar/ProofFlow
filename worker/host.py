"""Linux host primitives for trusted worker administration, never user commands."""

import os
import selectors
import signal
import subprocess
import time
from pathlib import Path

from worker.protocol import SupervisorError

HOST_ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C", "LC_ALL": "C"}


def command(args: list[str], *, timeout: float = 5, allow_failure: bool = False) -> str:
    process = subprocess.Popen(  # noqa: S603 - internal fixed host commands, no public dispatcher
        args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=HOST_ENV, start_new_session=True,
    )
    content = bytearray()
    deadline = time.monotonic() + timeout
    try:
        with selectors.DefaultSelector() as selector:
            for pipe in (process.stdout, process.stderr):
                os.set_blocking(pipe.fileno(), False)
                selector.register(pipe, selectors.EVENT_READ)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise SupervisorError("HOST_COMMAND_TIMEOUT")
                for key, _ in selector.select(min(remaining, 0.1)):
                    chunk = os.read(key.fd, 4096)
                    if not chunk:
                        selector.unregister(key.fileobj)
                    elif key.fileobj is process.stdout:
                        content.extend(chunk)
                        if len(content) > 65536:
                            raise SupervisorError("HOST_RESPONSE_LIMIT")
            code = process.wait(timeout=max(0.001, deadline - time.monotonic()))
            if code and not allow_failure:
                raise SupervisorError("HOST_COMMAND_FAILED")
        return content.decode("utf-8", errors="strict")
    except (OSError, UnicodeError, subprocess.TimeoutExpired):
        raise SupervisorError("HOST_COMMAND_FAILED") from None
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=2)
        process.stdout.close()
        process.stderr.close()


def synced_write(path: Path, content: bytes, *, mode: int = 0o600) -> None:
    if mode not in (0o600, 0o444):
        raise SupervisorError("UNAPPROVED_DURABLE_FILE_MODE")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        view = memoryview(content)
        while view:
            written = os.write(fd, view)
            if not written:
                raise SupervisorError("SHORT_DURABLE_WRITE")
            view = view[written:]
        # The service uses UMask=0077. Apply the reviewed final mode on this
        # exact newly created descriptor, so staged guest inputs are readable
        # after their read-only bind without making the host parent traversable.
        os.fchmod(fd, mode)
        os.fsync(fd)
    finally:
        os.close(fd)


def sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
