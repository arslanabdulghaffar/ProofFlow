"""Real designated-worker fixture; natural expiry and readback, never a local execution."""

import argparse
import base64
import hashlib
import json
import shlex
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from product_live_session import LiveSession, require  # noqa: E402
from vultr_phase1 import PRIVATE  # noqa: E402

REMOTE = """import hashlib,json,sys,time
from pathlib import Path
from uuid import UUID
sys.path.insert(0,'/opt/proofflow-control/lib')
from orchestrator.worker_client import WorkerClient
from worker.protocol import ExecutionRequest,SupervisorError
from worker.wire import tls_context
r=Path('/opt/proofflow-control'); c=json.loads((r/'worker.json').read_bytes())
v=json.load(sys.stdin); marker='INERT_PREVIEW_'+v['execution']
source=('print('+repr(marker)+',flush=True)\\n').encode()
q=ExecutionRequest(UUID(v['execution']),UUID(v['job']),1,source,b'',b'',b'{}')
w=WorkerClient(c['worker_address'],tls_context(r/'tls/ca.pem',r/'tls/controller.pem',
 r/'tls/controller.key',server=False),c['worker_certificate_sha256'],c['runtime_sha256'])
deadline=time.monotonic()+5
while True:
 try:
  assert w.call({'v':1,'op':'identity'})['sha256']==c['runtime_sha256']
  break
 except SupervisorError as error:
  if str(error)!='WORKER_DELIVERY_UNKNOWN' or time.monotonic()>=deadline: raise
  time.sleep(0.25)
if v['mode']=='start':
 result=w.create(q)
 assert result['cleanup']=='confirmed' and not result['collected']
 assert result['outcome']=='output_rejected' and result['failure_log_preview']
 import base64
 assert any(marker.encode() in base64.b64decode(x['base64'])
            for x in result['failure_log_preview'])
 result={'preview_sha256':hashlib.sha256(json.dumps(result['failure_log_preview'],
         sort_keys=True).encode()).hexdigest(),
         'receipt_sha256':hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest(),
         'manifest':result['manifest'],'cleanup':result['cleanup']}
else:
 result=w.call({'v':1,'op':'status','execution':q.execution_id.hex,'job':q.job_id.hex,'generation':1})
 assert result['state']=='CLEANED'
 receipt=result['receipt']
 if not receipt.get('failure_log_preview_retired'):
  print(json.dumps({'waiting_for_expiry':True})); sys.exit(0)
 assert 'failure_log_preview' not in receipt and receipt['cleanup']=='confirmed'
 assert receipt['failure_log_preview_sha256']==v['preview_sha256']
 assert receipt['manifest']==v['manifest']
 assert w.create(q)==receipt
 changed=ExecutionRequest(q.execution_id,q.job_id,1,b'# changed inert bytes',b'',b'',b'{}')
 try: w.create(changed)
 except SupervisorError: pass
 else: raise RuntimeError('CONFLICT_ACCEPTED')
 result={'retired':True,'cleanup':'confirmed','exact_replay':True,'changed_source_rejected':True}
print(json.dumps(result))
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('start', 'reconcile', 'restart', 'readback'))
    args = parser.parse_args()
    path = PRIVATE / 'evidence/phase5-worker-preview-probe.json'
    if args.mode == 'start':
        require(not path.exists(), 'PREVIEW_PROBE_EXISTS_RECONCILE')
        value = {'execution': uuid4().hex, 'job': uuid4().hex,
                 'started_at': datetime.now(UTC).isoformat(), 'completed': False}
        path.write_text(json.dumps(value), encoding='utf-8')
    else:
        value = json.loads(path.read_bytes())
        require(value['completed'] == (args.mode in ('restart', 'readback')),
                'PREVIEW_PROBE_MODE_MISMATCH')
    with LiveSession() as live:
        if args.mode == 'restart':
            require(not value.get('restart_passed'), 'PREVIEW_RESTART_ALREADY_COMPLETE')
            require(live.sql("SELECT count(*) FROM pf_product.jobs WHERE state IN "
                             "('QUEUED','RUNNING','RECONCILING');") == b'0', 'PRODUCT_NOT_IDLE')
            value['restart_requested_at'] = datetime.now(UTC).isoformat()
            path.write_text(json.dumps(value, indent=2), encoding='utf-8')
            restarted = live.admin.host('worker',
                'systemctl restart proofflow-worker.service && '
                'systemctl is-active proofflow-worker.service', timeout=60)
            require(restarted.returncode == 0 and restarted.stdout.strip() == b'active',
                    'WORKER_RESTART_FAILED')
        reply = json.loads(live.host('/usr/bin/python3 -I -B -c ' + shlex.quote(REMOTE),
                                     json.dumps({**value, 'mode': args.mode}).encode()))
        if args.mode == 'start':
            value.update(reply)
            value['created_at'] = datetime.now(UTC).isoformat()
        elif reply.get('waiting_for_expiry'):
            print(json.dumps(reply))
            return
        else:
            value['readback'] = reply
            # Read only metadata and byte-absence booleans from the fixed worker journal.
            marker = base64.b64encode(('INERT_PREVIEW_' + value['execution'] + '\n').encode())
            script = """import json,sqlite3,sys
from pathlib import Path
p=Path('/var/lib/proofflow-worker/state/journal.sqlite3')
c=sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True)
rows=c.execute('SELECT count(*) FROM executions').fetchone()[0]
expired=c.execute('SELECT count(*) FROM executions '
                  'WHERE preview_expires_at<=unixepoch()').fetchone()[0]
c.close()
marker=sys.stdin.buffer.read()
for name in ('journal.sqlite3','journal.sqlite3-wal'):
 f=p.with_name(name)
 if f.exists():
  assert f.stat().st_size<=33554432
  assert marker not in f.read_bytes()
print(json.dumps({'raw_marker_absent_database_and_wal':True,'expired_previews':expired,
                  'execution_records_retained':rows}))
"""
            check = live.admin.host('worker', '/usr/bin/python3 -I -S -B -c ' + shlex.quote(script),
                                    stdin=marker, timeout=30)
            require(check.returncode == 0, 'RAW_PREVIEW_BYTES_REMAIN')
            value['physical'] = json.loads(check.stdout)
            value['completed'] = True
            if args.mode == 'restart':
                value['restart_passed'] = True
            elif args.mode == 'readback':
                value['later_readback_passed'] = True
            value['finished_at'] = datetime.now(UTC).isoformat()
            value['credit'] = live.credit
        value['runtime_sha256'] = live.policy['runtime_sha256']
        value['controller_sha256'] = hashlib.sha256(REMOTE.encode()).hexdigest()
        value.setdefault('controller_hashes', {})[args.mode] = value['controller_sha256']
        value.setdefault('readback_history', []).append({
            'mode': args.mode, 'observed_at': datetime.now(UTC).isoformat(),
            'controller_sha256': value['controller_sha256'], 'completed': value['completed']})
        path.write_text(json.dumps(value, indent=2), encoding='utf-8')
        print(json.dumps({'mode': args.mode, 'completed': value['completed'],
                          'cleanup': value['cleanup']}))


if __name__ == '__main__':
    main()
