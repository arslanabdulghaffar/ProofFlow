#!/bin/sh
# Trusted control-host installation. Uses the previously verified official repository.
set -eu
test "$(id -u)" = 0
test -f /var/lib/proofflow-setup/cloud-init-ready
echo '1500c1f56fa9e26b9b8f42452a553675796ade0807cdce11975eb98170b3a570  /etc/apt/keyrings/docker.asc' | sha256sum -c -
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    docker-ce=5:29.9.2-1~ubuntu.24.04~noble \
    docker-ce-cli=5:29.9.2-1~ubuntu.24.04~noble \
    containerd.io=2.4.2-3~ubuntu.24.04~noble
install -d -m 0755 /etc/docker
test ! -e /etc/docker/daemon.json
cat > /etc/docker/daemon.json <<'EOF'
{"log-driver":"local","log-opts":{"max-size":"10m","max-file":"3"},"live-restore":true,"no-new-privileges":true}
EOF
systemctl restart docker
docker --host=unix:///var/run/docker.sock version --format '{{.Server.Version}}'
# Docker's management socket is root only; no group grants to application identities.
chmod 0600 /var/run/docker.sock
install -d -m 0755 /etc/systemd/system/docker.socket.d
cat > /etc/systemd/system/docker.socket.d/10-proofflow.conf <<'EOF'
[Socket]
SocketMode=0600
SocketGroup=root
EOF
systemctl daemon-reload
test "$(stat -c '%a:%U' /var/run/docker.sock)" = 600:root
