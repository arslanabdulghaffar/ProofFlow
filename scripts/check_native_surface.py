"""Read-only native-library inventory on pinned product image and designated worker.

No exploit payload, uploaded database, candidate program, provider call or new resource.
Presence/absence of an entry point is scoped evidence, never vulnerability clearance.
"""

import hashlib
import json
import shlex
import subprocess
from datetime import UTC, datetime

from check_product_image import IMAGE
from product_live_session import LiveSession, require
from vultr_phase1 import PRIVATE

PROBE = """
import hashlib,json,os,sqlite3,sys,zlib
from contextlib import closing
from pathlib import Path
with closing(sqlite3.connect(':memory:')) as db:
 options=[r[0] for r in db.execute('PRAGMA compile_options')]
paths=set()
for line in Path('/proc/self/maps').read_text().splitlines():
 parts=line.split()
 if len(parts)<6:continue
 p=parts[-1]
 if p.startswith(('/usr/','/lib/')) and any(s in p for s in
  ('libsqlite3','libz.so','_sqlite3.','zlib.')):
  paths.add(p)
libraries=[{'path':p,'sha256':hashlib.sha256(Path(p).read_bytes()).hexdigest()}
 for p in sorted(paths)]
result={'python':sys.version.split()[0],'sqlite':sqlite3.sqlite_version,
 'zlib_compile':zlib.ZLIB_VERSION,'zlib_runtime':zlib.ZLIB_RUNTIME_VERSION,
 'sqlite_fts5_compiled':'ENABLE_FTS5' in options,
 'sqlite_session_compiled':'ENABLE_SESSION' in options,'libraries':libraries}
if os.environ.get('PROOFFLOW_FIXED_WORKER_INVENTORY')=='1':
 p=Path('/var/lib/proofflow-worker/state/journal.sqlite3')
 with closing(sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True)) as db:
  schema=db.execute("SELECT type,name,sql FROM sqlite_master ORDER BY type,name").fetchall()
  result['worker_journal_virtual_tables']=[n for t,n,s in schema
   if s and 'VIRTUAL TABLE' in s.upper()]
  result['worker_journal_schema_sha256']=hashlib.sha256(json.dumps(schema).encode()).hexdigest()
  result['worker_journal_tables']=[n for t,n,s in schema if t=='table']
print(json.dumps(result,sort_keys=True))
"""


def main():
    reply = subprocess.run(  # noqa: S603 - pinned trusted image, fixed introspection only
        ["C:/Windows/System32/wsl.exe", "-d", "Ubuntu-24.04", "--", "docker", "run", "--rm",
         "--pull=never", "--network=none", "--read-only", "--cap-drop=ALL",
         "--security-opt=no-new-privileges", "--memory=128m", "--memory-swap=128m",
         "--cpus=1", "--pids-limit=16", "--user=10003:10003", "--entrypoint=python",
         "sha256:" + IMAGE, "-I", "-B", "-c", PROBE], capture_output=True, timeout=30
    )
    require(reply.returncode == 0, "NATIVE_IMAGE_INVENTORY_FAILED")
    result = {"observed_at": datetime.now(UTC).isoformat(), "image": IMAGE,
              "product": json.loads(reply.stdout), "provider_calls": 0, "new_resources": 0,
              "vulnerability_clearance": False}
    with LiveSession() as live:
        for role in ("api", "dispatcher"):
            require(live.host("docker inspect --format '{{.Image}}' proofflow-product-" + role)
                    == ("sha256:" + IMAGE).encode(), "DEPLOYED_IMAGE_CHANGED")
        worker = live.admin.host(
            "worker", "PROOFFLOW_FIXED_WORKER_INVENTORY=1 /usr/bin/python3 -I -S -B -c "
            + shlex.quote(PROBE), timeout=30
        )
        require(worker.returncode == 0, "WORKER_NATIVE_INVENTORY_FAILED")
        result["worker"] = json.loads(worker.stdout)
        require(result["worker"]["worker_journal_virtual_tables"] == [],
                "UNREVIEWED_WORKER_VIRTUAL_TABLE")
        require(set(result["worker"]["worker_journal_tables"])
                == {"executions", "fences", "authority_clock"}, "WORKER_SCHEMA_CHANGED")
        result["runtime"] = live.policy["runtime_sha256"]
        result["credit"] = live.credit
        result["probe_sha256"] = hashlib.sha256(PROBE.encode()).hexdigest()
    (PRIVATE / "evidence/phase5-native-surface.json").write_text(
        json.dumps(result, sort_keys=True, indent=2), encoding="utf-8"
    )
    print(json.dumps({"inventory": "passed", "product_sqlite": result["product"]["sqlite"],
                      "worker_sqlite": result["worker"]["sqlite"], "virtual_tables": 0,
                      "product_native_hashes": len(result["product"]["libraries"]),
                      "worker_native_hashes": len(result["worker"]["libraries"]),
                      "vulnerability_clearance": False}))


if __name__ == "__main__":
    main()
