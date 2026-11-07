"""Real bounded-pipe faults using trusted test children, never candidate programs."""

import os
import sys
import time

import pytest

from scripts.consistent_product_backup import CaptureError, command, running

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Linux pipe/Docker capture")


@pytest.mark.parametrize("target", ["other", "proofflow-budget;id", "-Hremote", ""])
def test_target_rejected_before_process(target):
    with pytest.raises(CaptureError, match="TARGET_INVALID"):
        command(target, "psql")


@pytest.mark.parametrize("source,code", [
    ("import os;os.write(1,b'x'*4097)", "OUTPUT_LIMIT"),
    ("import os;os.write(2,b'private diagnostic')", "TOOL_DIAGNOSTIC"),
    ("raise SystemExit(1)", "TOOL_FAILED"),
    ("import time;time.sleep(10)", "TIMEOUT"),
])
def test_pipe_faults_close_child(source, code):
    with pytest.raises(CaptureError, match=code), running(
        [sys.executable, "-c", source], 4096, time.monotonic()+0.3,
    ) as (process, reader):
        reader.all()
    assert process.poll() is not None


def test_multiple_lines_and_eof():
    with running([sys.executable, "-c", "print('one');print('two')"],
                 4096, time.monotonic()+5) as (_, reader):
        assert reader.line() == b"one"
        assert reader.line() == b"two"
        assert reader.all() == b""


def test_partial_line_eof_denied():
    with pytest.raises(CaptureError, match="UNEXPECTED_EOF"), running(
        [sys.executable, "-c", "import os;os.write(1,b'partial')"],
        4096, time.monotonic()+5,
    ) as (_, reader):
        reader.line()


def test_capture_has_container_owned_deadline(monkeypatch):
    monkeypatch.setattr("scripts.consistent_product_backup.shutil.which", lambda _: "/bin/docker")
    argv = command("proofflow-budget", "pg_dump", "--no-owner")
    start = argv.index("timeout")
    assert argv[start:start+5] == ["timeout", "-s", "KILL", "55", "pg_dump"]
    options = next(value for value in argv if value.startswith("PGOPTIONS="))
    assert "-c idle_in_transaction_session_timeout=60000" in options


def test_broken_stdin_during_cleanup_still_kills_hanging_child():
    source = "import os,time;os.close(0);print('closed',flush=True);time.sleep(10)"
    with pytest.raises(RuntimeError, match="fixture interruption"), running(
        [sys.executable, "-c", source], 4096, time.monotonic()+5,
    ) as (process, reader):
        assert reader.line() == b"closed"
        process.stdin.write(b"buffered write")  # Flush at close raises BrokenPipeError.
        raise RuntimeError("fixture interruption")
    assert process.poll() is not None
