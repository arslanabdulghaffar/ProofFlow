#!/bin/sh
# Trusted control-host package preparation. Official Docker apt source only.
set -eu
test "$(id -u)" = 0
. /etc/os-release
test "$ID" = ubuntu
test "$VERSION_CODENAME" = noble
test "$(dpkg --print-architecture)" = amd64
test -f /var/lib/proofflow-setup/cloud-init-ready
install -d -m 0755 /etc/apt/keyrings
curl --fail --silent --show-error --proto '=https' --tlsv1.2 --max-time 30 \
    https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod 0644 /etc/apt/keyrings/docker.asc
cat > /etc/apt/sources.list.d/docker.sources <<'EOF'
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: noble
Components: stable
Architectures: amd64
Signed-By: /etc/apt/keyrings/docker.asc
EOF
apt-get update -qq
sha256sum /etc/apt/keyrings/docker.asc
apt-cache policy docker-ce docker-ce-cli containerd.io | head -60
