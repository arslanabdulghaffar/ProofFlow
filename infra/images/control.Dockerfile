# Trusted controller health foundation ONLY, never a candidate execution image.
# Docker Official Python 3.12.16, Debian trixie, linux/amd64, inspected 2026-11-04 KST.
FROM python:3.12.16-slim-trixie@sha256:1148dbb014615300fa7e713b2f94f550c0d1c69780c0805f84f093ceee34dd0b

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY infra/images/control-build-requirements.txt /opt/proofflow/build-requirements.txt
RUN python -m pip install --no-cache-dir --only-binary=:all: --require-hashes \
    -r /opt/proofflow/build-requirements.txt
COPY infra/images/control-requirements.txt /opt/proofflow/requirements.txt
RUN python -m pip install --no-cache-dir --only-binary=:all: --require-hashes \
    -r /opt/proofflow/requirements.txt \
    && python -m pip uninstall --yes pip
# The HTTP service needs no setuid/setgid utilities. Preserve packages/notices
# and scanner visibility; this hardening does not patch their CVEs.
RUN find /usr -xdev -type f -perm /6000 -exec chmod a-s {} +
COPY api /app/api
USER 10001:10001
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "api.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--no-server-header", "--no-proxy-headers"]
