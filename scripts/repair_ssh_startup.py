"""Repair observed socket/service boot mismatch without weakening SSH host pins.

Temporary forwarding uses the operator key locally on both SSH connections; no
key or agent is forwarded to the worker. Existing port22 and443 scope is retained.
"""

import json
import socket
import subprocess
import time

from vultr_phase1 import PRIVATE, Admin

FIX = b"""import hashlib,json,subprocess
from pathlib import Path
path=Path('/etc/ssh/sshd_config.d/00-proofflow-ports.conf')
data=b'Port 22\\nPort 443\\nListenAddress 0.0.0.0\\n'
if path.exists():
    if path.read_bytes()!=data: raise SystemExit('SSH_CONFIG_CONFLICT')
else:
    with path.open('xb') as output: output.write(data)
    path.chmod(0o644)
def run(args):
    result=subprocess.run(args,capture_output=True,check=True,timeout=20)
    return result.stdout.decode()
run(['/usr/sbin/sshd','-t'])
effective=run(['/usr/sbin/sshd','-T'])
if sorted(x for x in effective.splitlines() if x.startswith('port '))!=['port 22','port 443']:
    raise SystemExit('UNEXPECTED_SSH_PORTS')
if ('passwordauthentication no' not in effective
        or 'permitrootlogin prohibit-password' not in effective):
    # OpenSSH normalizes prohibit-password to without-password on some versions.
    if ('passwordauthentication no' not in effective
            or 'permitrootlogin without-password' not in effective):
        raise SystemExit('SSH_KEY_ONLY_REQUIRED')
run(['/usr/bin/systemctl','disable','ssh.socket'])
run(['/usr/bin/systemctl','enable','ssh.service'])
run(['/usr/bin/systemctl','reload','ssh.service'])
print(json.dumps({'ports':[22,443],'password_authentication':False,'key_only_root':True,
 'config_sha256':hashlib.sha256(data).hexdigest(),'socket':'disabled','service':'enabled'}))
"""

admin = Admin()
tunnel = None
try:
    base = [
        "C:/Windows/System32/OpenSSH/ssh.exe",
        "-F",
        "NUL",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "HostKeyAlgorithms=ssh-ed25519",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "ConnectTimeout=5",
        "-o",
        "UserKnownHostsFile=" + str(PRIVATE / "known_hosts"),
        "-i",
        str(PRIVATE / "operator_ed25519"),
    ]
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    tunnel = subprocess.Popen(  # noqa: S603 - exact project worker and pinned local key
        base
        + [
            "-p",
            "443",
            "-N",
            "-o",
            "ExitOnForwardFailure=yes",
            "-L",
            f"127.0.0.1:{port}:10.77.0.3:22",
            "root@" + admin.state["hosts"]["worker"]["address"],
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    time.sleep(1)
    alias = "[" + admin.state["hosts"]["control"]["address"] + "]:443"
    inner = base + ["-o", "HostKeyAlias=" + alias, "-p", str(port), "root@127.0.0.1"]
    identity = (
        subprocess.run(  # noqa: S603 - fixed trusted SSH identity readback
            inner + ["cat /etc/machine-id"],
            capture_output=True,
            check=True,
            timeout=15,
        )
        .stdout.decode()
        .strip()
    )
    if identity != admin.state["control_machine_id"]:
        raise RuntimeError("CONTROL_IDENTITY_CHANGED")
    result = subprocess.run(  # noqa: S603 - fixed reviewed SSH repair, not candidate content
        inner + ["/usr/bin/python3 -I -S -B -"],
        input=FIX,
        capture_output=True,
        check=True,
        timeout=45,
    )
    reports = {"control": json.loads(result.stdout)}
    # Verify public administrative recovery before applying the same fix to worker.
    check = admin.host("control", "cat /etc/machine-id")
    if check.returncode or check.stdout.decode().strip() != identity:
        raise RuntimeError("CONTROL_DIRECT_RECOVERY_FAILED")
    result = admin.host("worker", "/usr/bin/python3 -I -S -B -", stdin=FIX)
    if result.returncode:
        raise RuntimeError("WORKER_SSH_FIX_FAILED")
    reports["worker"] = json.loads(result.stdout)
    (PRIVATE / "evidence/ssh-boot-repair.json").write_bytes(json.dumps(reports).encode())
    print(json.dumps(reports))
finally:
    if tunnel:
        tunnel.terminate()
        tunnel.wait(timeout=5)
    admin.close()
