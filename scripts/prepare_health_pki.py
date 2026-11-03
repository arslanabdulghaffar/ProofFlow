"""Trusted local private-CA leaf creation; no CA key is transferred to a server."""

import os
import subprocess
from pathlib import Path

root = Path("/mnt/c/Users/IT/.proofflow/deployment/tls")
os.umask(0o077)
if any((root / ("health." + suffix)).exists() for suffix in ("key", "pem", "csr")):
    raise SystemExit("EXISTING_HEALTH_IDENTITY_PRESERVED")
extension = root / "health-extension.txt"
extension.write_text("basicConstraints=critical,CA:FALSE\n"
                     "keyUsage=critical,digitalSignature\n"
                     "extendedKeyUsage=serverAuth\nsubjectAltName=IP:127.0.0.1\n")
commands = [
    ["req", "-new", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1",
     "-nodes", "-keyout", str(root / "health.key"), "-out", str(root / "health.csr"),
     "-subj", "/CN=ProofFlow operator health"],
    ["x509", "-req", "-in", str(root / "health.csr"), "-CA", str(root / "ca.pem"),
     "-CAkey", str(root / "ca.key"), "-set_serial", "4", "-days", "25",
     "-extfile", str(extension), "-out", str(root / "health.pem")],
]
for command in commands:
    subprocess.run(["/usr/bin/openssl", *command], check=True, timeout=20,  # noqa: S603
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
print("Private operator-health certificate created; CA key stays local.")
