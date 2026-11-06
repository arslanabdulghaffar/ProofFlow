"""Closed/idle reviewed worker update and exact runtime repin on existing VMs only."""

import argparse
import base64
import hashlib
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from product_live_session import LiveSession, require  # noqa: E402
from vultr_phase1 import PRIVATE, ROOT  # noqa: E402

PREVIOUS = '67920adc671b0084078fa71e1b17a929ed66dba2'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--receipt-metadata', action='store_true',
                        help='Distinct seven-day receipt update; never replay preview update')
    args = parser.parse_args()
    previous = 'ea8f7a23dc32e7908c95b38ef88863a2d40ab263' if args.receipt_metadata else PREVIOUS
    operation = 'worker-metadata-update' if args.receipt_metadata else 'worker-retention-update'
    receipt = PRIVATE / ('evidence/phase5-' + operation + '.json')
    require(not receipt.exists(), 'WORKER_UPDATE_ALREADY_STARTED_RECONCILE')
    old, new = {}, {}
    for path in sorted((ROOT / 'worker').glob('*.py')):
        raw = subprocess.run(  # noqa: S603 - fixed trusted commit, read-only source bytes
            ['C:/Program Files/Git/cmd/git.exe', 'show', previous + ':worker/' + path.name],
            capture_output=True, check=True).stdout
        old[path.name] = hashlib.sha256(raw).hexdigest()
        if path.read_bytes() != raw:
            new[path.name] = base64.b64encode(path.read_bytes()).decode()
    require(set(new) == {'journal.py', 'supervisor.py'}, 'UNEXPECTED_WORKER_CHANGES')
    record = {'started_at': datetime.now(UTC).isoformat(), 'previous_commit': previous,
              'old_sources': old, 'new_sources': {
                  n: hashlib.sha256(base64.b64decode(raw)).hexdigest() for n, raw in new.items()},
              'completed': False}

    def persist():
        receipt.write_text(json.dumps(record, indent=2), encoding='utf-8')

    with LiveSession() as live:
        require(live.sql("SELECT count(*) FROM pf_product.jobs WHERE state IN "
                         "('QUEUED','RUNNING','RECONCILING');") == b'0', 'JOBS_NOT_IDLE')
        require(live.sql("SELECT count(*)=1 AND bool_and(blocked) FROM pf_budget.accounts;",
                         'proofflow_budget') == b't', 'INFERENCE_MUST_BE_CLOSED')
        control_config = json.loads(live.host('cat /opt/proofflow-control/worker.json'))
        dispatcher_config = json.loads(live.host(
            'cat /etc/proofflow-product-dispatcher/worker/worker.json'))
        require({**control_config, 'verifier_sha256': live.policy['verifier_sha256']}
                == dispatcher_config
                and control_config['runtime_sha256'] == live.policy['runtime_sha256'],
                'CONTROLLER_PINS_CHANGED')
        record.update(credit=live.credit, old_policy=live.policy,
                      old_runtime=control_config['runtime_sha256'])
        identity = dict(control_config['runtime_identity'])
        # The identity binds exactly the fixed worker runtime file set.
        names = ('__init__', 'runtime', 'launcher', 'host', 'start_gate', 'staging', 'collector',
                 'protocol', 'journal', 'supervisor', 'log_capture', 'rootfs', 'wire', 'service',
                 'entrypoint', 'metrics', 'runtime_bundle')
        previous_sources = {n: old[n + '.py'] for n in names}
        require(hashlib.sha256(json.dumps(previous_sources, sort_keys=True).encode()).hexdigest()
                == identity['supervisor_sha256'], 'PREVIOUS_WORKER_SOURCE_PIN_CHANGED')
        sources = {n: hashlib.sha256((ROOT / 'worker' / (n + '.py')).read_bytes()).hexdigest()
                   for n in names}
        identity['supervisor_sha256'] = hashlib.sha256(
            json.dumps(sources, sort_keys=True).encode()).hexdigest()
        runtime = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        require(runtime != live.policy['runtime_sha256'], 'RUNTIME_UNCHANGED')
        config = {**control_config, 'runtime_identity': identity, 'runtime_sha256': runtime}
        record['new_runtime'] = runtime
        persist()

        def worker(command, data=None):
            result = live.admin.host('worker', command, stdin=data, timeout=60)
            if result.returncode:
                record['failure_sha256'] = hashlib.sha256(result.stderr).hexdigest()
                persist()
                raise RuntimeError('WORKER_UPDATE_FAILED_RECONCILE_PRIVATE_RECEIPT')
            return result.stdout.strip()

        require(worker('cat /etc/machine-id').decode() == live.admin.state['worker_machine_id'],
                'WORKER_IDENTITY_CHANGED')
        installer = (ROOT / 'scripts/install_worker_retention_update.py').read_bytes()
        target = ('/var/lib/proofflow-setup/' + operation + '-installer-'
                  + hashlib.sha256(installer).hexdigest())
        worker('set -C; umask 077; cat > ' + target, installer)
        payload = json.dumps({'machine_id': live.admin.state['worker_machine_id'],
                              'old': old, 'new': new}).encode()
        record['preflight'] = json.loads(worker('/usr/bin/python3 -I -S -B ' + target
                                                + ' --check-only', payload))
        live.host('systemctl stop proofflow-product-dispatcher.service')
        record['dispatcher_stopped'] = True
        persist()
        worker('systemctl stop proofflow-worker.service')
        record['install'] = json.loads(worker('/usr/bin/python3 -I -S -B ' + target,
                                              payload))
        persist()
        worker('systemctl start proofflow-worker.service')
        require(worker('systemctl is-active proofflow-worker.service') == b'active',
                'WORKER_NOT_ACTIVE')
        # Trusted fixed-path config update; no provider/App/TLS credentials are changed.
        update = """import hashlib,json,os,stat,sys
from pathlib import Path
v=json.load(sys.stdin)
paths=[Path('/opt/proofflow-control/worker.json'),
       Path('/etc/proofflow-product-dispatcher/worker/worker.json')]
for p in paths:
 i=p.lstat()
 assert stat.S_ISREG(i.st_mode) and i.st_nlink==1 and i.st_uid in (0,10003)
 assert json.loads(p.read_bytes())==v['old'][str(p)]
for p in paths:
 i=p.stat(); old=p.read_bytes(); b=p.with_name(p.name+'.previous-'+hashlib.sha256(old).hexdigest())
 if not b.exists():
  fd=os.open(b,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
  with os.fdopen(fd,'wb') as f: f.write(old); f.flush(); os.fsync(f.fileno())
 else: assert b.read_bytes()==old
 t=p.with_name(p.name+'.retention-pending')
 fd=os.open(t,os.O_WRONLY|os.O_CREAT|os.O_EXCL,stat.S_IMODE(i.st_mode))
 with os.fdopen(fd,'wb') as f:
  f.write(json.dumps(v['new'][str(p)],sort_keys=True).encode()); f.flush(); os.fsync(f.fileno())
 os.chown(t,i.st_uid,i.st_gid); os.replace(t,p)
 fd=os.open(p.parent,os.O_DIRECTORY|os.O_NOFOLLOW); os.fsync(fd); os.close(fd)
print('pins_updated')
"""
        import shlex

        live.host('/usr/bin/python3 -I -B -c ' + shlex.quote(update),
                  json.dumps({'old': {'/opt/proofflow-control/worker.json': control_config,
                    '/etc/proofflow-product-dispatcher/worker/worker.json': dispatcher_config},
                    'new': {'/opt/proofflow-control/worker.json': config,
                    '/etc/proofflow-product-dispatcher/worker/worker.json': {
                        **config, 'verifier_sha256': live.policy['verifier_sha256']}}}).encode())
        deadline = time.monotonic() + 10
        while True:
            try:
                record['identity'] = json.loads(live.host('/usr/bin/python3 -I -B '
                    '/opt/proofflow-control/probe_worker_controller.py identity'))
                break
            except RuntimeError:
                # Identity is read-only; never retry a dispatch or installation.
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.25)
        live.sql("SET ROLE pf_product_provisioner; SELECT pf_product.configure_execution('"
                 + runtime + "','" + live.policy['verifier_sha256'] + "',false);")
        record['new_policy'] = json.loads(live.sql(
            'SELECT row_to_json(p) FROM pf_product.execution_policy p;'))
        require(record['new_policy']['verification_epoch'] == live.policy['verification_epoch'] + 1
                and not record['new_policy']['enabled'], 'SEMANTIC_EPOCH_NOT_ADVANCED')
        live.host('systemctl start proofflow-product-dispatcher.service')
        require(live.host('systemctl is-active proofflow-product-dispatcher.service') == b'active',
                'DISPATCHER_NOT_ACTIVE')
        record['completed'] = True
        record['finished_at'] = datetime.now(UTC).isoformat()
        live.admin.state['probe_controller']['runtime_sha256'] = runtime
        live.admin.save()
        persist()
        print(json.dumps({'worker_updated': True, 'runtime_sha256': runtime,
                          'admissions_closed': True, 'old_versions_invalidated': True}))


if __name__ == '__main__':
    main()
