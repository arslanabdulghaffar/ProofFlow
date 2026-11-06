"""Trusted deployed controller probes. Payload text executes ONLY on the worker.

Run on the configured control VM. No local fallback, exec, eval, pipeline import,
or subprocess execution of payloads. These are infrastructure fixtures, not
business-verifier results or measured repair-agent performance.
"""

import argparse
import base64
import ipaddress
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, "/opt/proofflow-control/lib")
from orchestrator.worker_client import WorkerClient  # noqa: E402
from worker.protocol import ExecutionRequest, SupervisorError, authority_id  # noqa: E402
from worker.wire import tls_context  # noqa: E402

ROOT = Path("/opt/proofflow-control")
EVIDENCE = Path("/var/lib/proofflow-control/probes")
HEADER = '''import json, os
def emit(value):
    with open('/output/ledger.jsonl', 'w') as f:
        f.write(json.dumps(value, sort_keys=True)+'\\n')
    open('/output/unresolved.jsonl', 'w').close()
'''
PROBES = {
    "network": "",  # Filled only from the administrator's fixed endpoint configuration.
    "mounts": HEADER + '''from pathlib import Path
emit({'mountinfo':Path('/proc/self/mountinfo').read_text(),
      'stats':{p:{'device':os.stat(p).st_dev,'inode':os.stat(p).st_ino,
                  'blocks':os.statvfs(p).f_blocks,'blocksize':os.statvfs(p).f_frsize,
                  'files':os.statvfs(p).f_files} for p in ('/','/scratch','/output','/dev/shm')}})
''',
    "benign": HEADER + '''import pandas as pd
import numpy as np
import resource
data = pd.DataFrame({'merchant':['A','A','B'], 'amount':[-100,250,350]})
status = dict(line.split(':',1) for line in open('/proc/self/status') if ':' in line)
emit({'uid':os.getuid(), 'gid':os.getgid(), 'pandas':pd.__version__, 'numpy':np.__version__,
      'sums':{k:int(v) for k,v in data.groupby('merchant').amount.sum().items()},
      'nproc':resource.getrlimit(resource.RLIMIT_NPROC),
      'nofile':resource.getrlimit(resource.RLIMIT_NOFILE),
      'cap_eff':status.get('CapEff','').strip(),
      'no_new_privs':status.get('NoNewPrivs','').strip()})
''',
    "filesystem": HEADER + '''import errno
results = {}
for name,path in [('host_marker','/var/lib/proofflow-setup/host-marker'),
                  ('host_credential','/etc/proofflow/credentials/vultr-api-key')]:
    try:
        with open(path,'rb') as f: f.read(1)
        results[name] = 'READABLE'
    except OSError as e: results[name] = e.errno
for name,path in [('root_write','/var/tmp/proofflow-probe'),('input_write','/input/pipeline.py')]:
    try:
        with open(path,'ab') as f: f.write(b'x')
        results[name] = 'WRITABLE'
    except OSError as e: results[name] = e.errno
results['environment_keys'] = sorted(os.environ)
results['fds'] = sorted(os.listdir('/proc/self/fd'))
emit(results)
''',
    "forks": HEADER + '''import resource, time, signal
children=[]
error=None
emit({'children_started':0,'in_progress':True})
for i in range(100):
    try: pid=os.fork()
    except OSError as e:
        error=e.errno
        break
    if pid==0:
        time.sleep(10)
        os._exit(0)
    children.append(pid)
    emit({'children_started':len(children),'in_progress':True})
    time.sleep(0.02)  # Let runsc recycle idle host helpers; burst exhaustion is separate.
for pid in children: os.kill(pid, signal.SIGKILL)
for pid in children: os.waitpid(pid,0)
raised=False
try: resource.setrlimit(resource.RLIMIT_NPROC,(128,128)); raised=True
except (OSError,ValueError): pass
emit({'children_started':len(children),'errno':error,'hard_limit_raise_succeeded':raised})
''',
    "threads": HEADER + '''import threading, resource
event=threading.Event()
threads=[]
error=None
for i in range(100):
    try:
        t=threading.Thread(target=event.wait)
        t.start()
        threads.append(t)
    except (OSError,RuntimeError) as e:
        error=type(e).__name__
        break
event.set()
for t in threads: t.join()
raised=False
try: resource.setrlimit(resource.RLIMIT_NPROC,(128,128)); raised=True
except (OSError,ValueError): pass
emit({'threads_started':len(threads),'error':error,'hard_limit_raise_succeeded':raised})
''',
    "cpu": HEADER + '''import time
begin=time.monotonic()
x=1
while time.monotonic()-begin < 3: x=(x*3+1)%10000019
emit({'elapsed_seconds':time.monotonic()-begin,'value':x})
''',
    "memory": HEADER + '''import pandas as pd
emit({'probe':'memory','pandas':pd.__version__})
parts=[]
fd=os.open('/dev/zero',os.O_RDONLY)
while True:
    parts.append(os.read(fd,1024*1024*1024))
''',
    "timeout": HEADER + '''import time
emit({'probe':'timeout'})
print('timeout-probe-start',flush=True)
while True: time.sleep(1)
''',
    "descendants": HEADER + '''import time
emit({'probe':'descendants'})
if os.fork()==0:
    os.setsid()
    while True: time.sleep(1)
print('descendant-probe-start',flush=True)
while True: time.sleep(1)
''',
    "logs": HEADER + '''for stream in (1,2):
    for i in range(64): os.write(stream,b'x'*4096)
emit({'wrote_per_stream':262144})
''',
    "symlink": "import os\nos.symlink('/etc/passwd','/output/ledger.jsonl')\n"
               "open('/output/unresolved.jsonl','w').close()\n",
    "fifo": "import os\nos.mkfifo('/output/ledger.jsonl')\n"
            "open('/output/unresolved.jsonl','w').close()\n",
    "hardlink": "import os\nopen('/output/ledger.jsonl','w').close()\n"
                "os.link('/output/ledger.jsonl','/output/unresolved.jsonl')\n",
    "extra": HEADER + "emit({})\nopen('/output/extra','w').close()\n",
    "output_bytes": "open('/output/ledger.jsonl','wb').write(b'x'*10485761)\n"
                    "open('/output/unresolved.jsonl','w').close()\n",
    "output_lines": "open('/output/ledger.jsonl','wb').write(b'{}\\n'*20001)\n"
                    "open('/output/unresolved.jsonl','w').close()\n",
    "storage": HEADER + '''results={}
for target in ('/scratch','/output','/dev/shm','/tmp'):
    count=0
    paths=[]
    try:
        for index in range(3):
            path=target+'/flood'+str(index)
            paths.append(path)
            with open(path,'wb',buffering=0) as f:
                for chunk in range(32): count+=f.write(b'x'*1048576)
        error=None
    except OSError as e: error=e.errno
    finally:
        for path in paths:
            try: os.unlink(path)
            except OSError: pass
    results[target]={'bytes_written':count,'errno':error}
with open('/scratch/shared-marker','wb') as f: f.write(b'shared-backing')
results['aliases_share_bytes']=all(open(p+'/shared-marker','rb').read()==b'shared-backing'
                                 for p in ('/tmp','/dev/shm'))
os.unlink('/scratch/shared-marker')
count=0
paths=[]
try:
    for index,target in enumerate(('/scratch','/tmp','/dev/shm')):
        path=target+'/combined'+str(index)
        paths.append(path)
        with open(path,'wb',buffering=0) as f:
            for chunk in range(32): count+=f.write(b'x'*1048576)
    error=None
except OSError as e: error=e.errno
finally:
    for path in paths: os.unlink(path)
results['combined_aliases']={'bytes_written':count,'errno':error}
emit(results)
''',
    "inodes": HEADER + '''results={}
for target in ('/scratch','/output'):
    paths=[]
    error=None
    try:
        for n in range(1500):
            path=target+'/f'+str(n)
            open(path,'wb').close()
            paths.append(path)
    except OSError as e: error=e.errno
    finally:
        for path in paths: os.unlink(path)
    results[target]={'files_created':len(paths),'errno':error}
emit(results)
''',
}

# Exercise the guest's fork accounting below the stricter host-runtime task
# ceiling. This changes only this fixture's own limit, never deployment policy.
# Keep the original default-limit fork test and its failures as separate evidence.
PROBES["fork_limit_lowered"] = PROBES["forks"].replace(
    "children=[]", "resource.setrlimit(resource.RLIMIT_NPROC,(32,32))\nchildren=[]")


def client(config, certificate="controller", pin=None):
    context = tls_context(ROOT / "tls/ca.pem", ROOT / f"tls/{certificate}.pem",
                          ROOT / f"tls/{certificate}.key", server=False)
    return WorkerClient(config["worker_address"], context,
                        pin or config["worker_certificate_sha256"], config["runtime_sha256"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("probe", choices=("identity", *PROBES))
    args = parser.parse_args()
    config = json.loads((ROOT / "worker.json").read_text())
    if Path("/etc/machine-id").read_text().strip() != config["control_machine_id"]:
        raise SystemExit("DESIGNATED_CONTROL_REQUIRED")
    os.umask(0o077)
    transport = client(config)
    if args.probe == "identity":
        result = transport.call({"v": 1, "op": "identity"})
        if result["sha256"] != config["runtime_sha256"]:
            raise RuntimeError("INSTALLED_RUNTIME_MISMATCH")
        for bad in (client(config, "unapproved"), client(config, pin="0" * 64)):
            try:
                bad.call({"v": 1, "op": "identity"})
            except SupervisorError:
                continue
            raise RuntimeError("UNAPPROVED_TLS_IDENTITY_ACCEPTED")
        print(json.dumps({"identity": "matched_independent_install_pins",
                          "unauthorized_client_and_server_pin": "rejected"}))
        return
    pipeline = PROBES[args.probe]
    if args.probe == "network":
        targets = json.loads((ROOT / "network-targets.json").read_text())
        if set(targets) != {"private_control", "private_worker", "controlled_external",
                            "external_ipv4", "external_ipv6", "metadata"}:
            raise RuntimeError("INVALID_NETWORK_FIXTURE")
        for address, port in targets.values():
            ipaddress.ip_address(address)
            if type(port) is not int or port not in (80, 443, 9443, 9444):
                raise RuntimeError("INVALID_NETWORK_FIXTURE")
        pipeline = HEADER + "targets=" + repr(targets) + '''
import socket
results={}
for name,(address,port) in targets.items():
    family=socket.AF_INET6 if ':' in address else socket.AF_INET
    with socket.socket(family,socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        try: sock.connect((address,port)); results[name]='CONNECTED'
        except OSError as error: results[name]={'errno':error.errno,'type':type(error).__name__}
try:
    socket.getaddrinfo('example.com',443)
    results['dns']='RESOLVED'
except OSError as error: results['dns']={'errno':error.errno,'type':type(error).__name__}
with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
    sock.settimeout(1)
    try: sock.sendto(b'probe',('1.1.1.1',53)); results['udp']='SENT'
    except OSError as error: results['udp']={'errno':error.errno,'type':type(error).__name__}
try:
    sock=socket.socket(socket.AF_INET,socket.SOCK_RAW,socket.IPPROTO_ICMP)
    sock.close()
    results['raw_socket']='CREATED'
except OSError as error: results['raw_socket']={'errno':error.errno,'type':type(error).__name__}
emit(results)
'''
    request = ExecutionRequest(authority_id(), authority_id(), 1,
                               pipeline.encode(), b"", b"", b"{}")
    identifier = request.execution_id.hex
    intent = {"probe": args.probe, "execution": identifier, "job": request.job_id.hex,
              "generation": 1, "manifest": request.manifest_hash(),
              "pipeline_base64": base64.b64encode(request.pipeline).decode()}
    with (EVIDENCE / (identifier + ".intent.json")).open("x") as file:
        json.dump(intent, file, sort_keys=True)
        file.flush()
        os.fsync(file.fileno())
    receipt = transport.create(request)
    (EVIDENCE / (identifier + ".receipt.json")).write_text(json.dumps(receipt, sort_keys=True))
    report = {"probe": args.probe, "execution": identifier, "receipt": receipt}
    if receipt.get("collected"):
        captures = EVIDENCE / "captures"
        captures.mkdir(mode=0o700, exist_ok=True)
        path = transport.capture_to(captures, request.execution_id, request.job_id, 1,
                                    request.manifest_hash())
        raw = (path / "ledger.jsonl").read_bytes()
        if len(raw) < 8192:
            report["observed"] = json.loads(raw)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
