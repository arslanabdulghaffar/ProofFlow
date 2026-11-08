"""Root-only pinned ACME client installation; no certificate request or public listener."""

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C", "PIP_CONFIG_FILE": "/dev/null"}


def run(args, timeout=180):
    result = subprocess.run(args, capture_output=True, timeout=timeout, env=ENV)  # noqa: S603
    if result.returncode:
        raise RuntimeError("ACME_CLIENT_INSTALL_FAILED")
    return result.stdout.decode().strip()


def main():
    if os.geteuid() != 0:
        raise RuntimeError("ROOT_REQUIRED")
    requirements = Path(__file__).with_name("acme-requirements.txt")
    required = dict(re.findall(r"^([a-z0-9-]+)==([^\s]+)", requirements.read_text(), re.M))
    if required.get("certbot") != "5.9.0" or len(required) != 18:
        raise RuntimeError("ACME_DEPENDENCY_SET_CHANGED")
    venv = Path("/opt/proofflow-acme")
    if not venv.exists():
        run(["/usr/bin/python3", "-m", "venv", str(venv)])
    if venv.is_symlink() or venv.stat().st_uid != 0:
        raise RuntimeError("ACME_ENVIRONMENT_UNTRUSTED")
    run([str(venv / "bin/python"), "-m", "pip", "install", "--no-input", "--no-cache-dir",
         "--require-hashes", "--only-binary=:all:", "--no-deps", "--index-url",
         "https://pypi.org/simple", "-r", str(requirements)])
    script = ("import importlib.metadata,json; print(json.dumps({"
              "d.metadata['Name'].lower().replace('_','-'):d.version "
              "for d in importlib.metadata.distributions()}))")
    installed = json.loads(run([str(venv / "bin/python"), "-I", "-c", script]))
    if any(installed.get(name) != version for name, version in required.items()):
        raise RuntimeError("ACME_INSTALLED_VERSIONS_CHANGED")
    for directory in ("/etc/proofflow-acme", "/var/lib/proofflow-acme", "/var/log/proofflow-acme"):
        path = Path(directory)
        if not path.exists():
            path.mkdir(mode=0o700)
        if path.is_symlink() or path.stat().st_uid != 0 or path.stat().st_mode & 0o777 != 0o700:
            raise RuntimeError("ACME_STATE_NOT_PRIVATE")
    print(json.dumps({"client": run([str(venv / "bin/certbot"), "--version"]),
                      "packages": len(required), "requirements_sha256":
                      hashlib.sha256(requirements.read_bytes()).hexdigest(),
                      "certificate_requested": False}))


if __name__ == "__main__":
    main()
