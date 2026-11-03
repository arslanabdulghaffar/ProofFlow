# Trusted database image; no candidate execution. Run as postgres, never root.
FROM postgres:18.6-alpine3.24@sha256:10a5c69a83035ab5239f5620d708520e8b28f5aa1f2b20143e6024532edadfb5
# Fixed stable-branch security updates; unavailable versions fail the build.
RUN apk add --no-cache brotli-libs=1.2.1-r0 libcurl=8.23.0-r0 \
    && rm /usr/local/bin/gosu \
    && find /usr /bin /sbin -xdev -type f -perm /6000 -exec chmod a-s {} +
USER 70:70
