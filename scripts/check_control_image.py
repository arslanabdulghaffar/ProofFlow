"""Smoke-test only our trusted health image on a local Linux Docker host.

Never supply a candidate image. This is NOT a sandbox or deployed acceptance
test. The image must be an immutable locally built SHA-256 image ID.
"""

import argparse
import json
import re
import shutil
import subprocess
import time
import uuid


def docker(*args: str, timeout: int = 30) -> str:
    executable = shutil.which("docker")
    if executable is None:
        raise RuntimeError("Docker CLI is not installed")
    return subprocess.run(  # noqa: S603 - trusted CLI, fixed args plus validated local image ID
        [executable, *args], check=True, capture_output=True, text=True, timeout=timeout
    ).stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image_id")
    args = parser.parse_args()
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", args.image_id):
        parser.error("Use an immutable local SHA-256 image ID")
    image = json.loads(docker("image", "inspect", args.image_id))[0]
    if image["Config"]["User"] != "10001:10001":
        raise RuntimeError("Unexpected controller user")
    name = "proofflow-trusted-health-" + uuid.uuid4().hex
    # The unique name is selected before create, allowing reconciliation even
    # if the client loses the response. No volumes, ports or secrets are supplied.
    created = False
    receipt = {"scope": "local_trusted_control_only", "image_id": args.image_id}
    try:
        docker(
            "create", "--name", name, "--label", "proofflow.test=trusted-health",
            "--network", "none", "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--memory", "256m",
            "--cpus", "0.5", "--pids-limit", "32", args.image_id,
        )
        created = True
        docker("start", name)
        config = json.loads(docker("inspect", name))[0]
        host = config["HostConfig"]
        if not (
            host["NetworkMode"] == "none" and host["ReadonlyRootfs"]
            and not config["Mounts"] and not host["PortBindings"]
            and host["Memory"] == 268435456 and host["PidsLimit"] == 32
            and host["NanoCpus"] == 500000000 and host["CapDrop"] == ["ALL"]
            and "no-new-privileges" in host["SecurityOpt"]
        ):
            raise RuntimeError("Unexpected trusted container configuration")
        probe = (
            "import json,os,sys; from urllib.request import urlopen; "
            "from urllib.error import HTTPError; "
            "r=urlopen('http://127.0.0.1:8000/health/live',timeout=1); "
            "assert r.status==200 and json.load(r)=={'status':'alive'}; "
            "assert os.getuid()==10001; print(sys.version.split()[0])"
        )
        deadline = time.monotonic() + 15
        while True:
            try:
                receipt["python"] = docker("exec", name, "python", "-I", "-c", probe, timeout=3)
                break
            except subprocess.CalledProcessError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.1)
        readiness = """import json
from urllib.request import urlopen
from urllib.error import HTTPError
try:
    urlopen('http://127.0.0.1:8000/health/ready',timeout=1)
    raise RuntimeError('Unexpected readiness success')
except HTTPError as response:
    assert response.code == 503
    assert json.load(response)['reason'] == 'infrastructure_not_verified'
"""
        docker("exec", name, "python", "-I", "-c", readiness, timeout=3)
        receipt.update(liveness=200, readiness=503, uid=10001, mounts=0, network="none")
    finally:
        # Resolve only this generated test name. Never prune other containers.
        found = docker("ps", "-aq", "--filter", "name=^/" + name + "$")
        if found:
            docker("rm", "--force", name)
        elif created:
            raise RuntimeError("Test container unexpectedly disappeared")
        if docker("ps", "-aq", "--filter", "name=^/" + name + "$"):
            raise RuntimeError("Test container cleanup failed")
        receipt["cleanup"] = "confirmed_absent"
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
