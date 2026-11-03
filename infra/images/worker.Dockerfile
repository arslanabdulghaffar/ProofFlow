# Build locally if needed; NEVER run this image on the development/control host.
# Runtime admission requires a designated worker and all deployed Phase 1 gates.
FROM python:3.12.16-slim-trixie@sha256:1148dbb014615300fa7e713b2f94f550c0d1c69780c0805f84f093ceee34dd0b
COPY infra/images/control-build-requirements.txt /tmp/build-requirements.txt
COPY infra/images/worker-requirements.txt /tmp/requirements.txt
RUN python -m pip install --no-cache-dir --only-binary=:all: --require-hashes -r /tmp/build-requirements.txt \
    && python -m pip install --no-cache-dir --only-binary=:all: --require-hashes -r /tmp/requirements.txt \
    && python -m pip uninstall -y pip \
    && find /usr -xdev -type f -perm /6000 -exec chmod a-s {} + \
    && rm /tmp/build-requirements.txt /tmp/requirements.txt \
    && mkdir -p /input /output /scratch /opt/proofflow \
    && chown 10001:10001 /output /scratch
COPY worker/launcher.py /opt/proofflow/launcher.py
RUN chmod 0444 /opt/proofflow/launcher.py
WORKDIR /scratch
USER 10001:10001
ENTRYPOINT ["/usr/local/bin/python3", "-I", "-B", "/opt/proofflow/launcher.py"]
