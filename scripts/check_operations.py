"""One-shot owner operations check. Read-only cloud/SQL/HTTPS; no admission or scheduling.

Success means these observations passed, never release approval or end-to-end AI readiness.
No credentials, workspace identifiers, SQL rows or native errors are printed.
"""

import json
import shlex
import socket
import ssl
import subprocess
from datetime import UTC, datetime
from decimal import Decimal

import httpx
from asset_backup_vault import recover
from export_portable_backup import checked_backup, read_latest, require_current_receipt
from vultr_credit_guard import stop_reason
from vultr_phase1 import LABEL, PRIVATE, Admin

ORIGIN = "https://158.247.227.66:8443"
ADDRESS = "158.247.227.66"
SERVICES = {
    "control": ("proofflow-budget.service", "proofflow-product-api.service",
                "proofflow-product-dispatcher.service", "proofflow-public-api.service",
                "proofflow-product-retention.timer", "proofflow-public-renew.timer",
                "proofflow-guest-demo.timer"),
    "worker": ("proofflow-worker.service",),
}
STORAGE = {"control": "/var/lib/docker", "worker": "/var/lib/proofflow-worker"}
HOST_PROBE = """
import json,os,subprocess,sys
value=json.loads(sys.stdin.buffer.read(8192))
services={}
for name in value['services']:
 r=subprocess.run(['/usr/bin/systemctl','is-active',name],capture_output=True,timeout=5)
 services[name]=r.returncode==0 and r.stdout.strip()==b'active'
s=os.statvfs(value['storage'])
result={'services':services,'storage_path':value['storage'],
 'free_bytes':s.f_bavail*s.f_frsize,
 'total_bytes':s.f_blocks*s.f_frsize,'free_inodes':s.f_favail,'total_inodes':s.f_files}
if value['storage']=='/var/lib/docker':
 r=subprocess.run(['/usr/bin/systemctl','show','proofflow-public-renew.service',
   '-p','Result','-p','ExecMainStatus'],capture_output=True,check=True,timeout=5)
 fields=dict(line.split('=',1) for line in r.stdout.decode().splitlines())
 result['renewal_success']=fields=={'Result':'success','ExecMainStatus':'0'}
 result['tls_rotation_pending']=any(os.path.lexists('/etc/proofflow-public-api/tls/'+n)
   for n in ('.rotation.json','health.pem.pending','health.key.pending'))
print(json.dumps(result))
"""
TASKS = r"""
$ErrorActionPreference='Stop'
$rows=@()
foreach($name in @('ProofFlow-CreditGuard','ProofFlow-ProductBackup')){
 $task=Get-ScheduledTask -TaskName $name
 $info=$task | Get-ScheduledTaskInfo
 $rows+=@{name=$name;enabled=($task.State -ne 'Disabled');
 last_run=$info.LastRunTime.ToUniversalTime().ToString('o');result=$info.LastTaskResult}
}
ConvertTo-Json -InputObject $rows -Compress
"""


def public_probe():
    context = ssl.create_default_context()
    with socket.create_connection((ADDRESS, 8443), timeout=10) as raw:
        with context.wrap_socket(raw, server_hostname=ADDRESS) as connection:
            expiry = ssl.cert_time_to_seconds(connection.getpeercert()["notAfter"])
    observed = {}
    with httpx.Client(trust_env=False, follow_redirects=False, timeout=10) as client:
        for key, path in (("live", "/health/live"), ("ready", "/health/ready")):
            with client.stream("GET", ORIGIN+path) as response:
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > 4096:
                        raise RuntimeError("HEALTH_RESPONSE_LIMIT")
                parsed = json.loads(body)
                expected = ({"status": "alive"} if key == "live" else {
                    "status": "not_ready", "reason": "product_acceptance_incomplete"})
                safe = expected if parsed == expected else {"status": "unexpected"}
                observed[key] = {"status": response.status_code, "body": safe}
    return {"certificate_expires_at": datetime.fromtimestamp(expiry, UTC).isoformat(), **observed}


def backup_probe():
    latest = read_latest(PRIVATE)
    envelope, key = recover(latest["backup_id"])
    payload = checked_backup(latest, envelope, key, now=datetime.now(UTC))
    require_current_receipt(latest, PRIVATE)
    return {"snapshot_at": payload["snapshot"]["observed_at"],
            "expires_at": payload["expires_at"], "authenticated": True}


def tasks_probe():
    response = subprocess.run(  # noqa: S603 - fixed read-only scheduler query
        ["C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe", "-NoProfile",
         "-NonInteractive", "-Command", TASKS], capture_output=True, check=True, timeout=15,
        creationflags=subprocess.CREATE_NO_WINDOW)
    return json.loads(response.stdout)


def remote_probe():
    admin = Admin()
    try:
        if admin.state["project"] != LABEL:
            raise RuntimeError("OPERATIONS_PROJECT_CHANGED")
        account = admin.request("GET", "/account")["account"]
        reason = stop_reason(account, admin.state, datetime.now(UTC))
        remaining = -Decimal(str(account["balance"]))-Decimal(str(account["pending_charges"]))
        result = {"remaining_credit_usd": str(remaining), "credit_stop_reason": reason,
                  "funded_until": admin.state["review_due_at"], "hosts": {}}
        sql = ("SELECT row_to_json(a) FROM (SELECT project_limit,inference_limit,probe_limit,"
               "expires_at FROM pf_budget.accounts) a;")
        response = admin.host("control", "docker exec -i --user=70:70 proofflow-budget "
                              "psql -X -qAt "
                              "-h /run/proofflow-budget -U postgres -d proofflow_budget "
                              "--set ON_ERROR_STOP=1", stdin=sql.encode())
        if response.returncode:
            raise RuntimeError("OPERATIONS_BUDGET_UNAVAILABLE")
        result["budget"] = json.loads(response.stdout)
        for role, services in SERVICES.items():
            response = admin.host(role, "/usr/bin/python3 -I -c " + shlex.quote(HOST_PROBE),
                                  stdin=json.dumps({"services": services,
                                                    "storage": STORAGE[role]}).encode(), timeout=50)
            if response.returncode:
                raise RuntimeError("OPERATIONS_HOST_UNAVAILABLE")
            result["hosts"][role] = json.loads(response.stdout)
        return result
    finally:
        admin.close()


def assess(observations, now):
    blockers = []
    notes = ["READ_ONLY_OBSERVATION_NOT_RELEASE_APPROVAL",
             "NO_WORKER_JOB_OR_PROVIDER_CALL", "OFFLINE_KEY_CUSTODY_DEFERRED",
             "NO_BACKGROUND_MONITOR_INSTALLED"]

    def age(value):
        stamp = datetime.fromisoformat(value)
        if stamp.tzinfo is None:
            raise ValueError("timezone required")
        return (now-stamp).total_seconds()

    for key in ("public", "backup", "tasks", "remote"):
        if key not in observations:
            blockers.append(key.upper()+"_UNAVAILABLE")
    try:
        if "public" in observations:
            public = observations["public"]
            if public["live"] != {"status": 200, "body": {"status": "alive"}}:
                blockers.append("PUBLIC_LIVENESS_FAILED")
            if age(public["certificate_expires_at"]) >= -86400:
                blockers.append("TLS_EXPIRY_WITHIN_24H")
            if public["ready"] != {"status": 503, "body": {
                    "status": "not_ready", "reason": "product_acceptance_incomplete"}}:
                blockers.append("READINESS_CONTRACT_CHANGED")
            else:
                notes.append("PUBLIC_READINESS_REMAINS_503_NOT_VERIFIED")
        if "backup" in observations:
            backup = observations["backup"]
            if (backup["authenticated"] is not True or not 0 <= age(backup["snapshot_at"]) < 86400
                    or age(backup["expires_at"]) >= -7200):
                blockers.append("BACKUP_AUTHENTICITY_AGE_OR_EXPIRY")
        if "tasks" in observations:
            tasks = observations["tasks"]
            expected = {"ProofFlow-CreditGuard": 1800, "ProofFlow-ProductBackup": 7200}
            if len(tasks) != 2 or {t["name"] for t in tasks} != set(expected):
                blockers.append("TASK_INVENTORY_CHANGED")
            else:
                for task in tasks:
                    if (task["enabled"] is not True or task["result"] != 0
                            or not 0 <= age(task["last_run"]) < expected[task["name"]]):
                        blockers.append(task["name"].upper()+"_CHECK_REQUIRED")
        if "remote" in observations:
            remote = observations["remote"]
            balance = Decimal(remote["remaining_credit_usd"])
            if not balance.is_finite() or balance < 150 or remote["credit_stop_reason"] is not None:
                blockers.append("CREDIT_REVIEW_REQUIRED")
            if age(remote["funded_until"]) >= -21600:
                blockers.append("FUNDED_REVIEW_WITHIN_6H")
            budget = remote["budget"]
            if (budget["project_limit"] != 150000000 or budget["inference_limit"] != 25000000
                    or budget["probe_limit"] != 2000000
                    or datetime.fromisoformat(budget["expires_at"])
                        != datetime.fromisoformat(remote["funded_until"])):
                blockers.append("BUDGET_CAP_OR_DEADLINE_CHANGED")
            if set(remote["hosts"]) != set(SERVICES):
                blockers.append("HOST_INVENTORY_CHANGED")
            for role in SERVICES:
                host = remote["hosts"][role]
                if role == "control" and (host["renewal_success"] is not True
                                          or host["tls_rotation_pending"] is not False):
                    blockers.append("TLS_RENEWAL_OR_ROTATION_REQUIRES_RECONCILIATION")
                if (set(host["services"]) != set(SERVICES[role])
                        or not all(value is True for value in host["services"].values())):
                    blockers.append(role.upper()+"_SERVICE_UNHEALTHY")
                if (host["storage_path"] != STORAGE[role]
                        or host["free_bytes"] < 1024**3 or host["total_bytes"] <= 0
                        or host["free_bytes"]/host["total_bytes"] < 0.1
                        or host["total_inodes"] <= 0
                        or host["free_inodes"]/host["total_inodes"] < 0.1):
                    blockers.append(role.upper()+"_STORAGE_PRESSURE")
    except (KeyError, TypeError, ValueError, ArithmeticError):
        blockers.append("OBSERVATION_INVALID")
    return {"observed_at": now.isoformat(),
            "status": "ACTION_REQUIRED" if blockers else "SCOPED_OK",
            "blockers": blockers, "notes": notes, "phase6_complete": False}


def main():
    observations = {}
    for name, probe in (("public", public_probe), ("backup", backup_probe),
                        ("tasks", tasks_probe), ("remote", remote_probe)):
        try:
            observations[name] = probe()
        except Exception:  # noqa: S110 - fixed unavailable code below; native errors may leak secrets
            pass  # Emit only the fixed UNAVAILABLE code, never native error/secret text.
    report = assess(observations, datetime.now(UTC))
    # Probe output contains only explicitly selected non-secret aggregate fields.
    print(json.dumps({**report, "observations": observations}))
    return 1 if report["blockers"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
