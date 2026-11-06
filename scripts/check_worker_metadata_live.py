"""Read-only deployed receipt-deadline/source checks; never edits journal clocks."""

import argparse
import hashlib
import json
import shlex
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from product_live_session import LiveSession, require  # noqa: E402
from vultr_phase1 import PRIVATE  # noqa: E402

REMOTE = """
import hashlib,json,os,sqlite3,stat,time
from contextlib import closing
from pathlib import Path
p=Path('/var/lib/proofflow-worker/state/journal.sqlite3'); i=p.lstat()
assert stat.S_ISREG(i.st_mode) and i.st_nlink==1 and i.st_uid==0
assert stat.S_IMODE(i.st_mode)==0o600
with closing(sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True)) as c:
 columns={r[1] for r in c.execute('PRAGMA table_info(executions)')}
 assert 'receipt_expires_at' in columns
 counts=dict(c.execute('SELECT state,count(*) FROM executions GROUP BY state'))
 missing=c.execute('SELECT count(*) FROM executions WHERE receipt IS NOT NULL '
  'AND receipt_expires_at IS NULL AND coalesce(json_extract(receipt,'
  '\"$.receipt_retired\"),0)!=1').fetchone()[0]
 bounds=c.execute('SELECT min(receipt_expires_at),max(receipt_expires_at) '
  'FROM executions WHERE receipt_expires_at IS NOT NULL').fetchone()
 fences=c.execute('SELECT count(*) FROM fences').fetchone()[0]
 assert missing==0 and not any(k!='CLEANED' and v for k,v in counts.items())
 assert bounds[0] is not None and bounds[1]<=time.time()+7*86400+5
 hashes={n:hashlib.sha256((Path('/opt/proofflow-worker/worker')/n).read_bytes()).hexdigest()
  for n in ('journal.py','supervisor.py')}
 print(json.dumps({'counts':counts,'missing_deadlines':missing,'deadline_bounds':bounds,
  'fences':fences,'sources':hashes,'observed_epoch':time.time()}))
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--after-probes", action="store_true")
    args = parser.parse_args()
    name = "phase5-worker-metadata-" + ("after-probes" if args.after_probes else "readback")
    path = PRIVATE / ("evidence/" + name + ".json")
    require(not path.exists(), "METADATA_READBACK_ALREADY_RECORDED")
    update = json.loads((PRIVATE / "evidence/phase5-worker-metadata-update.json").read_bytes())
    require(update["completed"], "METADATA_UPDATE_INCOMPLETE")
    with LiveSession() as live:
        require(live.policy["runtime_sha256"] == update["new_runtime"], "WORKER_PIN_CHANGED")
        reply = live.admin.host("worker", "/usr/bin/python3 -I -S -B -c " + shlex.quote(REMOTE),
                                timeout=30)
        require(reply.returncode == 0, "WORKER_METADATA_READBACK_FAILED")
        result = json.loads(reply.stdout)
        require(result["sources"] == update["new_sources"], "WORKER_SOURCE_CHANGED")
        started = datetime.fromisoformat(update["started_at"]).timestamp()
        require(result["deadline_bounds"][0] >= started + 7 * 86400 - 2,
                "WORKER_MIGRATION_DEADLINE_INVALID")
        result.update(observed_at=datetime.now(UTC).isoformat(), credit=live.credit,
                      scope="actual_deployed_deadlines_and_sources_read_only",
                      natural_seven_day_expiry="NOT_YET_ELAPSED",
                      raw_receipt_sha256=hashlib.sha256(reply.stdout).hexdigest())
        require(live.sql("SELECT count(*)=1 AND bool_and(blocked) FROM pf_budget.accounts;",
                         "proofflow_budget") == b"t", "INFERENCE_ADMISSION_CHANGED")
        result["service_state"] = live.host("systemctl is-active proofflow-product-api.service "
                                           "proofflow-product-dispatcher.service "
                                           "proofflow-product-retention.timer").decode().splitlines()
        require(result["service_state"] == ["active"] * 3, "PRODUCT_SERVICE_NOT_ACTIVE")
        result["product_admission"] = "closed"
        result["inference_admission"] = "closed"
        with path.open("xb") as output:
            output.write(json.dumps(result, sort_keys=True).encode())
        print(json.dumps({"deadlines_verified": True, "counts": result["counts"],
                          "fences": result["fences"], "missing_deadlines": 0,
                          "natural_seven_day_expiry": "NOT_YET_ELAPSED"}))


if __name__ == "__main__":
    main()
