"""Install reviewed crash-recoverable TLS hook on the existing control host only.

No certificate issuance, new service/resource, funding change or admission. Preserve
old revision/unit. Require closed idle admission and exact prior unit before mutation.
"""

import hashlib
import json
import shlex
from datetime import UTC, datetime

from check_operations import public_probe
from vultr_credit_guard import stop_reason
from vultr_phase1 import LABEL, ROOT, Admin

OLD_UNIT_SHA256 = "34faea65f2cf88c8e449515d780a6179417802eef41027127b5fcb7809c67301"
OLD_HOOK = ("/opt/proofflow-public-setup/"
            "f642c5cea2e4c3e1f9f2733fc59dcf9fefdc73a73a5d9d0877b9616d1a3f56f2/"
            "install_public_certificate.py")
REMOTE = r"""
import hashlib,json,os,stat,subprocess,sys
from pathlib import Path
v=json.loads(sys.stdin.buffer.read(131073))
raw=v['source'].encode(); digest=hashlib.sha256(raw).hexdigest()
assert digest==v['digest']
parent=Path('/opt/proofflow-public-setup')
info=parent.lstat()
assert stat.S_ISDIR(info.st_mode) and info.st_uid==0 and not info.st_mode&0o022
target=parent/digest
target.mkdir(mode=0o700,exist_ok=True)
info=target.lstat()
assert stat.S_ISDIR(info.st_mode) and info.st_uid==0 and stat.S_IMODE(info.st_mode)==0o700
hook=target/'install_public_certificate.py'
unit=Path('/etc/systemd/system/proofflow-public-renew.service')
info=unit.lstat()
assert stat.S_ISREG(info.st_mode) and info.st_uid==0 and info.st_nlink==1 and not info.st_mode&0o022
before=unit.read_bytes()
expected=v['unit'].encode()
assert before==expected or hashlib.sha256(before).hexdigest()==v['old_unit_sha256']
def save(path,data,mode):
 if path.exists() or path.is_symlink():
  st=path.lstat()
  assert stat.S_ISREG(st.st_mode) and st.st_uid==0 and st.st_nlink==1
  assert stat.S_IMODE(st.st_mode)==mode and path.read_bytes()==data
 else:
  fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
  with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
save(hook,raw,0o400)
save(target/'proofflow-public-renew.service',expected,0o644)
r=subprocess.run(['/usr/bin/systemd-analyze','verify',str(target/'proofflow-public-renew.service')],capture_output=True,timeout=20)
assert r.returncode==0
# Validate live lineage and exercise same-certificate no-op before wiring the timer.
r=subprocess.run(['/opt/proofflow-acme/bin/python','-I',str(hook)],capture_output=True,timeout=100)
assert r.returncode==0
certificate=json.loads(r.stdout)
assert certificate['replaced'] is False
if before!=expected:
 save(target/'previous-renew.service',before,0o400)
 pending=unit.with_suffix('.service.pending')
 save(pending,expected,0o644)
 os.replace(pending,unit)
 fd=os.open(unit.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
 try:os.fsync(fd)
 finally:os.close(fd)
subprocess.run(['/usr/bin/systemctl','daemon-reload'],check=True,capture_output=True,timeout=20)
assert unit.read_bytes()==expected
for service in ('proofflow-public-api.service','proofflow-public-renew.timer'):
 subprocess.run(['/usr/bin/systemctl','is-active',service],check=True,capture_output=True,timeout=10)
print(json.dumps({'hook_sha256':digest,'unit_sha256':hashlib.sha256(expected).hexdigest(),
 'certificate':certificate,'old_revision_preserved':True,'renewal_timer_active':True,
 'unit_has_post_check':b'ExecStartPost=' in expected}))
"""


def replacement_unit(before, digest):
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise RuntimeError("TLS_HOOK_DIGEST_INVALID")
    hook = "/opt/proofflow-public-setup/" + digest + "/install_public_certificate.py"
    if hashlib.sha256(before).hexdigest() != OLD_UNIT_SHA256:
        raise RuntimeError("TLS_RENEWAL_UNIT_CHANGED")
    text = before.decode()
    if text.count(OLD_HOOK) != 1 or "ExecStartPost=" in text:
        raise RuntimeError("TLS_RENEWAL_HOOK_CHANGED")
    return text.replace(OLD_HOOK, hook).replace(
        "TimeoutStartSec=240", "ExecStartPost=/opt/proofflow-acme/bin/python -I "
        + hook + "\nTimeoutStartSec=240")


def main():
    source = (ROOT / "scripts/install_public_certificate.py").read_text(encoding="utf-8")
    digest = hashlib.sha256(source.encode()).hexdigest()
    admin = Admin()
    try:
        if admin.state["project"] != LABEL:
            raise RuntimeError("TLS_UPDATE_PROJECT_CHANGED")
        account = admin.request("GET", "/account")["account"]
        if stop_reason(account, admin.state, datetime.now(UTC)) is not None:
            raise RuntimeError("TLS_UPDATE_FUNDING_STOPPED")
        identity = admin.host("control", "cat /etc/machine-id")
        if (identity.returncode or identity.stdout.decode().strip()
                != admin.state["control_machine_id"]):
            raise RuntimeError("TLS_UPDATE_HOST_CHANGED")
        sql = ("SELECT NOT enabled AND NOT EXISTS(SELECT 1 FROM pf_product.jobs WHERE state "
               "NOT IN ('NEEDS_REVIEW','FAILED_INFRA','CANCELLED')) AND NOT EXISTS(SELECT 1 "
               "FROM pf_product.repairs WHERE state IN ('QUEUED','RUNNING','RECONCILING')) "
               "FROM pf_product.execution_policy;")
        result = admin.host("control", "docker exec -i --user=70:70 proofflow-budget psql -X -qAt "
                            "-h /run/proofflow-budget -U postgres -d proofflow_product "
                            "--set ON_ERROR_STOP=1", stdin=sql.encode())
        if result.returncode or result.stdout.strip() != b't':
            raise RuntimeError("TLS_UPDATE_REQUIRES_CLOSED_IDLE")
        result = admin.host("control", "cat /etc/systemd/system/proofflow-public-renew.service")
        if result.returncode:
            raise RuntimeError("TLS_UPDATE_UNIT_UNAVAILABLE")
        unit = replacement_unit(result.stdout, digest)
        public_before = public_probe()
        result = admin.host("control", "/usr/bin/python3 -I -c " + shlex.quote(REMOTE),
                            stdin=json.dumps({'source':source,'digest':digest,'unit':unit,
                                              'old_unit_sha256':OLD_UNIT_SHA256}).encode(),
                            timeout=150)
        if result.returncode:
            raise RuntimeError("TLS_UPDATE_UNCERTAIN_RECONCILE_NO_BLIND_RETRY")
        receipt = json.loads(result.stdout)
        public_after = public_probe()
        if public_after != public_before or public_after['live']['status'] != 200:
            raise RuntimeError("TLS_UPDATE_PUBLIC_READBACK_CHANGED")
        print(json.dumps({**receipt, 'observed_at':datetime.now(UTC).isoformat(),
                          'public_before_after_unchanged':True,'public':public_after,
                          'certificate_issuance':False,'new_resources':0,'provider_calls':0,
                          'funded_until':admin.state['review_due_at']}))
    finally:
        admin.close()


if __name__ == '__main__':
    main()
