FROM python:3.12.16-slim-trixie@sha256:1148dbb014615300fa7e713b2f94f550c0d1c69780c0805f84f093ceee34dd0b
RUN python -m pip uninstall -y pip && find / -xdev -type f -perm /6000 -exec chmod a-s {} +
COPY --chmod=0444 contracts/__init__.py contracts/codec.py contracts/scalars.py contracts/source.py contracts/policy.py /opt/proofflow/contracts/
COPY --chmod=0444 verifier/__init__.py verifier/outputs.py verifier/lineage.py verifier/reference.py verifier/compare.py verifier/canaries.py verifier/protocol.py verifier/entrypoint.py /opt/proofflow/verifier/
COPY --chmod=0444 infra/images/verifier_main.py /opt/proofflow/verifier_main.py
RUN find /opt/proofflow -type d -exec chmod 0555 {} +
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 10002:10002
ENTRYPOINT ["/usr/local/bin/python3", "-I", "-B", "/opt/proofflow/verifier_main.py"]
