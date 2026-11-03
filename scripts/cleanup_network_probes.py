"""Remove only the recorded temporary positive-control firewall rule/listener."""

import ipaddress

from vultr_phase1 import Admin

admin = Admin()
try:
    route = "/firewalls/" + admin.state["resources"]["firewall_control"] + "/rules"
    identifier = admin.state.get("network_rule_id")
    worker = str(ipaddress.IPv4Address(admin.state["hosts"]["worker"]["address"]))
    control = str(ipaddress.IPv4Address(admin.state["hosts"]["control"]["address"]))
    matches = [r for r in admin.request("GET", route)["firewall_rules"]
               if r["id"] == identifier]
    if matches:
        rule = matches[0]
        if (rule["notes"] != "ProofFlow temporary network positive control"
                or rule["subnet"] != worker or rule["port"] != "443"
                or rule["subnet_size"] != 32 or rule["protocol"] != "tcp"):
            raise RuntimeError("TEMPORARY_RULE_IDENTITY_CHANGED")
        admin.request("DELETE", route + "/" + str(identifier))
    if any(r["id"] == identifier for r in admin.request("GET", route)["firewall_rules"]):
        raise RuntimeError("TEMPORARY_RULE_STILL_PRESENT")
    for command in (
        "systemctl stop proofflow-network-probe.service",
        "ufw --force delete allow from " + worker + " to any port 443 proto tcp",
        "ufw --force delete allow from " + worker + " to " + control + " port 443 proto tcp",
    ):
        result = admin.host("control", command)
        if result.returncode:
            raise RuntimeError("NETWORK_CONTROL_CLEANUP_FAILED")
    admin.state["network_rule_cleaned"] = True
    admin.save()
    print("Temporary provider/host public ingress removed; positive-control listener stopped.")
finally:
    admin.close()
