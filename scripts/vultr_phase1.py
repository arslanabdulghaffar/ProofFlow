"""Trusted Windows deployment administration. Never import from application/worker code.

One fixed project, two fixed VM plans, no candidate-controlled arguments. Credentials
stay in the administrator profile; API responses are filtered before console output.
"""

import argparse
import base64
import ctypes
import hashlib
import ipaddress
import json
import os
import re
import subprocess
import sys
from ctypes import wintypes
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = Path(os.environ.get("USERPROFILE", "")) / ".proofflow" / "deployment"
STATE = PRIVATE / "phase1.json"
LABEL = "proofflow-phase1"
PLANS = {"control": "vhp-2c-4gb-amd", "worker": "vhp-4c-8gb-amd"}
PRICES = {"control": 24, "worker": 48}


def write_private(path: Path, value: dict):
    raw = json.dumps(value, sort_keys=True, indent=2).encode()
    temporary = path.with_suffix(".pending")
    with temporary.open("wb") as output:
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)


def load_token() -> str:
    if sys.platform != "win32":
        raise RuntimeError("WINDOWS_ADMINISTRATOR_REQUIRED")
    # Reuse the bounded, no-secret-output ACL/authentication preflight.
    check = subprocess.run(  # noqa: S603 - fixed reviewed local administrator script
        ["C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe", "-NoProfile", "-File",
         str(ROOT / "scripts/Read-VultrAccount.ps1")],
        capture_output=True, timeout=80,
        env={key: value for key, value in os.environ.items() if key.upper() != "PSMODULEPATH"},
    )
    if check.returncode:
        raise RuntimeError("MANAGEMENT_PREFLIGHT_FAILED")
    report = json.loads(check.stdout)
    if report["pending_charges"] is None:
        raise RuntimeError("ACCOUNT_CHARGES_UNAVAILABLE")
    encrypted = (PRIVATE.parent / "credentials/vultr-management.dpapi").read_text().strip()
    if len(encrypted) > 65536 or not re.fullmatch("[0-9a-fA-F]+", encrypted):
        raise RuntimeError("INVALID_ENCRYPTED_KEY")

    class Blob(ctypes.Structure):
        _fields_ = [("length", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    source = (ctypes.c_ubyte * (len(encrypted) // 2)).from_buffer_copy(bytes.fromhex(encrypted))
    incoming, outgoing = Blob(len(source), source), Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    crypt.CryptUnprotectData.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p,
                                        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                        wintypes.DWORD, ctypes.POINTER(Blob)]
    crypt.CryptUnprotectData.restype = wintypes.BOOL
    if not crypt.CryptUnprotectData(ctypes.byref(incoming), None, None, None, None, 1,
                                   ctypes.byref(outgoing)):
        raise RuntimeError("KEY_DECRYPTION_FAILED")
    try:
        if not 2 <= outgoing.length <= 1024:
            raise RuntimeError("INVALID_KEY_LENGTH")
        token = ctypes.string_at(outgoing.data, outgoing.length).decode("utf-16-le")
        if not re.fullmatch(r"[\x21-\x7e]{1,512}", token):
            raise RuntimeError("INVALID_KEY_FORMAT")
        return token
    finally:
        ctypes.memset(outgoing.data, 0, outgoing.length)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree.restype = ctypes.c_void_p
        kernel.LocalFree(outgoing.data)


class Admin:
    def __init__(self):
        # Serialize scheduled guard and interactive provisioning. Never lose an
        # uncertain-create intent to a concurrent read/modify/write of the plan.
        import msvcrt
        self._lock = (PRIVATE / "administrator.lock").open("a+b")
        if self._lock.tell() == 0:
            self._lock.write(b"0")
            self._lock.flush()
        self._lock.seek(0)
        try:
            msvcrt.locking(self._lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            self._lock.close()
            raise RuntimeError("ADMINISTRATOR_OPERATION_IN_PROGRESS") from None
        self.client = httpx.Client(base_url="https://api.vultr.com/v2", trust_env=False,
                                   follow_redirects=False, timeout=30,
                                   headers={"Authorization": "Bearer " + load_token(),
                                            "User-Agent": "ProofFlow-Phase1-Admin/1.0"})
        self.state = json.loads(STATE.read_text()) if STATE.exists() else {}

    def close(self):
        self.client.close()
        self._lock.close()

    def request(self, method, route, body=None):
        if not route.startswith("/") or route.startswith("//") or ".." in route:
            raise RuntimeError("INVALID_ADMIN_ROUTE")
        with self.client.stream(method, route, json=body) as response:
            if response.status_code not in (200, 201, 202, 204):
                raise RuntimeError("VULTR_HTTP_" + str(response.status_code))
            content = bytearray()
            for chunk in response.iter_bytes():
                content.extend(chunk)
                if len(content) > 4 * 1024 * 1024:
                    raise RuntimeError("VULTR_RESPONSE_LIMIT")
            return json.loads(content) if content else {}

    def save(self):
        write_private(STATE, self.state)

    def create_once(self, key, route, body, response_key):
        if self.state.get("credit_guard", {}).get("admission_closed"):
            raise RuntimeError("CREDIT_GUARD_ADMISSION_CLOSED")
        if key in self.state.get("resources", {}):
            return self.state["resources"][key]
        intents = self.state.setdefault("intents", {})
        if key in intents:
            raise RuntimeError("UNCERTAIN_CREATE_REQUIRES_READBACK_" + key)
        intents[key] = {"route": route, "body_sha256": hashlib.sha256(
            json.dumps(body, sort_keys=True).encode()).hexdigest(),
            "started_at": datetime.now(UTC).isoformat(), "state": "OUTCOME_UNKNOWN"}
        self.save()  # Durable before any external create. Never automatically retry POST.
        result = self.request("POST", route, body)[response_key]
        identifier = result["id"]
        if not re.fullmatch(r"[a-zA-Z0-9-]{1,64}", identifier):
            raise RuntimeError("INVALID_RESOURCE_IDENTIFIER")
        self.state.setdefault("resources", {})[key] = identifier
        intents[key]["state"] = "CREATED_REQUIRES_READBACK"
        self.save()
        return identifier

    def prepare(self):
        if self.state:
            raise RuntimeError("EXISTING_PLAN_PRESERVED")
        account = self.request("GET", "/account")["account"]
        if Decimal(str(account["balance"])) > -150 or Decimal(str(account["pending_charges"])) != 0:
            raise RuntimeError("CREDIT_MARGIN_REVIEW_REQUIRED")
        existing = self.request("GET", "/instances?per_page=100")
        if existing["instances"] or existing.get("meta", {}).get("total", 0):
            raise RuntimeError("EXISTING_INSTANCES_REVIEW_REQUIRED")
        plans = self.request("GET", "/plans?per_page=500")["plans"]
        selected = {}
        for role, identifier in PLANS.items():
            plan = next(p for p in plans if p["id"] == identifier)
            if (plan["monthly_cost"] != PRICES[role] or "icn" not in plan["locations"]
                    or plan.get("location_cost", {}).get("icn")):
                raise RuntimeError("PLAN_QUOTE_CHANGED")
            selected[role] = plan
        systems = self.request("GET", "/os?per_page=500")["os"]
        systems = [item for item in systems if item.get("name") == "Ubuntu 24.04 LTS x64"]
        if len(systems) != 1:
            raise RuntimeError("OS_SELECTION_REVIEW_REQUIRED")
        # No credentials sent to the address-discovery service.
        with httpx.Client(trust_env=False, follow_redirects=False, timeout=10) as public:
            reply = public.get("https://api.ipify.org")
            reply.raise_for_status()
            address = ipaddress.IPv4Address(reply.text.strip())
        now = datetime.now(UTC)
        self.state = {"project": LABEL, "created_at": now.isoformat(),
                      "review_due_at": (now + timedelta(hours=72)).isoformat(),
                      "credit_expiry_date": "2026-12-04", "resources": {}, "intents": {},
                      "os_id": systems[0]["id"], "admin_ipv4": str(address),
                      "region": "icn", "plans": selected,
                      "reservations_usd": {"compute": 72, "inference": 25,
                                           "later_storage": 18, "incidental": 10,
                                           "contingency": 20},
                      "project_limit_usd": 150, "probe_limit_usd": 2,
                      "remaining_credit_at_prepare": 200,
                      "authorization": "Owner authorized credit use while support reply pending"}
        self.save()
        return {"prepared": True, "monthly_compute_quote": 72, "reserved_total": 145,
                "initial_72h_compute_estimate": 7.92, "probe_limit": 2,
                "card_or_deposit": False, "cloud_resources_created": 0}

    def network(self):
        if not self.state or self.state["project"] != LABEL:
            raise RuntimeError("REVIEWED_PLAN_REQUIRED")
        address = str(ipaddress.IPv4Address(self.state["admin_ipv4"]))
        key = (PRIVATE / "operator_ed25519.pub").read_text().strip()
        if not key.startswith("ssh-ed25519 ") or len(key) > 1024:
            raise RuntimeError("INVALID_OPERATOR_PUBLIC_KEY")
        self.create_once("ssh", "/ssh-keys", {"name": LABEL, "ssh_key": key}, "ssh_key")
        self.create_once("vpc", "/vpcs", {"region": "icn", "description": LABEL,
                         "v4_subnet": "10.77.0.0", "v4_subnet_mask": 24}, "vpc")
        for role in PLANS:
            firewall = self.create_once("firewall_" + role, "/firewalls",
                                        {"description": LABEL + "-" + role}, "firewall_group")
            rules = self.request("GET", "/firewalls/" + firewall + "/rules")["firewall_rules"]
            if not rules:
                self.request("POST", "/firewalls/" + firewall + "/rules", {
                    "ip_type": "v4", "protocol": "tcp", "subnet": address,
                    "subnet_size": 32, "port": "22", "notes": "ProofFlow administrator only"})
            rules = self.request("GET", "/firewalls/" + firewall + "/rules")["firewall_rules"]
            if len(rules) != 1 or any(r.get("port") != "22" or r.get("subnet") != address
                                      or r.get("subnet_size") != 32 for r in rules):
                raise RuntimeError("FIREWALL_RULE_READBACK_FAILED")
        return {"project_network": "created_and_read_back", "ssh": "administrator_ip_only",
                "compute_instances_created": 0}

    def instances(self):
        return [{name: item.get(name) for name in ("id", "label", "status", "server_status",
                                                   "power_status", "main_ip", "internal_ip")}
                for item in self.request("GET", "/instances?per_page=100")["instances"]
                if item.get("label") in {LABEL + "-control", LABEL + "-worker"}]

    def refresh_hosts(self):
        hosts = {}
        for role in PLANS:
            identifier = self.state["resources"]["vm_" + role]
            item = self.request("GET", "/instances/" + identifier)["instance"]
            if item["label"] != LABEL + "-" + role or item["plan"] != PLANS[role]:
                raise RuntimeError("DEPLOYMENT_IDENTITY_CHANGED")
            address = str(ipaddress.IPv4Address(item["main_ip"]))
            if ipaddress.IPv4Address(address).is_unspecified:
                raise RuntimeError("HOST_ADDRESS_NOT_READY")
            ssh_port = self.state.get("hosts", {}).get(role, {}).get("ssh_port", 22)
            hosts[role] = {"address": address, "status": item["status"], "ssh_port": ssh_port,
                           "server_status": item["server_status"], "power": item["power_status"]}
        self.state["hosts"] = hosts
        self.save()
        known = ""
        for role, host in hosts.items():
            public = (PRIVATE / (role + "_host_ed25519.pub")).read_text().split()
            known += host["address"] + " " + public[0] + " " + public[1] + "\n"
            known += "[" + host["address"] + "]:443 " + public[0] + " " + public[1] + "\n"
        (PRIVATE / "known_hosts").write_text(known, encoding="ascii")
        return {role: {k: v for k, v in item.items() if k != "address"}
                for role, item in hosts.items()}

    def host(self, role: str, command: str, *, stdin: bytes | None = None, timeout=90):
        if role not in PLANS:
            raise RuntimeError("INVALID_HOST_ROLE")
        address = str(ipaddress.IPv4Address(self.state["hosts"][role]["address"]))
        port = self.state["hosts"][role].get("ssh_port", 22)
        if port not in (22, 443):
            raise RuntimeError("UNAPPROVED_SSH_PORT")
        result = subprocess.run(  # noqa: S603 - trusted administrator command, never candidate bytes
            ["C:/Windows/System32/OpenSSH/ssh.exe", "-F", "NUL", "-o", "BatchMode=yes",
             "-o", "StrictHostKeyChecking=yes", "-o", "HostKeyAlgorithms=ssh-ed25519",
             "-o", "IdentitiesOnly=yes", "-o", "ConnectTimeout=10",
             "-o", "UserKnownHostsFile=" + str(PRIVATE / "known_hosts"),
             "-p", str(port),
             "-i", str(PRIVATE / "operator_ed25519"), "root@" + address, command],
            input=stdin, capture_output=True, timeout=timeout,
        )
        return result

    def compute(self):
        if sum(self.state.get("reservations_usd", {}).values()) != 145:
            raise RuntimeError("DURABLE_PROJECT_RESERVATION_REQUIRED")
        if datetime.now(UTC) >= datetime.fromisoformat(self.state["review_due_at"]):
            raise RuntimeError("DEPLOYMENT_QUOTE_EXPIRED")
        resources = self.state["resources"]
        account = self.request("GET", "/account")["account"]
        if -Decimal(str(account["balance"])) - Decimal(str(account["pending_charges"])) < 150:
            raise RuntimeError("INSUFFICIENT_CREDIT_MARGIN")
        current = {p["id"]: p for p in self.request("GET", "/plans?per_page=500")["plans"]}
        for role, plan_id in PLANS.items():
            if current[plan_id]["monthly_cost"] != PRICES[role]:
                raise RuntimeError("PLAN_QUOTE_CHANGED")
            host_key = (PRIVATE / (role + "_host_ed25519")).read_text()
            host_public = (PRIVATE / (role + "_host_ed25519.pub")).read_text().strip()
            cloud = {
                "hostname": LABEL + "-" + role, "manage_etc_hosts": True,
                "ssh_deletekeys": True, "ssh_genkeytypes": [],
                "ssh_keys": {"ed25519_private": host_key, "ed25519_public": host_public},
                "ssh_pwauth": False, "disable_root": False,
                "ssh_authorized_keys": [(PRIVATE / "operator_ed25519.pub").read_text().strip()],
                "package_update": True, "package_upgrade": True,
                "packages": ["python3", "python3-venv", "squashfs-tools", "openssl",
                             "curl", "ca-certificates", "nftables"],
                "write_files": [{"path": "/etc/ssh/sshd_config.d/00-proofflow.conf",
                                 "permissions": "0600", "owner": "root:root",
                                 "content": "Port 22\nPort 443\nListenAddress 0.0.0.0\n"
                                            "PasswordAuthentication no\n"
                                            "KbdInteractiveAuthentication no\n"
                                            "PermitRootLogin prohibit-password\n"
                                            "AllowUsers root\n"}],
                "runcmd": [["systemctl", "disable", "--now", "ssh.socket"],
                           ["systemctl", "enable", "ssh.service"],
                           ["systemctl", "restart", "ssh.service"],
                           ["sh", "-c", "install -d -m 0700 /var/lib/proofflow-setup && "
                            "printf ready > /var/lib/proofflow-setup/cloud-init-ready"]],
            }
            body = {"region": "icn", "plan": plan_id, "os_id": self.state["os_id"],
                    "label": LABEL + "-" + role, "hostname": LABEL + "-" + role,
                    "tags": [LABEL], "sshkey_id": [resources["ssh"]],
                    "attach_vpc": [resources["vpc"]],
                    "firewall_group_id": resources["firewall_" + role],
                    "backups": "disabled", "ddos_protection": False,
                    "enable_ipv6": True, "activation_email": False,
                    "user_data": base64.b64encode(
                        ("#cloud-config\n" + json.dumps(cloud)).encode()).decode()}
            instance = self.create_once("vm_" + role, "/instances", body, "instance")
            observed = self.request("GET", "/instances/" + instance)["instance"]
            if (observed["plan"] != plan_id or observed["region"] != "icn"
                    or observed["label"] != LABEL + "-" + role
                    or observed["firewall_group_id"] != resources["firewall_" + role]):
                raise RuntimeError("INSTANCE_READBACK_MISMATCH")
        return {"compute_created": 2, "monthly_quote_usd": 72,
                "backups": "disabled", "ddos_addon": False,
                "ssh": "pinned_host_keys_and_operator_ip_only", "acceptance": "NOT_RUN"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "network", "compute", "status", "hosts"))
    args = parser.parse_args()
    if not PRIVATE.is_dir():
        raise RuntimeError("PROTECTED_DEPLOYMENT_DIRECTORY_REQUIRED")
    admin = Admin()
    try:
        if args.action == "prepare":
            result = admin.prepare()
        elif args.action == "network":
            result = admin.network()
        elif args.action == "compute":
            result = admin.compute()
        elif args.action == "hosts":
            result = admin.refresh_hosts()
        else:
            result = admin.instances()
        print(json.dumps(result))
    finally:
        admin.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        code = str(error)
        print(code if re.fullmatch("[A-Z0-9_]{1,100}", code) else "ADMIN_OPERATION_FAILED",
              file=sys.stderr)
        raise SystemExit(1) from None
