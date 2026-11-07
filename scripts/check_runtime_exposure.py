"""Read-only inventory of fixed runtime daemons and protected sockets on owned VMs.

No exploits, candidate programs, service changes, remote URLs or arbitrary argv.
"""

import hashlib
import json
import shlex
from datetime import UTC, datetime

from product_live_session import LiveSession, require
from vultr_phase1 import PRIVATE, ROOT

PROBE = r'''
import hashlib,json,os,stat,subprocess
from pathlib import Path
def run(args):
 try:p=subprocess.run(args,capture_output=True,timeout=15)
 except FileNotFoundError:return {'exit':None,'absent':True}
 return {'exit':p.returncode,'stdout':p.stdout.decode(errors='replace').strip()}
result={'kernel':os.uname().release,'packages':run(['/usr/bin/dpkg-query','-W',
 '-f=${Package} ${Version}\n','docker-ce','containerd.io','linux-image-generic','openssl'])}
result['containerd_plugins']=run(['/usr/bin/ctr','plugins','ls'])
result['containerd_version']=run(['/usr/bin/containerd','--version'])
result['docker_version']=run(['/usr/bin/docker','--version'])
result['services']={n:run(['/usr/bin/systemctl','is-active',n]) for n in
 ('docker.service','containerd.service','proofflow-worker.service')}
result['sockets']={}
for name in ('/run/docker.sock','/run/containerd/containerd.sock'):
 try:
  s=Path(name).lstat()
  result['sockets'][name]={'socket':stat.S_ISSOCK(s.st_mode),'uid':s.st_uid,
                          'gid':s.st_gid,'mode':oct(stat.S_IMODE(s.st_mode))}
 except FileNotFoundError: result['sockets'][name]={'absent':True}
result['runtime_processes']={}
names={'runsc','gvisor_sentry','checkpointgofer','runsc-metric-server',
       'containerd-shim-runsc-v1','containerd','dockerd'}
for p in Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:name=Path(os.readlink(p/'exe')).name
 except (OSError,PermissionError):continue
 if name in names:result['runtime_processes'][name]=result['runtime_processes'].get(name,0)+1
result['cdi_specs']={n:len(list(Path(n).iterdir())) if Path(n).exists() else 0
                     for n in ('/etc/cdi','/var/run/cdi')}
result['tcp_listeners']=run(['/usr/bin/ss','-H','-lnt'])
result['runtime_members']={}
manifest=Path('/etc/proofflow-worker/runtime.json')
if manifest.exists():
 for name,pin in json.loads(manifest.read_bytes())['members'].items():
  p=Path('/usr/local/bin')/name;s=p.lstat()
  with p.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
  result['runtime_members'][name]={'sha256':digest,'matches':digest==pin['sha256'],
     'uid':s.st_uid,'mode':oct(stat.S_IMODE(s.st_mode)),'links':s.st_nlink}
print(json.dumps(result,sort_keys=True))
'''


def main():
    record = {"observed_at": datetime.now(UTC).isoformat(), "hosts": {},
              "probe_sha256": hashlib.sha256(PROBE.encode()).hexdigest(),
              "new_resources": 0, "provider_calls": 0, "vulnerability_waiver": False}
    with LiveSession() as live:
        record["credit"] = live.credit
        for role in ("control", "worker"):
            result = live.admin.host(role, "/usr/bin/python3 -I -S -B -c " + shlex.quote(PROBE),
                                     timeout=60)
            if result.returncode:
                failure = PRIVATE / "evidence/phase5-runtime-exposure-failure.txt"
                failure.write_bytes(result.stderr)
            require(result.returncode == 0, "RUNTIME_INVENTORY_FAILED")
            record["hosts"][role] = json.loads(result.stdout)
        expected = json.loads((ROOT / "infra/gvisor/runsc-release.json").read_bytes())["members"]
        actual = record["hosts"]["worker"]["runtime_members"]
        require(actual.keys() == expected.keys() and all(
            row["matches"] and row["sha256"] == expected[name]["sha256"]
            and row["uid"] == 0 and row["mode"] == "0o755" and row["links"] == 1
            for name, row in actual.items()), "RUNTIME_MEMBER_DRIFT")
    path = PRIVATE / "evidence/phase5-runtime-exposure.json"
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    # Raw listener addresses remain private. Publish only bounded runtime facts.
    print(json.dumps({"runtime_members_verified": len(actual), "hosts": {
        role: {k: data[k] for k in ("kernel", "packages", "containerd_version", "docker_version",
                                   "runtime_processes", "cdi_specs", "containerd_plugins")}
        for role, data in record["hosts"].items()}}))


if __name__ == "__main__":
    main()
