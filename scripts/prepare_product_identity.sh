#!/bin/sh
# Private API/dispatcher identity. Secrets are separate, restricted container mounts.
set -eu
test "$(id -u)" = 0
if ! getent group 10003 >/dev/null; then
    groupadd --gid 10003 pf-product
fi
test "$(getent group 10003 | cut -d: -f1)" = pf-product
if ! getent passwd 10003 >/dev/null; then
    useradd --uid 10003 --gid 10003 --no-create-home --home-dir /nonexistent \
        --shell /usr/sbin/nologin pf-product
fi
test "$(getent passwd 10003 | cut -d: -f1)" = pf-product
test "$(id -G pf-product)" = 10003
test "$(getent passwd 10003 | cut -d: -f6,7)" = /nonexistent:/usr/sbin/nologin
