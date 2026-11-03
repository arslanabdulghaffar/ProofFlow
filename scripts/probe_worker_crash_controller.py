"""Fixed crash-test transport; payload executes only through the isolated worker."""

import json
import os
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, "/opt/proofflow-control")
from probe_worker_controller import EVIDENCE, PROBES, ROOT, client  # noqa: E402

from worker.protocol import ExecutionRequest  # noqa: E402

operation, execution_text, job_text = sys.argv[1:]
execution, job = UUID(hex=execution_text), UUID(hex=job_text)
config = json.loads((ROOT / "worker.json").read_text())
if Path("/etc/machine-id").read_text().strip() != config["control_machine_id"]:
    raise SystemExit("DESIGNATED_CONTROL_REQUIRED")
transport = client(config)
if operation == "dispatch":
    os.umask(0o077)
    request = ExecutionRequest(execution, job, 1, PROBES["descendants"].encode(), b"", b"", b"{}")
    with (EVIDENCE / (execution.hex + ".crash-intent.json")).open("x") as output:
        json.dump(
            {
                "execution": execution.hex,
                "job": job.hex,
                "manifest": request.manifest_hash(),
                "fixture": "descendants",
            },
            output,
        )
        output.flush()
        os.fsync(output.fileno())
    result = transport.create(request)
elif operation == "status":
    result = transport.call(
        {"v": 1, "op": "status", "execution": execution.hex, "job": job.hex, "generation": 1}
    )
else:
    raise SystemExit("UNKNOWN_CRASH_PROBE_OPERATION")
print(json.dumps(result, sort_keys=True))
