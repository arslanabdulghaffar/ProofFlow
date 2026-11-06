"""Fixed two-file worker update, after service drain; never handles candidate code."""

import base64
import hashlib
import json
import os
import sqlite3
import stat
import sys
from contextlib import closing
from pathlib import Path


def require(value, code):
    if not value:
        raise RuntimeError(code)


def regular(path, mode=None):
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and info.st_nlink == 1
            and not info.st_mode & 0o022, "UPDATE_FILE_UNSAFE")
    if mode is not None:
        require(stat.S_IMODE(info.st_mode) == mode, "UPDATE_FILE_MODE_CHANGED")


def replace_bytes(path, raw, mode):
    temporary = path.with_name(path.name + ".retention-pending")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, "wb") as output:
        os.fchmod(output.fileno(), mode)
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)
    parent = os.open(path.parent, os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(parent)
    finally:
        os.close(parent)


def main():
    value = json.load(sys.stdin)
    require(os.geteuid() == 0 and Path('/etc/machine-id').read_text().strip()
            == value['machine_id'], "DESIGNATED_WORKER_REQUIRED")
    require(set(value['new']) in ({'journal.py', 'supervisor.py'},
                                 {'journal.py', 'supervisor.py', 'protocol.py'}),
            "UNEXPECTED_WORKER_CHANGE")
    root = Path('/opt/proofflow-worker/worker')
    regular(root / 'journal.py', 0o644)
    for name, expected in value['old'].items():
        require(name.endswith('.py') and '/' not in name and '\\' not in name,
                "INVALID_SOURCE_NAME")
        path = root / name
        regular(path, 0o644)
        require(hashlib.sha256(path.read_bytes()).hexdigest() == expected, "SOURCE_CHANGED")
    state = Path('/var/lib/proofflow-worker/state')
    require(not list((state / 'executions').iterdir()), "WORKER_STAGING_NOT_IDLE")
    regular(state / 'journal.sqlite3', 0o600)
    with closing(sqlite3.connect('file:' + str(state / 'journal.sqlite3') + '?mode=ro',
                                uri=True)) as db:
        require(db.execute("SELECT count(*) FROM executions WHERE state!='CLEANED'")
                .fetchone()[0] == 0, "WORKER_JOURNAL_NOT_IDLE")
    receipt = Path('/var/lib/proofflow-setup/worker-install.json')
    regular(receipt)
    install = json.loads(receipt.read_bytes())
    for name, expected in value['old'].items():
        require(install['files']['code/' + name]['sha256'] == expected,
                "INSTALL_RECEIPT_CHANGED")
    decoded = {name: base64.b64decode(encoded, validate=True)
               for name, encoded in value['new'].items()}
    require(all(0 < len(raw) < 65536 for raw in decoded.values()), "SOURCE_SIZE_INVALID")
    if sys.argv[1:] == ['--check-only']:
        print(json.dumps({'preflight': 'passed'}))
        return
    require(sys.argv[1:] == [], "UNEXPECTED_UPDATE_MODE")
    revision = hashlib.sha256(json.dumps(value['new'], sort_keys=True).encode()).hexdigest()
    backup = Path('/var/lib/proofflow-setup/retention-update-' + revision)
    backup.mkdir(mode=0o700)  # Unknown/partial upgrade cannot be blindly replayed.
    for name in sorted(decoded):
        old = (root / name).read_bytes()
        fd = os.open(backup / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
        with os.fdopen(fd, 'wb') as file:
            file.write(old)
            file.flush()
            os.fsync(file.fileno())
    replace_bytes(backup / 'previous-install.json', receipt.read_bytes(), 0o400)
    for name, raw in decoded.items():
        replace_bytes(root / name, raw, 0o644)
        install['files']['code/' + name]['sha256'] = hashlib.sha256(raw).hexdigest()
    replace_bytes(receipt, json.dumps(install, sort_keys=True).encode(), 0o600)
    print(json.dumps({'revision': revision, 'changed_files': len(decoded),
                      'previous_sources_preserved': True,
                      'journal_copied': False}))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('WORKER_RETENTION_UPDATE_FAILED_RECONCILE_NO_RETRY') from None
