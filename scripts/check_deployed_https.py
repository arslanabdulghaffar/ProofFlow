"""Verify private Vultr HTTPS over an exact-host-key operator SSH tunnel."""

import hashlib
import json
import socket
import ssl
import subprocess
import time
import urllib.error
import urllib.request

from vultr_phase1 import PRIVATE, Admin

admin = Admin()
tunnel = None
try:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    address = admin.state["hosts"]["control"]["address"]
    args = ["C:/Windows/System32/OpenSSH/ssh.exe", "-F", "NUL", "-N",
            "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
            "-o", "HostKeyAlgorithms=ssh-ed25519", "-o", "IdentitiesOnly=yes",
            "-o", "ExitOnForwardFailure=yes", "-o", "ConnectTimeout=10",
            "-o", "UserKnownHostsFile=" + str(PRIVATE / "known_hosts"),
            "-p", "443", "-i", str(PRIVATE / "operator_ed25519"),
            "-L", f"127.0.0.1:{port}:127.0.0.1:8443", "root@" + address]
    tunnel = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,  # noqa: S603
                              creationflags=subprocess.CREATE_NO_WINDOW)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.load_verify_locations(str(PRIVATE / "tls/ca.pem"))
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                        urllib.request.HTTPSHandler(context=context))
    deadline = time.monotonic() + 15
    base = f"https://127.0.0.1:{port}"
    while True:
        try:
            with opener.open(base + "/health/live", timeout=2) as response:
                alive = response.status, json.loads(response.read(1024))
            break
        except urllib.error.URLError:
            if time.monotonic() >= deadline or tunnel.poll() is not None:
                raise RuntimeError("DEPLOYED_HTTPS_UNAVAILABLE") from None
            time.sleep(0.2)
    if alive != (200, {"status": "alive"}):
        raise RuntimeError("LIVENESS_MISMATCH")
    for path, expected in (("/health/ready", 503), ("/v1/jobs", 404), ("/docs", 404)):
        try:
            opener.open(base + path, timeout=3).close()
        except urllib.error.HTTPError as error:
            if error.code != expected:
                raise RuntimeError("HEALTH_SURFACE_MISMATCH") from None
        else:
            raise RuntimeError("PREMATURE_ADMISSION_OR_ROUTE")
    untrusted = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                           urllib.request.HTTPSHandler())
    try:
        untrusted.open(base + "/health/live", timeout=3).close()
    except urllib.error.URLError as error:
        if not isinstance(error.reason, ssl.SSLCertVerificationError):
            raise RuntimeError("TLS_NEGATIVE_CONTROL_INCONCLUSIVE") from None
    else:
        raise RuntimeError("UNTRUSTED_CA_ACCEPTED")
    with socket.create_connection(("127.0.0.1", port), timeout=3) as raw:
        with context.wrap_socket(raw, server_hostname="127.0.0.1") as secure:
            tls_version = secure.version()
            fingerprint = hashlib.sha256(secure.getpeercert(binary_form=True)).hexdigest()
    report = {"scope": "actual_vultr_operator_https_over_pinned_ssh",
              "liveness": 200, "readiness": 503, "unimplemented_routes": 404,
              "untrusted_ca": "rejected", "tls_version": tls_version,
              "certificate_der_sha256": fingerprint, "anonymous_public_access": False,
              "application_ready": False}
    (PRIVATE / "evidence/https-health.json").write_bytes(json.dumps(report).encode())
    print(json.dumps(report))
finally:
    if tunnel is not None:
        tunnel.terminate()
        tunnel.wait(timeout=5)
    admin.close()
