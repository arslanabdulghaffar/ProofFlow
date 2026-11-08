"""Observe the real90s recovery-container deadline after its launcher exits.

Empty trusted PostgreSQL only. No saved backup, secrets, candidates or cloud calls.
The parent observes; successful removal must come from timeout/AutoRemove, not finally.
"""

import json
import subprocess
import sys
import time
from uuid import uuid4

from scripts.check_budget_postgres import docker, require


def main():
    token = uuid4().hex
    name = "proofflow-saved-restore-" + token
    child = ("from scripts.rehearse_saved_database import create_args;"
             "from scripts.check_budget_postgres import docker;"
             "import sys;name=sys.argv[1];token=sys.argv[2];"
             "docker(*create_args(name,'proofflow.saved-restore='+token));"
             "docker('start',name)")
    started = time.monotonic()
    since = str(int(time.time()))
    try:
        subprocess.run([sys.executable, "-c", child, name, token],  # noqa: S603 - fixed trusted source
                       capture_output=True, check=True, timeout=15)
        require(bool(docker("ps", "-q", "--filter", "name=^/"+name+"$")),
                "SAVED_WATCHDOG_POSITIVE_CONTROL_FAILED")
        while docker("ps", "-aq", "--filter", "name=^/"+name+"$"):
            require(time.monotonic()-started < 105, "SAVED_WATCHDOG_TIMEOUT_FAILED")
            time.sleep(1)
        elapsed = time.monotonic()-started
        require(85 <= elapsed < 105, "SAVED_WATCHDOG_UNEXPECTED_EXIT")
        events = docker("events", "--since", since, "--until", str(int(time.time())+1),
                        "--filter", "container="+name, "--filter", "event=die",
                        "--format", "{{json .}}")
        events = [json.loads(line) for line in events.splitlines() if line]
        require(len(events) == 1 and events[0]["Actor"]["Attributes"]["exitCode"] == "137",
                "SAVED_WATCHDOG_KILL_NOT_OBSERVED")
        print(json.dumps({"scope": "empty_local_postgres_no_backup_or_credentials",
                          "launcher_exited_before_timeout": True, "watchdog_seconds": 90,
                          "container_exit": 137,
                          "observed_seconds": round(elapsed, 3), "container_removed": True,
                          "observer_issued_cleanup": False, "cloud_calls": 0}))
    finally:
        if docker("ps", "-aq", "--filter", "name=^/"+name+"$"):
            observed = json.loads(docker("inspect", name))[0]
            require(observed["Config"]["Labels"].get("proofflow.saved-restore") == token,
                    "SAVED_WATCHDOG_FOREIGN_CONTAINER")
            docker("rm", "--force", name)


if __name__ == "__main__":
    main()
