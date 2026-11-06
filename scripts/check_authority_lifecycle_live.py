"""Read-only deployed lifecycle acceptance; no expiry clocks or job states edited."""

import hashlib
import json
import shlex
from datetime import UTC, datetime

from product_live_session import LiveSession, require
from vultr_phase1 import PRIVATE, ROOT

WORKER = """
import hashlib,json,sqlite3,time
from contextlib import closing
from pathlib import Path
path=Path('/var/lib/proofflow-worker/state/journal.sqlite3')
with closing(sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True)) as db:
 counts=dict(db.execute('SELECT state,count(*) FROM executions GROUP BY state'))
 missing=db.execute('SELECT count(*) FROM executions WHERE retire_at IS NULL').fetchone()[0]
 fences,missing_fences=db.execute('SELECT count(*),count(*) FILTER '
  '(WHERE retire_at IS NULL) FROM fences').fetchone()
 floor=db.execute('SELECT observed FROM authority_clock WHERE singleton=1').fetchone()[0]
 assert missing==missing_fences==0 and all(k=='CLEANED' for k in counts)
 assert 0<floor<=time.time()+5
 hashes={n:hashlib.sha256((Path('/opt/proofflow-worker/worker')/n).read_bytes()).hexdigest()
  for n in ('journal.py','supervisor.py','protocol.py')}
 print(json.dumps({'counts':counts,'fences':fences,'missing_deadlines':0,
  'clock_floor_present':True,'sources':hashes}))
"""


def main():
    update = json.loads((PRIVATE / "evidence/phase5-worker-authority-expiry.json").read_bytes())
    enabled = json.loads(
        (PRIVATE / "evidence/phase5-authority-retention-enabled.json").read_bytes()
    )
    installed = json.loads((PRIVATE / "evidence/product-retention-install.json").read_bytes())
    require(update["completed"] and enabled["completed"], "LIFECYCLE_NOT_INSTALLED")
    with LiveSession() as live:
        require(live.policy["runtime_sha256"] == update["new_runtime"], "RUNTIME_CHANGED")
        result = live.admin.host(
            "worker", "/usr/bin/python3 -I -S -B -c " + shlex.quote(WORKER), timeout=30
        )
        require(result.returncode == 0, "WORKER_LIFECYCLE_READBACK_FAILED")
        report = json.loads(result.stdout)
        for name, digest in report["sources"].items():
            require(hashlib.sha256((ROOT / "worker" / name).read_bytes()).hexdigest() == digest,
                    "WORKER_SOURCE_CHANGED")
        target = "/opt/proofflow-retention/" + installed["revision"]
        for name, digest in installed["sources"].items():
            require(live.host("sha256sum " + target + "/" + name).decode().split()[0] == digest,
                    "RETENTION_SOURCE_CHANGED")
        require(live.sql("SET ROLE pf_product_provisioner; "
                         "SELECT pf_product.retention_expiry_ready();") == b"t",
                "EXPIRY_NOT_RUNTIME_BOUND")
        require(live.sql("SELECT count(*) FROM pf_product.workspaces;") == b"0",
                "RECOVERY_FIXTURES_REMAIN")
        require(live.sql("SELECT count(*) FROM pg_database "
                         "WHERE datname LIKE 'proofflow_restore_%';") == b"0",
                "RESTORE_CLONE_REMAINS")
        require(live.sql("SELECT count(*)=1 AND bool_and(blocked) FROM pf_budget.accounts;",
                         "proofflow_budget") == b"t", "INFERENCE_NOT_BLOCKED")
        services = live.host("systemctl is-active proofflow-product-api.service "
                             "proofflow-product-dispatcher.service "
                             "proofflow-product-retention.timer").decode().splitlines()
        require(services == ["active"] * 3, "SERVICES_NOT_HEALTHY")
        status = live.host("systemctl show proofflow-product-retention.service "
                           "--property=Result --property=ExecMainStatus").decode().splitlines()
        require(set(status) == {"Result=success", "ExecMainStatus=0"}, "RETENTION_FAILED")
        report.update(observed_at=datetime.now(UTC).isoformat(), credit=live.credit,
                      services=services, retention_status=status, runtime_bound_expiry=True,
                      workspaces_remaining=0, restore_clones_remaining=0,
                      product_admission="closed", inference_admission="closed",
                      natural_seven_day_expiry="NOT_YET_ELAPSED", clock_edits=False,
                      retention_revision=installed["revision"])
        (PRIVATE / "evidence/phase5-authority-lifecycle-readback.json").write_text(
            json.dumps(report, sort_keys=True), encoding="utf-8"
        )
        print(json.dumps({k: report[k] for k in (
            "counts", "fences", "missing_deadlines", "runtime_bound_expiry", "services",
            "workspaces_remaining", "restore_clones_remaining", "natural_seven_day_expiry"
        )}))


if __name__ == "__main__":
    main()
