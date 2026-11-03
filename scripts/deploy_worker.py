"""Trusted Windows administrator upload of the exact reviewed worker artifact set."""

import hashlib
import io
import ipaddress
import json
import ssl
import subprocess
import tarfile

from vultr_phase1 import PRIVATE, ROOT, Admin

IMAGE = "2f6e7eeff7d8c66ec76010b2c19f4f1420abdeb28039e7a887f1878e258ccf96"
ROOTFS = "98f64a3b6b9276f012aa1894089b7dbb0397c56479758cb8325ed0be00707393"
RUNTIME = "7c50f528e54024e3c5b3fd05a28c6c46288c39c41701249bd8e53ce590133cbe"


def checked_host(admin, command, *, stdin=None, timeout=90):
    result = admin.host("worker", command, stdin=stdin, timeout=timeout)
    if result.returncode:
        raise RuntimeError("WORKER_ADMIN_COMMAND_FAILED")
    return result.stdout


def fingerprint(path):
    return hashlib.sha256(ssl.PEM_cert_to_DER_cert(path.read_text())).hexdigest()


def deploy(admin):
    if admin.state.get("credit_guard", {}).get("admission_closed"):
        raise RuntimeError("CREDIT_ADMISSION_CLOSED")
    machine = checked_host(admin, "cat /etc/machine-id").decode().strip()
    if machine != admin.state["worker_machine_id"]:
        raise RuntimeError("WORKER_MACHINE_ID_CHANGED")
    vpcs = admin.request("GET", "/instances/" + admin.state["resources"]["vm_worker"]
                         + "/vpcs")["vpcs"]
    vpc = next(v for v in vpcs if v["id"] == admin.state["resources"]["vpc"])
    address = str(ipaddress.IPv4Address(vpc["ip_address"]))
    if ipaddress.IPv4Address(address) not in ipaddress.ip_network("10.77.0.0/24"):
        raise RuntimeError("WORKER_VPC_ADDRESS_CHANGED")
    bundle_path = PRIVATE / "worker-install.tar.gz"
    manifest = {"machine_id": machine, "files": {}}
    runtime_path = ROOT / "infra/gvisor/runsc-release.json"
    runtime_raw = runtime_path.read_bytes()
    if hashlib.sha256(runtime_raw).hexdigest() != RUNTIME:
        raise RuntimeError("RUNTIME_MANIFEST_CHANGED")
    runtime = json.loads(runtime_raw)
    config = {"machine_id": machine, "bind_address": address,
              "image_sha256": IMAGE, "rootfs_sha256": ROOTFS,
              "runsc_sha256": runtime["members"]["runsc"]["sha256"],
              "controller_certificate_sha256": fingerprint(PRIVATE / "tls/controller.pem"),
              "runtime_bundle_sha256": RUNTIME}
    with tarfile.open(bundle_path, "w:gz") as archive:
        def add(name, data, destination, mode):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o600
            archive.addfile(info, io.BytesIO(data))
            manifest["files"][name] = {"destination": destination, "mode": mode,
                                        "sha256": hashlib.sha256(data).hexdigest()}
        for source in sorted((ROOT / "worker").glob("*.py")):
            add("code/" + source.name, source.read_bytes(),
                "/opt/proofflow-worker/worker/" + source.name, 0o644)
        for name, pin in runtime["members"].items():
            data = (ROOT / ".tools/gvisor/release-20261102.0/bin" / name).read_bytes()
            if len(data) != pin["bytes"] or hashlib.sha256(data).hexdigest() != pin["sha256"]:
                raise RuntimeError("RUNTIME_MEMBER_CHANGED")
            add("bin/" + name, data, "/usr/local/bin/" + name, 0o755)
        add("runtime.json", runtime_raw, "/etc/proofflow-worker/runtime.json", 0o600)
        for name in ("rootfs.squashfs", "import.json"):
            data = subprocess.run(  # noqa: S603 - fixed trusted local artifact, never executed
                ["C:/Windows/System32/wsl.exe", "-d", "Ubuntu-24.04", "--", "cat",
                 "/var/tmp/proofflow-rootfs-tmp-fixed-final/" + name],  # noqa: S108 - pinned private blob
                capture_output=True, check=True, timeout=60).stdout
            if name == "rootfs.squashfs" and hashlib.sha256(data).hexdigest() != ROOTFS:
                raise RuntimeError("ROOTFS_ARTIFACT_CHANGED")
            add("image/" + name, data,
                "/var/lib/proofflow-worker/images/" + IMAGE + "/" + name, 0o400)
        for name in ("ca.pem", "worker.pem", "worker.key"):
            add("tls/" + name, (PRIVATE / "tls" / name).read_bytes(),
                "/etc/proofflow-worker/tls/" + name, 0o600)
        add("service.json", json.dumps(config, sort_keys=True).encode(),
            "/etc/proofflow-worker/service.json", 0o600)
        add("service.unit", (ROOT / "infra/systemd/proofflow-worker.service").read_bytes(),
            "/etc/systemd/system/proofflow-worker.service", 0o644)
        raw = json.dumps(manifest, sort_keys=True).encode()
        info = tarfile.TarInfo("manifest.json")
        info.size = len(raw)
        archive.addfile(info, io.BytesIO(raw))
    raw = bundle_path.read_bytes()
    expected = hashlib.sha256(raw).hexdigest()
    print(json.dumps({"worker_bundle_bytes": len(raw), "sha256": expected}), flush=True)
    checked_host(admin, "umask 077; cat > /var/lib/proofflow-setup/worker-install.tar.gz",
                 stdin=raw, timeout=180)
    observed = checked_host(admin,
                            "sha256sum /var/lib/proofflow-setup/worker-install.tar.gz")
    if observed.decode().split()[0] != expected:
        raise RuntimeError("WORKER_UPLOAD_HASH_MISMATCH")
    source = (ROOT / "scripts/install_worker_host.py").read_bytes()
    checked_host(admin, "umask 077; cat > /var/lib/proofflow-setup/install_worker_host.py",
                 stdin=source)
    install_command = "/usr/bin/python3 -I -S -B /var/lib/proofflow-setup/install_worker_host.py"
    result = checked_host(admin, install_command, timeout=90)
    admin.state["worker_install"] = {"bundle_sha256": expected, "vpc_address": address,
                                      "worker_certificate_sha256": fingerprint(
                                          PRIVATE / "tls/worker.pem"),
                                      "acceptance": "NOT_RUN"}
    admin.save()
    return json.loads(result)


if __name__ == "__main__":
    admin = Admin()
    try:
        print(json.dumps(deploy(admin)))
    finally:
        admin.close()
