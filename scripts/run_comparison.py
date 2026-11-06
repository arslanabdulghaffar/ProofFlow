"""One finite prospectively frozen synthetic comparison; no activation/publication.

Existing campaign state is a reconciliation boundary, never automatic replay.
"""

import hashlib
import io
import json
import secrets
import shlex
import subprocess
import sys
import tarfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from comparison_api import retire, run, save  # noqa: E402
from install_product_services import IMAGE  # noqa: E402
from product_live_session import LiveSession, require  # noqa: E402
from vultr_phase1 import PRIVATE, ROOT  # noqa: E402

from eval.comparison_cases import cases, check_oracle  # noqa: E402
from eval.report import digest, manifest  # noqa: E402

RUNTIME = "c826cf6662bcb4495cb744e34b9944044ade193fd870ca5a7bef140d3150dd78"
VERIFIER = "0290920d63d9b55108c83d300922f5af84608147495f340e86025fc0e599e63b"
QUOTE_POLICY = {
    "model": "qwen3.8-flash-next",
    "input_micro_usd_per_million": 100000,
    "output_micro_usd_per_million": 200000,
    "maximum_quote_seconds": 3600,
    "minimum_remaining_seconds_before_job": 600,
    "same_account_required": True,
    "refresh": "official_catalogue_closed_idle_same_account_model_rates_only",
}
SOURCES = (
    "eval/comparison_controller.py",
    "eval/comparison_journal.py",
    "eval/comparison_setup.py",
    "eval/comparison_cases.py",
    "eval/report.py",
    "scripts/comparison_api.py",
    "scripts/run_comparison.py",
    "orchestrator/repair_proposal.py",
    "orchestrator/repair_evidence.py",
    "orchestrator/verification_run.py",
    "verifier/protocol.py",
    "verifier/reference.py",
    "scripts/refresh_product_quote.py",
    "scripts/install_provider_quote.py",
    "scripts/deploy_product_services.py",
    "scripts/install_product_services.py",
    "scripts/product_live_session.py",
    "scripts/vultr_credit_guard.py",
    "scripts/vultr_phase1.py",
    "schemas/merchant_revenue_v1.1.schema.json",
    "tests/fixtures/phase2/canary_correct.py.txt",
)


def refresh():
    config = json.loads((PRIVATE / "repair-provider.json").read_bytes())
    if datetime.fromisoformat(config["quote"]["valid_until"]) <= datetime.now(UTC) + timedelta(
        minutes=10
    ):
        for name in ("refresh_product_quote.py", "deploy_product_services.py"):
            reply = subprocess.run(  # noqa: S603 - fixed reviewed quote/deployment helpers
                [sys.executable, str(ROOT / "scripts" / name)],
                capture_output=True,
                timeout=240,
                check=False,
            )
            if reply.returncode:
                evidence = PRIVATE / "evidence" / ("comparison-quote-failure-" + uuid4().hex)
                evidence.with_suffix(".stdout").write_bytes(reply.stdout)
                evidence.with_suffix(".stderr").write_bytes(reply.stderr)
            require(reply.returncode == 0, "COMPARISON_QUOTE_REFRESH_FAILED_RECONCILE")
        config = json.loads((PRIVATE / "repair-provider.json").read_bytes())
    require(
        all(
            config["quote"][k] == QUOTE_POLICY[k]
            for k in ("model", "input_micro_usd_per_million", "output_micro_usd_per_million")
        ),
        "COMPARISON_QUOTE_POLICY_CHANGED",
    )
    require(
        datetime.fromisoformat(config["quote"]["valid_until"])
        > datetime.now(UTC) + timedelta(minutes=10),
        "COMPARISON_QUOTE_TOO_SHORT",
    )
    return config


def container(target, state, *, job=None):
    argv = [
        "docker",
        "run",
        "--rm",
        "--pull=never",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--user=10003:10003",
        "--group-add=10001",
        "--network=host" if job else "--network=none",
        "--memory=512m",
        "--memory-swap=512m",
        "--cpus=1",
        "--pids-limit=64",
        "--ulimit=core=0",
        "--ulimit=nofile=128:128",
        "--mount=type=bind,src=" + target + ",dst=/comparison,readonly",
        "--mount=type=bind,src=" + state + ",dst=/var/lib/proofflow-comparison",
    ]
    if job:
        argv += [
            "--name=proofflow-comparison-" + job["run_id"],
            "--label=proofflow.role=comparison",
        ]
        mounts = [
            ("/run/proofflow-verifier", "/run/proofflow-verifier"),
            ("/etc/proofflow-product-dispatcher/worker", "/etc/proofflow-product/worker"),
        ]
        if job["arm"] != "D":
            mounts += [
                (p, p)
                for p in (
                    "/run/proofflow-budget",
                    "/etc/proofflow-repair/credentials",
                    "/etc/proofflow-repair/config.json",
                )
            ]
        for source, destination in mounts:
            argv.append("--mount=type=bind,src=" + source + ",dst=" + destination + ",readonly")
    argv += [
        "sha256:" + IMAGE,
        "python",
        "/comparison/" + ("comparison_controller.py" if job else "comparison_setup.py"),
    ]
    if job:
        argv.append(job["run_id"])
    return argv


def closed(live):
    require(
        live.sql(
            "SELECT count(*)=1 AND bool_and(blocked) FROM pf_budget.accounts;", "proofflow_budget"
        )
        == b"t",
        "COMPARISON_BUDGET_NOT_CLOSED",
    )
    require(
        live.sql(
            "SELECT count(*) FROM pf_product.jobs WHERE state NOT IN "
            "('NEEDS_REVIEW','FAILED_INFRA','CANCELLED');"
        )
        == b"0",
        "COMPARISON_ORIGINAL_QUEUE_NOT_IDLE",
    )
    require(
        live.sql(
            "SELECT count(*) FROM pf_product.pr_intents WHERE lease_owner IS NOT NULL "
            "OR state IN ('BRANCH_PENDING','COMMIT_PENDING','PR_PENDING');"
        )
        == b"0",
        "COMPARISON_EXTERNAL_QUEUE_NOT_IDLE",
    )
    require(
        live.host(
            "systemctl is-active proofflow-product-api.service "
            "proofflow-product-dispatcher.service proofflow-product-retention.timer"
        )
        == b"active\nactive\nactive",
        "COMPARISON_SERVICES_NOT_ACTIVE",
    )
    require(
        live.policy["runtime_sha256"] == RUNTIME and live.policy["verifier_sha256"] == VERIFIER,
        "COMPARISON_POLICY_CHANGED",
    )
    require(
        live.host("docker inspect --format='{{.Image}}' proofflow-product-dispatcher")
        == ("sha256:" + IMAGE).encode(),
        "COMPARISON_PRODUCT_IMAGE_CHANGED",
    )
    require(
        datetime.fromisoformat(live.credit["review_due_at"])
        > datetime.now(UTC) + timedelta(minutes=15),
        "COMPARISON_FUNDED_REVIEW_TOO_CLOSE",
    )


def main():
    require(sys.argv[1:] == [], "COMPARISON_ARGUMENTS_FORBIDDEN")
    root = PRIVATE / "evidence/final-comparison-v1"
    require(not root.exists(), "COMPARISON_ALREADY_STARTED_RECONCILE_NO_RETRY")
    status = subprocess.run(
        ["C:/Program Files/Git/cmd/git.exe", "status", "--porcelain"],
        cwd=ROOT,
        capture_output=True,
        check=True,
        timeout=15,
    )  # noqa: S603
    require(not status.stdout, "COMPARISON_COMMIT_SOURCES_BEFORE_FREEZE")
    config = refresh()
    dataset = cases(secrets.token_hex(32))
    for case in dataset:
        check_oracle(case)  # Data only; no source execution, no final model observation.
    hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCES}
    freeze = {
        "source": digest({"files": hashes, "product_image": IMAGE}),
        "prompts": hashes["orchestrator/repair_proposal.py"],
        "runtime": digest({"worker": RUNTIME, "verifier": VERIFIER, "product_image": IMAGE}),
        "schemas": hashes["schemas/merchant_revenue_v1.1.schema.json"],
        "grader": digest(
            {
                k: v
                for k, v in hashes.items()
                if k.startswith("verifier/")
                or k in ("scripts/comparison_api.py", "orchestrator/repair_evidence.py")
            }
        ),
        "model_quote": digest(QUOTE_POLICY),
    }
    plan = manifest(
        cases=[{k: c[k] for k in ("id", "family", "kind", "sha256")} for c in dataset],
        freeze=freeze,
        stage="final",
    )
    jobs = [{**job, "run_id": str(uuid4())} for job in plan["jobs"]]
    settings = {
        "jobs": jobs,
        "campaign_sha256": digest(plan),
        "account_id": config["account_id"],
        "runtime_sha256": RUNTIME,
        "verifier_sha256": VERIFIER,
        "deterministic_sha256": hashes["tests/fixtures/phase2/canary_correct.py.txt"],
        "cases": {
            c["id"]: {"file_hashes": c["file_hashes"], "sha256": c["sha256"]} for c in dataset
        },
    }
    files = {
        "settings.json": json.dumps(settings, sort_keys=True).encode(),
        "eval/__init__.py": b"",
        "comparison_controller.py": (ROOT / "eval/comparison_controller.py").read_bytes(),
        "comparison_setup.py": (ROOT / "eval/comparison_setup.py").read_bytes(),
        "eval/comparison_journal.py": (ROOT / "eval/comparison_journal.py").read_bytes(),
        "deterministic.py.txt": (ROOT / "tests/fixtures/phase2/canary_correct.py.txt").read_bytes(),
    }
    for case in dataset:
        files.update(
            {"cases/" + case["id"] + "/" + name: raw for name, raw in case["files"].items()}
        )
    shipped = {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}
    revision = digest(shipped)
    target, state = "/opt/proofflow-comparison/" + revision, "/var/lib/proofflow-comparison-v1"
    root.mkdir(mode=0o700)
    save(
        root,
        "freeze.json",
        {
            "plan": plan,
            "jobs": jobs,
            "sources": hashes,
            "shipped": shipped,
            "revision": revision,
            "quote_policy": QUOTE_POLICY,
            "initial_quote": config["quote"],
            "oracles": {c["id"]: c["oracle_summary"] for c in dataset},
            "final_envelope_micro": 12000000,
            "forecast_micro": 7200000,
            "A_cap_micro": 2400000,
            "BC_cap_micro": 4800000,
            "scope": "prospective synthetic; shared fault/template; no human oracle review",
        },
    )
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as output:
        for name, raw in files.items():
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(raw), 0o444
            output.addfile(info, io.BytesIO(raw))
    (root / "frozen-sources.tar").write_bytes(archive.getvalue())
    with LiveSession() as live:
        closed(live)
        require(
            live.host("test -e " + state + " && echo present || echo absent") == b"absent",
            "COMPARISON_REMOTE_STATE_EXISTS",
        )
        # Actual worst-case A calls remain inside the unchanged shared product allocation.
        used = int(live.sql("SELECT reserved_micro FROM pf_product.repair_allocation;"))
        require(used + 24 * 3 * 27853 <= 5000000, "COMPARISON_PRODUCT_ENVELOPE_EXHAUSTED")
        require(
            int(live.host("df --output=avail -B1 /var/lib | tail -n 1")) >= 4 * 1024**3,
            "COMPARISON_DISK_RESERVE_UNAVAILABLE",
        )
        save(root, "launch-precheck.json", {"credit": live.credit, "development_reserved": used})
        live.host("install -d -m 0755 " + target)
        live.host("tar -xf - --no-same-owner -C " + target, archive.getvalue())
        for name, expected in shipped.items():
            require(
                live.host("sha256sum " + target + "/" + name).decode().split()[0] == expected,
                "COMPARISON_SHIPPED_SOURCE_CHANGED",
            )
        live.host("install -d -o 10003 -g 10003 -m 0700 " + state)
        require(
            live.host(shlex.join(container(target, state))) == b"COMPARISON_BOOK_INITIALIZED",
            "COMPARISON_BOOK_SETUP_UNCERTAIN",
        )
    dispatch(root, jobs, {c["id"]: c for c in dataset}, target, state, settings, hashes)


def dispatch(root, jobs, lookup, target, state, settings, hashes, *, start=0):
    for index, job in enumerate(jobs[start:], start):
        require(
            all(
                hashlib.sha256((ROOT / n).read_bytes()).hexdigest() == v for n, v in hashes.items()
            ),
            "COMPARISON_LOCAL_SOURCE_CHANGED",
        )
        current = refresh()
        require(current["account_id"] == settings["account_id"], "COMPARISON_ACCOUNT_CHANGED")
        with LiveSession() as live:
            closed(live)
            require(
                json.loads(live.host("cat /etc/proofflow-repair/config.json")) == current,
                "COMPARISON_INSTALLED_QUOTE_CHANGED",
            )
            save(
                root,
                "dispatch-" + job["run_id"] + ".json",
                {"job": job, "quote": current["quote"], "credit": live.credit},
            )
            unit = "proofflow-comparison-stop-" + job["run_id"]
            stop = [
                "/usr/bin/docker",
                "exec",
                "--user=70:70",
                "proofflow-budget",
                "psql",
                "-X",
                "-qAt",
                "-h",
                "/run/proofflow-budget",
                "-U",
                "postgres",
                "-d",
                "proofflow_budget",
                "-c",
                "UPDATE pf_budget.accounts SET blocked=true;",
            ]
            live.host(
                "systemd-run --quiet --on-active=12min --unit=" + unit + " " + shlex.join(stop)
            )
            try:
                if job["arm"] != "D":
                    live.sql("UPDATE pf_budget.accounts SET blocked=false;", "proofflow_budget")
                if job["arm"] == "A":
                    live.opened = True
                    live.admission(True)
                    result = run(live, job, lookup[job["case"]], root)
                    require(not result.get("critical"), "COMPARISON_CRITICAL_API_FAILURE")
                    retire(live, result, root)
                else:
                    name = "proofflow-comparison-" + job["run_id"]
                    live.host(
                        "systemd-run --quiet --on-active=8min --unit="
                        + unit
                        + "-container "
                        + shlex.join(["/usr/bin/docker", "stop", "--time=5", name])
                    )
                    reply = live.admin.host(
                        "control", shlex.join(container(target, state, job=job)), timeout=490
                    )
                    (root / ("stdout-" + job["run_id"] + ".json")).write_bytes(reply.stdout)
                    if reply.returncode:
                        (root / ("stderr-" + job["run_id"] + ".txt")).write_bytes(reply.stderr)
                    require(reply.returncode == 0, "COMPARISON_RUN_UNCERTAIN_RECONCILE")
                    result = json.loads(reply.stdout)
                    save(root, "result-" + job["run_id"] + ".json", result)
                    require(not result.get("critical"), "COMPARISON_CRITICAL_INFRASTRUCTURE")
                    live.host("systemctl stop " + unit + "-container.timer")
                print(
                    json.dumps(
                        {
                            "completed_jobs": index + 1,
                            "total_jobs": len(jobs),
                            "case": job["case"],
                            "arm": job["arm"],
                            "decision": result["decision"],
                            "grade": result["grade"],
                            "prepared_calls": len(result["calls"]),
                        }
                    ),
                    flush=True,
                )
            finally:
                live.sql("UPDATE pf_budget.accounts SET blocked=true;", "proofflow_budget")
                if live.opened:
                    live.admission(False)
                save(
                    root,
                    "closed-" + job["run_id"] + ".json",
                    {"admission": False, "inference": False},
                )
                live.host("systemctl stop " + unit + ".timer")
    save(
        root,
        "completed.json",
        {
            "jobs": len(jobs),
            "completed_at": datetime.now(UTC).isoformat(),
            "receipt_reconciliation": "REQUIRED",
        },
    )


if __name__ == "__main__":
    main()
