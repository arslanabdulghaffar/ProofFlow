# Trusted API/dispatcher image. Uploaded code is data sent only to the isolated worker.
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
COPY api /app/api
COPY contracts /app/contracts
COPY orchestrator /app/orchestrator
COPY verifier /app/verifier
COPY worker /app/worker
RUN find /app -type d -exec chmod 0555 {} + && find /app -type f -exec chmod 0444 {} +
USER 10003:10003
CMD ["python", "-m", "api.app.product_bootstrap"]
