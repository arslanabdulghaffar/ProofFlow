# Trusted control foundation and fixed provider adapter; never execute candidates.
FROM python:3.12.16-slim-trixie@sha256:1148dbb014615300fa7e713b2f94f550c0d1c69780c0805f84f093ceee34dd0b
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY infra/images/control-build-requirements.txt /tmp/build-requirements.txt
COPY infra/images/inference-check-requirements.txt /tmp/requirements.txt
RUN python -m pip install --no-cache-dir --only-binary=:all: --require-hashes -r /tmp/build-requirements.txt \
    && python -m pip install --no-cache-dir --only-binary=:all: --require-hashes -r /tmp/requirements.txt \
    && python -m pip uninstall -y pip \
    && find /usr -xdev -type f -perm /6000 -exec chmod a-s {} + \
    && rm /tmp/build-requirements.txt /tmp/requirements.txt
COPY api/ /app/api/
COPY orchestrator/ /app/orchestrator/
USER 10001:10001
CMD ["python", "-m", "uvicorn", "api.app.main:app", "--host", "127.0.0.1", "--port", "8000", "--no-access-log", "--no-server-header", "--no-proxy-headers"]
