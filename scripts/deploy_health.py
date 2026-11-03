"""Deploy the trusted empty HTTPS health shell, loopback only behind pinned SSH."""

import hashlib
import json

from deploy_control_images import CONTROL
from vultr_phase1 import PRIVATE, Admin

admin = Admin()
try:

    def host(command, data=None):
        result = admin.host("control", command, stdin=data)
        if result.returncode:
            raise RuntimeError("HEALTH_DEPLOYMENT_FAILED_REQUIRES_READBACK")
        return result.stdout

    if host("cat /etc/machine-id").decode().strip() != admin.state["control_machine_id"]:
        raise RuntimeError("CONTROL_HOST_CHANGED")
    host("install -d -o 10001 -g 10001 -m 0700 /etc/proofflow-health")
    for name in ("health.pem", "health.key", "ca.pem"):
        destination = "/etc/proofflow-health/" + name
        host("set -C; umask 077; cat > " + destination, (PRIVATE / "tls" / name).read_bytes())
        host("chown 10001:10001 " + destination + " && chmod 0400 " + destination)
    host(
        "docker create --name proofflow-health --pull=never --label proofflow.role=health "
        "--read-only --cap-drop=ALL --security-opt=no-new-privileges --user=10001:10001 "
        "--memory=256m --memory-swap=256m --cpus=0.5 --pids-limit=32 "
        "--ulimit core=0 --ulimit nofile=128:128 -p 127.0.0.1:8443:8443 "
        "--mount type=bind,src=/etc/proofflow-health,dst=/etc/proofflow-health,readonly "
        "sha256:" + CONTROL + " python -m uvicorn api.app.main:app --host 0.0.0.0 --port 8443 "
        "--no-access-log --no-server-header --no-proxy-headers --workers 1 "
        "--limit-concurrency 8 --timeout-keep-alive 2 "
        "--ssl-keyfile /etc/proofflow-health/health.key "
        "--ssl-certfile /etc/proofflow-health/health.pem"
    )
    unit = b"""[Unit]
Description=ProofFlow private operator HTTPS health
Requires=docker.service
After=docker.service
[Service]
ExecStart=/usr/bin/docker start -a proofflow-health
ExecStop=/usr/bin/docker stop -t 10 proofflow-health
Restart=on-failure
RestartSec=3
TimeoutStopSec=20
[Install]
WantedBy=multi-user.target
"""
    host("set -C; cat > /etc/systemd/system/proofflow-health.service", unit)
    host("systemctl daemon-reload && systemctl enable --now proofflow-health.service")
    # Persist a restrictive Docker socket mode across daemon/socket restarts.
    host("install -d -m 0755 /etc/systemd/system/docker.socket.d")
    host(
        "cat > /etc/systemd/system/docker.socket.d/proofflow.conf",
        b"[Socket]\nSocketMode=0600\nSocketGroup=root\n",
    )
    host("chmod 0600 /var/run/docker.sock && systemctl daemon-reload")
    report = {
        "image": CONTROL,
        "surface": "operator_https_over_pinned_ssh_loopback_only",
        "tls_leaf_sha256": hashlib.sha256((PRIVATE / "tls/health.pem").read_bytes()).hexdigest(),
        "ready": "503_until_product_admission_exists",
        "public_release": False,
    }
    (PRIVATE / "evidence/health-install.json").write_bytes(json.dumps(report).encode())
    print(json.dumps(report))
finally:
    admin.close()
