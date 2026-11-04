#!/bin/sh
# Dedicated no-login verifier identity, distinct from control/provider UID10001.
set -eu
test "$(id -u)" = 0
if ! getent group 10002 >/dev/null; then
    groupadd --gid 10002 pf-verifier
fi
test "$(getent group 10002 | cut -d: -f1)" = pf-verifier
if ! getent passwd 10002 >/dev/null; then
    useradd --uid 10002 --gid 10002 --no-create-home --home-dir /nonexistent \
        --shell /usr/sbin/nologin pf-verifier
fi
test "$(getent passwd 10002 | cut -d: -f1)" = pf-verifier
test "$(id -G pf-verifier)" = 10002
test "$(getent passwd 10002 | cut -d: -f6,7)" = /nonexistent:/usr/sbin/nologin
