"""Trusted administrator deployment of probe transport; no candidate runs on control."""

import hashlib
import io
import ipaddress
import json
import ssl
import tarfile

from deploy_worker import IMAGE, ROOTFS, RUNTIME
from vultr_phase1 import PRIVATE, ROOT, Admin

a = Admin()


def host(role, cmd, data=None):
    r = a.host(role, cmd, stdin=data, timeout=90)
    if r.returncode:
        raise RuntimeError(role + " trusted setup failed")
    return r.stdout


control_machine = host("control", "cat /etc/machine-id").decode().strip()
net = {}
for role in ("control", "worker"):
    vpcs = a.request("GET", "/instances/" + a.state["resources"]["vm_" + role] + "/vpcs")["vpcs"]
    item = next(x for x in vpcs if x["id"] == a.state["resources"]["vpc"])
    address = str(ipaddress.IPv4Address(item["ip_address"]))
    if ipaddress.IPv4Address(address) not in ipaddress.ip_network("10.77.0.0/24"):
        raise RuntimeError("UNEXPECTED_PRIVATE_NETWORK")
    net[role] = address
names = (
    "__init__",
    "runtime",
    "launcher",
    "host",
    "start_gate",
    "staging",
    "collector",
    "protocol",
    "journal",
    "supervisor",
    "log_capture",
    "rootfs",
    "wire",
    "service",
    "entrypoint",
    "metrics",
    "runtime_bundle",
)
sources = {
    name: hashlib.sha256((ROOT / "worker" / (name + ".py")).read_bytes()).hexdigest()
    for name in names
}
runtime = json.loads((ROOT / "infra/gvisor/runsc-release.json").read_bytes())
identity = {
    "runtime": "runsc",
    "platform": "systrap",
    "runtime_sha256": runtime["members"]["runsc"]["sha256"],
    "runtime_bundle_sha256": RUNTIME,
    "image_sha256": IMAGE,
    "rootfs_sha256": ROOTFS,
    "supervisor_sha256": hashlib.sha256(json.dumps(sources, sort_keys=True).encode()).hexdigest(),
    "host_tag": hashlib.sha256(a.state["worker_machine_id"].encode()).hexdigest(),
}
config = {
    "control_machine_id": control_machine,
    "worker_address": net["worker"],
    "control_address": net["control"],
    "runtime_identity": identity,
    "runtime_sha256": hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest(),
    "worker_certificate_sha256": hashlib.sha256(
        ssl.PEM_cert_to_DER_cert((PRIVATE / "tls/worker.pem").read_text())
    ).hexdigest(),
}
buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode="w") as archive:

    def add(name, data, mode=0o600):
        item = tarfile.TarInfo(name)
        item.size = len(data)
        item.mode = mode
        archive.addfile(item, io.BytesIO(data))

    for package in ("worker", "orchestrator"):
        for path in sorted((ROOT / package).glob("*.py")):
            add("lib/" + package + "/" + path.name, path.read_bytes(), 0o644)
    for name in ("ca.pem", "controller.pem", "controller.key", "unapproved.pem", "unapproved.key"):
        add("tls/" + name, (PRIVATE / "tls" / name).read_bytes())
    add("worker.json", json.dumps(config, sort_keys=True).encode())
host(
    "control",
    "install -d -m 0700 /opt/proofflow-control /var/lib/proofflow-control/probes && "
    "tar -xf - -C /opt/proofflow-control --no-same-owner",
    buf.getvalue(),
)
host("worker", "ufw allow from " + net["control"] + " to " + net["worker"] + " port 9443 proto tcp")
host(
    "control", "ufw allow from " + net["worker"] + " to " + net["control"] + " port 9444 proto tcp"
)
host("worker", "umask 077; printf 'host-only-marker' > /var/lib/proofflow-setup/host-marker")
a.state["control_machine_id"] = control_machine
a.state["private_addresses"] = net
a.state["probe_controller"] = {"runtime_sha256": config["runtime_sha256"], "installed": True}
a.save()
print(
    "Trusted controller transport/PKI installed; independent runtime pins; private firewall."
)
a.close()
