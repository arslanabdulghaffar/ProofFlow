"""Trusted administrator network positive controls; no candidate code on hosts.

Temporary ingress is restricted to the recorded worker address. The public test
target is the existing control SSH listener; no product is published.
"""

import ipaddress
import json
from datetime import UTC, datetime

from vultr_phase1 import PRIVATE, Admin


def main():
    admin = Admin()
    try:
        def host(role, command, data=None):
            result = admin.host(role, command, stdin=data, timeout=90)
            if result.returncode:
                raise RuntimeError("NETWORK_CONTROL_SETUP_FAILED")
            return result.stdout

        public = {role: str(ipaddress.IPv4Address(admin.state["hosts"][role]["address"]))
                  for role in ("control", "worker")}
        private = {role: str(ipaddress.IPv4Address(admin.state["private_addresses"][role]))
                   for role in ("control", "worker")}
        route = "/firewalls/" + admin.state["resources"]["firewall_control"] + "/rules"
        matches = [r for r in admin.request("GET", route)["firewall_rules"]
                   if r.get("notes") == "ProofFlow temporary network positive control"]
        if not matches:
            if admin.state.get("network_rule_intent"):
                raise RuntimeError("UNCERTAIN_NETWORK_RULE_REQUIRES_READBACK")
            admin.state["network_rule_intent"] = {"time": datetime.now(UTC).isoformat()}
            admin.save()
            admin.request("POST", route, {"ip_type": "v4", "protocol": "tcp",
                          "subnet": public["worker"], "subnet_size": 32, "port": "443",
                          "notes": "ProofFlow temporary network positive control"})
            matches = [r for r in admin.request("GET", route)["firewall_rules"]
                       if r.get("notes") == "ProofFlow temporary network positive control"]
        if (len(matches) != 1 or matches[0]["subnet"] != public["worker"]
                or matches[0]["subnet_size"] != 32 or matches[0]["port"] != "443"
                or matches[0]["protocol"] != "tcp"):
            raise RuntimeError("NETWORK_RULE_READBACK_MISMATCH")
        admin.state["network_rule_id"] = matches[0]["id"]
        admin.save()
        # Match the source at host ingress; destination can be translated by the
        # provider before UFW. Never widen the source beyond this worker /32.
        host("control", "ufw allow from " + public["worker"] + " to any port 443 proto tcp")
        listener = """import socket
with socket.socket() as server:
    server.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
    server.bind((ADDRESS,9444))
    server.listen(4)
    while True:
        connection,_=server.accept()
        with connection:
            connection.settimeout(1)
            connection.sendall(b'PF_NETWORK_POSITIVE_CONTROL')
""".replace("ADDRESS", repr(private["control"]))
        host("control", "install -d -m 0755 /usr/local/libexec")
        host("control", "cat > /usr/local/libexec/proofflow-network-probe.py", listener.encode())
        host("control", "chmod 0644 /usr/local/libexec/proofflow-network-probe.py")
        host("control", "systemd-run --quiet --unit=proofflow-network-probe "
             "--property=RuntimeMaxSec=600 --property=MemoryMax=33554432 "
             "--property=TasksMax=16 --property=CPUQuota=10% --property=User=nobody "
             "--property=NoNewPrivileges=yes /usr/bin/python3 -I -B "
             "/usr/local/libexec/proofflow-network-probe.py")
        targets = {"private_control": [private["control"], 9444],
                   "private_worker": [private["worker"], 9443],
                   "controlled_external": [public["control"], 443],
                   "external_ipv4": ["1.1.1.1", 443],
                   "external_ipv6": ["2606:4700:4700::1111", 443],
                   "metadata": ["169.254.169.254", 80]}
        raw = json.dumps(targets).encode()
        host("control", "umask 077; cat > /opt/proofflow-control/network-targets.json", raw)
        # This fixed host-side socket checker is administrator code, with no uploaded
        # candidate import/eval, no endpoint supplied by a user/model, and no body reads.
        positive = """import json,socket
targets=TARGETS
result={}
for name,(address,port) in targets.items():
    family=socket.AF_INET6 if ':' in address else socket.AF_INET
    with socket.socket(family,socket.SOCK_STREAM) as sock:
        sock.settimeout(5)
        try:
            sock.connect((address,port))
            result[name]='connected'
        except OSError as error:
            result[name]={'errno':error.errno,'type':type(error).__name__}
try:
    result['dns']='resolved' if socket.getaddrinfo('example.com',443) else 'empty'
except OSError as error: result['dns']={'errno':error.errno}
print(json.dumps(result))
""".replace("TARGETS", repr(targets))
        observed = json.loads(host("worker", "/usr/bin/python3 -I -S -B -", positive.encode()))
        (PRIVATE / "evidence/network-positive.json").write_text(
            json.dumps({"observed": observed, "time": datetime.now(UTC).isoformat()}))
        print(json.dumps({"host_positive_controls": observed}))
    finally:
        admin.close()


if __name__ == "__main__":
    main()
