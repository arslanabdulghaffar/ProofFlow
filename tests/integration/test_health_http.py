"""Local trusted-server smoke test; no candidate execution or cloud acceptance."""

import json
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, build_opener


def test_real_loopback_server_stays_unready():
    root = Path(__file__).resolve().parents[2]
    with socket.socket() as address:
        address.bind(("127.0.0.1", 0))
        port = address.getsockname()[1]
    # Wait for this child's own successful bind log before making requests, so
    # the port-selection race cannot mistake an unrelated listener for our app.
    log = tempfile.TemporaryFile()
    process = subprocess.Popen(  # noqa: S603 - fixed trusted module, never candidate input
        [
            sys.executable, "-m", "uvicorn", "api.app.main:app",
            "--host", "127.0.0.1", "--port", str(port),
            "--no-access-log", "--no-server-header", "--no-proxy-headers",
        ],
        cwd=root,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=log,
    )
    opener = build_opener(ProxyHandler({}))
    try:
        deadline = time.monotonic() + 10
        while True:
            assert process.poll() is None, "Trusted server failed to start"
            log.seek(0)
            if b"Uvicorn running on" not in log.read(65536):
                assert time.monotonic() < deadline, "Server did not confirm bind"
                time.sleep(0.05)
                continue
            try:
                with opener.open(f"http://127.0.0.1:{port}/health/live", timeout=1) as response:
                    assert response.status == 200
                    assert json.load(response) == {"status": "alive"}
                break
            except (URLError, TimeoutError):
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.05)
        try:
            opener.open(f"http://127.0.0.1:{port}/health/ready", timeout=1).close()
            raise AssertionError("Unverified infrastructure must not be ready")
        except HTTPError as response:
            with response:
                assert response.code == 503
                assert json.load(response)["reason"] == "infrastructure_not_verified"
        assert process.poll() is None
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        log.close()
