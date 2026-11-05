"""Finite real-model pilot on existing VMs; fresh quote, dual ledger, no product writes."""

import hashlib
import io
import json
import shlex
import sys
import tarfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from install_product_services import IMAGE  # noqa: E402
from product_live_session import LiveSession, require  # noqa: E402
from vultr_phase1 import PRIVATE, ROOT  # noqa: E402

from eval.development import cases  # noqa: E402

SELECTED = ("units-repairable", "joins-repairable", "downstream-repairable", "downstream-ambiguous")


def main():
    record = PRIVATE / "evidence/phase5-model-pilot-v1.json"
    require(not record.exists(), "PILOT_ALREADY_STARTED_RECONCILE_NO_RETRY")
    dataset = [c for c in cases() if c["id"] in SELECTED]
    jobs = [{"run_id": str(uuid4()), "case": case, "arm": arm} for case in SELECTED
            for arm in sorted("ABC", key=lambda a: hashlib.sha256((case + a).encode()).hexdigest())]
    provider = json.loads((PRIVATE / "repair-provider.json").read_bytes())
    require(datetime.fromisoformat(provider["quote"]["valid_until"]) > datetime.now(UTC),
            "FRESH_QUOTE_REQUIRED")
    settings = {"provider": provider, "jobs": jobs,
                "cases": {c["id"]: {"file_hashes": c["file_hashes"], "sha256": c["sha256"]}
                          for c in dataset}, "scope": "development_repair_core_pilot_only"}
    files = {"settings.json": json.dumps(settings, sort_keys=True).encode(),
             "pilot_controller.py": (ROOT / "eval/pilot_controller.py").read_bytes(),
             "eval/pilot_budget.py": (ROOT / "eval/pilot_budget.py").read_bytes(),
             "eval/__init__.py": b""}
    for case in dataset:
        files.update({"cases/" + case["id"] + "/" + n: raw for n, raw in case["files"].items()})
    hashes = {n: hashlib.sha256(raw).hexdigest() for n, raw in files.items()}
    revision = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    target = "/opt/proofflow-pilot/" + revision
    state = "/var/lib/proofflow-pilot-v1"
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as tar:
        for name, raw in files.items():
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(raw), 0o444
            tar.addfile(info, io.BytesIO(raw))
    summary = {"started_at": datetime.now(UTC).isoformat(), "revision": revision, "sources": hashes,
               "image": IMAGE, "settings": settings, "runs": [], "cap_micro_usd": 1200000,
               "source_scope": "disclosed development data, not held-out", "completed": False}

    def persist():
        record.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    with LiveSession() as live:
        require(live.sql("SELECT count(*)=1 AND bool_and(blocked) FROM pf_budget.accounts;",
                         "proofflow_budget") == b"t", "BUDGET_MUST_START_CLOSED")
        summary["credit"] = live.credit
        used = int(live.sql("SELECT reserved_micro FROM pf_product.repair_allocation;"))
        require(used + 1200000 <= 5000000, "DEVELOPMENT_ENVELOPE_EXHAUSTED")
        summary["previous_development_reserved_micro"] = used
        require(live.host("test -e " + state + " && echo present || echo absent") == b"absent",
                "PILOT_STATE_EXISTS_RECONCILE")
        persist()  # Persist all finite job IDs before any paid call or remote run.
        allocation = str(UUID(jobs[0]["run_id"]))
        live.sql("SET ROLE pf_product_provisioner; SELECT pf_product.reserve_evaluation('"
                 + allocation + "','" + revision + "',1200000);")
        summary["shared_development_allocation"] = allocation
        persist()
        live.host("install -d -m 0755 " + target)
        live.host("tar -xf - --no-same-owner -C " + target, archive.getvalue())
        for name, digest in hashes.items():
            require(live.host("sha256sum " + target + "/" + name).decode().split()[0] == digest,
                    "PILOT_SOURCE_CHANGED")
        live.host("install -d -o 10003 -g 10003 -m 0700 " + state + " " + state + "/budget")
        live.host("umask 077; cat > " + state + "/budget/plan.json",
                  json.dumps({"jobs": [j["run_id"] for j in jobs]}).encode())
        live.host("chown 10003:10003 " + state + "/budget/plan.json")
        # Independent one-shot cutoff survives this client disconnecting. Existing
        # project credit guard remains unchanged. The finite per-job book is primary.
        stop = ["/usr/bin/docker", "exec", "--user=70:70", "proofflow-budget", "psql", "-X",
                "-qAt", "-h", "/run/proofflow-budget", "-U", "postgres", "-d", "proofflow_budget",
                "-c", "UPDATE pf_budget.accounts SET blocked=true;"]
        live.host("systemd-run --quiet --on-active=40min --unit=proofflow-pilot-budget-stop "
                  + shlex.join(stop))
        try:
            live.sql("UPDATE pf_budget.accounts SET blocked=false;", "proofflow_budget")
            for job in jobs:
                argv = ["docker", "run", "--rm", "--pull=never",
                    "--name=proofflow-pilot-" + job["run_id"], "--label=proofflow.role=pilot-v1",
                    "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
                    "--user=10003:10003", "--group-add=10001", "--network=host", "--memory=512m",
                    "--memory-swap=512m", "--cpus=1", "--pids-limit=64", "--ulimit=core=0",
                    "--ulimit=nofile=128:128",
                    "--mount=type=bind,src=" + target + ",dst=/pilot,readonly",
                    "--mount=type=bind,src=" + state + ",dst=/var/lib/proofflow-pilot"]
                for src, dst in (("/run/proofflow-budget", "/run/proofflow-budget"),
                    ("/run/proofflow-verifier", "/run/proofflow-verifier"),
                    ("/etc/proofflow-repair/credentials", "/etc/proofflow-repair/credentials"),
                    ("/etc/proofflow-product-dispatcher/worker", "/etc/proofflow-product/worker")):
                    argv.append("--mount=type=bind,src=" + src + ",dst=" + dst + ",readonly")
                argv.extend(["sha256:" + IMAGE, "python", "/pilot/pilot_controller.py",
                             job["run_id"]])
                reply = live.admin.host("control", shlex.join(argv), timeout=330)
                (PRIVATE / "evidence" / ("pilot-" + job["run_id"] + ".stdout")).write_bytes(
                    reply.stdout)
                if reply.returncode:
                    (PRIVATE / "evidence" / ("pilot-" + job["run_id"] + ".stderr")).write_bytes(
                        reply.stderr)
                    raise RuntimeError("PILOT_RUN_UNCERTAIN_RECONCILE_NO_RETRY")
                result = json.loads(reply.stdout)
                summary["runs"].append(result)
                persist()
                print(json.dumps({"case": job["case"], "arm": job["arm"],
                                  "decision": result["decision"], "grade": result["grade"],
                                  "calls": len(result["calls"]), "ms": result["elapsed_ms"]}),
                      flush=True)
                require(not result.get("critical"), "CRITICAL_PILOT_GATE_FAILED")
            summary["completed"] = True
        finally:
            live.sql("UPDATE pf_budget.accounts SET blocked=true;", "proofflow_budget")
            summary["budget_closed"] = True
            live.host("systemctl stop proofflow-pilot-budget-stop.timer")
            summary["finished_at"] = datetime.now(UTC).isoformat()
            persist()


if __name__ == "__main__":
    main()
