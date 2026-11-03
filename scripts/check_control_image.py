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

# Fixed trusted inspection code, never supplied by a caller or an uploaded file.
# Only /usr regular files are inventoried; Debian's /bin and /sbin alias /usr.
HARDENING_PROBE = """import json, os, stat
from pathlib import Path
status = dict(line.split(':', 1) for line in Path('/proc/1/status').read_text().splitlines())
special = []
tar_modules = []
errors = []
def onerror(error):
    errors.append(str(error))
for directory, dirs, files in os.walk('/usr', followlinks=False, onerror=onerror):
    for name in files:
        path = Path(directory) / name
        mode = path.lstat().st_mode
        if stat.S_ISREG(mode) and mode & (stat.S_ISUID | stat.S_ISGID):
            special.append(str(path))
        if name == 'Tar.pm' and path.parent.name == 'Archive':
            tar_modules.append(str(path))
print(json.dumps({
    'pid1': {key: status[key].strip() for key in (
        'Uid', 'Gid', 'CapInh', 'CapPrm', 'CapEff', 'CapBnd', 'CapAmb', 'NoNewPrivs')},
    'setid_files_under_usr': sorted(special),
    'inventory_errors': errors,
    'archive_tar_modules_under_usr': sorted(tar_modules),
    'systemd_homed_present': Path('/usr/lib/systemd/systemd-homed').exists(),
    'infocmp_present': Path('/usr/bin/infocmp').exists(),
    'mount_present': Path('/usr/bin/mount').exists(),
    'nsenter_present': Path('/usr/bin/nsenter').exists(),
    'usr_aliases': {name: str(Path(name).resolve()) for name in ('/bin', '/sbin', '/lib')},
    'pid1_mapped_libraries': sorted({Path(line.split()[-1]).name
        for line in Path('/proc/1/maps').read_text().splitlines()
        if '/usr/' in line and '.so' in line}),
    'fstab_entries': [line for line in Path('/etc/fstab').read_text().splitlines()
                      if line.strip() and not line.lstrip().startswith('#')],
}))
"""


def validate_hardening(observed: dict) -> None:
    """Fail closed on absent/malformed observations or unexpected privilege."""
    status = observed["pid1"]
    for key in ("Uid", "Gid"):
        if status[key].split() != ["10001"] * 4:
            raise RuntimeError(f"Unexpected service {key}")
    for key in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"):
        if int(status[key], 16) != 0:
            raise RuntimeError(f"Unexpected service {key}")
    if status["NoNewPrivs"] != "1":
        raise RuntimeError("Service can acquire new privileges")
    for key in ("setid_files_under_usr", "inventory_errors", "fstab_entries"):
        if observed[key] != []:
            raise RuntimeError(f"Unexpected {key}: {observed[key]}")
    if observed["usr_aliases"] != {"/bin": "/usr/bin", "/sbin": "/usr/sbin", "/lib": "/usr/lib"}:
        raise RuntimeError("The /usr inventory does not cover expected Debian aliases")


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
        receipt["hardening"] = json.loads(
            docker("exec", name, "python", "-I", "-c", HARDENING_PROBE, timeout=10)
        )
        validate_hardening(receipt["hardening"])
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
