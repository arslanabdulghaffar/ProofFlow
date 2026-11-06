"""Read-only final receipt collection and independent offline reconciliation.

No provider request, job replay, status edit, activation, PR, refund or settlement.
Candidate source and archives are read as bytes only, never imported/extracted.
"""

import base64
import hashlib
import json
import sys
import tarfile
from pathlib import Path, PurePosixPath
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from comparison_api import grade_export, save  # noqa: E402
from continue_comparison import frozen_files  # noqa: E402
from product_live_session import LiveSession, require  # noqa: E402
from run_comparison import RUNTIME, VERIFIER, closed  # noqa: E402
from vultr_phase1 import PRIVATE  # noqa: E402

from eval.comparison_cases import check_oracle  # noqa: E402
from eval.comparison_receipts import call, product_call, record  # noqa: E402
from eval.report import digest, summarize  # noqa: E402
from orchestrator.repair_evidence import bind_sources, classify  # noqa: E402
from orchestrator.repair_proposal import INSTRUCTION  # noqa: E402


def archive_bytes(path):
    require(path.stat().st_size <= 64 * 1024 * 1024, "COMPARISON_ARCHIVE_LIMIT")
    files = {}
    with tarfile.open(path, "r:") as archive:
        for index, member in enumerate(archive):
            require(
                index < 10000 and (member.isdir() or member.isfile()),
                "COMPARISON_ARCHIVE_TYPE",
            )
            path = PurePosixPath(member.name)
            require(
                not path.is_absolute()
                and ".." not in path.parts
                and path.parts[0] == "proofflow-comparison-v1",
                "COMPARISON_ARCHIVE_PATH",
            )
            if member.isdir():
                continue
            name = str(path.relative_to("proofflow-comparison-v1"))
            require(
                name not in files and 0 <= member.size <= 10 * 1024 * 1024,
                "COMPARISON_ARCHIVE_MEMBER",
            )
            files[name] = archive.extractfile(member).read()  # Never extract filesystem paths.
    return files


def audit_execution(job, summary, files, case):
    execution = UUID(summary["execution"])
    base = job["run_id"] + "/executions/" + execution.hex + "/"
    receipt = json.loads(files[base + "result.json"])
    intent = json.loads(files[base + "intent.json"])
    source = files[base + "pipeline.py.txt"]
    contract = files[base + "contract.json"]
    tx, cs = files[base + "transactions.csv"], files[base + "customers.csv"]
    require(
        intent["job"] == UUID(job["run_id"]).hex
        and intent["execution"] == execution.hex
        and intent["purpose"] == summary["purpose"]
        and contract == case["files"]["contract.json"],
        "COMPARISON_EXECUTION_SCOPE",
    )
    if summary["purpose"] in ("original", "candidate"):
        require(
            tx == case["files"]["transactions.csv"] and cs == case["files"]["customers.csv"],
            "COMPARISON_EXECUTION_DATA_CHANGED",
        )
    if summary["purpose"] == "original":
        require(source == case["files"]["pipeline.py.txt"], "COMPARISON_ORIGINAL_CHANGED")
    bind_sources(
        intent,
        source=source,
        contract=contract,
        transactions=tx,
        customers=cs,
        runtime=RUNTIME,
        verifier=VERIFIER,
        purpose=summary["purpose"],
    )
    verdict, _ = classify(receipt, intent, RUNTIME, VERIFIER)
    require(
        verdict == summary["decision"] and receipt["worker"]["cleanup"] == "confirmed",
        "COMPARISON_EXECUTION_VERDICT_CHANGED",
    )
    return {
        "purpose": summary["purpose"],
        "decision": verdict,
        "source_sha256": hashlib.sha256(source).hexdigest(),
        "execution": execution.hex,
        "manifest": intent["manifest_sha256"],
    }


def audit_controller(job, result, files, case):
    remote = files[job["run_id"] + "/result.json"]
    require(json.loads(remote) == result, "COMPARISON_REMOTE_RESULT_CHANGED")
    proof = [audit_execution(job, e, files, case) for e in result["executions"]]
    require(len({e["execution"] for e in proof}) == len(proof), "COMPARISON_EXECUTION_REUSED")
    if result["decision"] == "accepted":
        candidate = [e for e in proof if e["purpose"] == "candidate"][-1]
        require(
            candidate["source_sha256"] == result["candidate_sha256"], "COMPARISON_CANDIDATE_CHANGED"
        )
        if job["arm"] == "B":
            baseline = json.loads(files[job["run_id"] + "/baseline-acceptance.json"])
            require(
                baseline
                == {
                    "execution": candidate["execution"],
                    "manifest": candidate["manifest"],
                    "candidate_sha256": candidate["source_sha256"],
                },
                "COMPARISON_BASELINE_ACCEPTANCE_CHANGED",
            )
        if result["grade"] == "correct":
            final = proof[-3:]
            require(
                [e["purpose"] for e in final]
                == ["candidate", "canary_ownership", "canary_quarantine"]
                and all(e["source_sha256"] == candidate["source_sha256"] for e in final)
                and [e["decision"] for e in final[:2]] == ["match", "match"]
                and final[-1]["decision"] in ("match", "held"),
                "COMPARISON_FINAL_PROOF_MISSING",
            )
        elif result["grade"] == "incorrect":
            require(
                job["arm"] == "B"
                and any(
                    e["decision"] not in ("match", "held")
                    or (e["purpose"] == "candidate" and e["decision"] == "held")
                    for e in proof[proof.index(candidate) :]
                ),
                "COMPARISON_WRONG_GRADE_UNSUPPORTED",
            )
    elif result["decision"] in ("held", "clarification") and result["grade"] == "correct":
        oracle = check_oracle(case)
        require(
            oracle.get("blocking_occurrences", 0) > 0 or oracle.get("contract_rejected"),
            "COMPARISON_UNJUSTIFIED_ABSTENTION",
        )
    return proof


def lifecycle(root, jobs):
    """Require every dispatch/closure and normal product retirement, not a counter."""
    require(
        {p.name for p in root.glob("dispatch-*.json")}
        == {"dispatch-" + job["run_id"] + ".json" for job in jobs},
        "COMPARISON_DISPATCH_SET_CHANGED",
    )
    for job in jobs:
        identifier = job["run_id"]
        dispatch = json.loads((root / ("dispatch-" + identifier + ".json")).read_bytes())
        require(dispatch["job"] == job, "COMPARISON_DISPATCH_IDENTITY_CHANGED")
        require(
            json.loads((root / ("closed-" + identifier + ".json")).read_bytes())
            == {"admission": False, "inference": False},
            "COMPARISON_CLOSURE_UNCONFIRMED",
        )
        if job["arm"] == "A":
            folder = root / identifier
            result = json.loads((folder / "result.json").read_bytes())
            retired = json.loads((folder / "retirement-completed.json").read_bytes())
            require(
                retired["sql_completed"] is True and retired["workspace"] == result["workspace"],
                "COMPARISON_RETIREMENT_UNCONFIRMED",
            )


def main():
    root = PRIVATE / "evidence/final-comparison-v1"
    completed = json.loads((root / "completed.json").read_bytes())
    require(completed["jobs"] == 96, "COMPARISON_CAMPAIGN_NOT_FINISHED")
    require(not (root / "collection.json").exists(), "COMPARISON_COLLECTION_ALREADY_STARTED")
    freeze = json.loads((root / "freeze.json").read_bytes())
    frozen = frozen_files(root, freeze)
    settings = json.loads(frozen["settings.json"])
    with LiveSession() as live:
        closed(live)
        size = int(
            live.host("du -sb --exclude=captures /var/lib/proofflow-comparison-v1").split()[0]
        )
        require(size <= 60 * 1024 * 1024, "COMPARISON_RECEIPT_STORAGE_LIMIT")
        reply = live.admin.host(
            "control",
            "tar --exclude='*/captures' -cf - -C /var/lib proofflow-comparison-v1",
            timeout=120,
        )
        require(
            reply.returncode == 0 and len(reply.stdout) <= 64 * 1024 * 1024,
            "COMPARISON_RECEIPT_COLLECTION_FAILED",
        )
        archive = root / "remote-receipts.tar"
        with archive.open("xb") as output:
            output.write(reply.stdout)
        rows = json.loads(
            live.sql(
                "SELECT coalesce(json_agg(r),'[]'::json) FROM pf_budget.reservations r;",
                "proofflow_budget",
            )
        )
        save(root, "budget-readback.json", rows)
        save(
            root,
            "collection.json",
            {
                "credit": live.credit,
                "remote_bytes": len(reply.stdout),
                "remote_sha256": hashlib.sha256(reply.stdout).hexdigest(),
                "admission": False,
                "inference": False,
            },
        )
    audit(root, freeze, frozen, settings, archive, rows)


def audit(root, freeze, frozen, settings, archive, rows):
    require(settings["jobs"] == freeze["jobs"], "COMPARISON_FROZEN_JOBS_CHANGED")
    lifecycle(root, freeze["jobs"])
    remote = archive_bytes(archive)
    ledger = {r["id"]: r for r in rows}
    require(len(ledger) == len(rows), "COMPARISON_LEDGER_DUPLICATE")
    requests = {
        json.loads(raw)["request_id"]: json.loads(raw)
        for name, raw in remote.items()
        if name.startswith("budget/request-")
    }
    require(len(requests) <= 144, "COMPARISON_REQUEST_COUNT")
    request_names = [name for name in remote if name.startswith("budget/request-")]
    require(
        len(requests) == len(request_names)
        and set(request_names)
        == {"budget/request-" + UUID(identifier).hex + ".json" for identifier in requests},
        "COMPARISON_REQUEST_NAME_OR_DUPLICATE",
    )
    normalized, details = [], []
    seen = set()
    lookup = {}
    for entry in freeze["plan"]["cases"]:
        key = entry["id"]
        lookup[key] = {
            **entry,
            "oracle_summary": freeze["oracles"][key],
            "files": {
                name: frozen["cases/" + key + "/" + name]
                for name in settings["cases"][key]["file_hashes"]
            },
        }
    for index, job in enumerate(freeze["jobs"]):
        path = (
            root / job["run_id"] / "result.json"
            if job["arm"] == "A"
            else root / ("result-" + job["run_id"] + ".json")
        )
        raw = path.read_bytes()
        result = json.loads(raw)
        case, checked_calls, bindings, proofs = lookup[job["case"]], [], [], []
        corrected_cleanup = None
        if job["arm"] == "A":
            folder = path.parent
            if index == 3:
                recovery = json.loads((folder / "original-reconciled.json").read_bytes())
                require(
                    result["critical"]
                    and recovery["state"] == "CANCELLED"
                    and recovery["worker_receipt"]["cleanup"] == "confirmed",
                    "COMPARISON_INTERRUPTION_UNRECONCILED",
                )
                corrected_cleanup = "confirmed"
            elif result["decision"] == "accepted":
                executions = json.loads((folder / "repair-executions.json").read_bytes())
                export = json.loads((folder / "export.json").read_bytes())
                require(
                    grade_export(export, executions, case["files"], settings)
                    == result["candidate_sha256"],
                    "COMPARISON_API_GRADE_CHANGED",
                )
                proofs = [e["execution_id"] for e in executions]
            elif result["grade"] == "correct":
                oracle = check_oracle(case)
                require(
                    oracle.get("blocking_occurrences", 0) > 0 or oracle.get("contract_rejected"),
                    "COMPARISON_API_ABSTENTION_UNJUSTIFIED",
                )
            calls_path = folder / "repair-calls.json"
            if calls_path.exists():
                bindings = [product_call(row) for row in json.loads(calls_path.read_bytes())]
        else:
            proofs = audit_controller(job, result, remote, case)
            for request in requests.values():
                if request["job"] != job["run_id"]:
                    continue
                require(
                    request["campaign_sha256"] == settings["campaign_sha256"],
                    "COMPARISON_REQUEST_SCOPE",
                )
                text = json.loads(base64.b64decode(request["payload_base64"]))["messages"][1][
                    "content"
                ]
                require(
                    text.startswith(INSTRUCTION)
                    and set(json.loads(text[len(INSTRUCTION) :])["feedback"]) <= {"code"},
                    "COMPARISON_PROTECTED_FEEDBACK_LEAK",
                )
                response = remote.get(
                    "budget/response-" + UUID(request["request_id"]).hex + ".json"
                )
                bindings.append((request, None if response is None else json.loads(response)))
        for request, response in bindings:
            identity = request["request_id"]
            require(identity not in seen, "COMPARISON_REQUEST_REUSED")
            seen.add(identity)
            checked_calls.append(
                call(request, response, ledger.get(identity), account_id=settings["account_id"])
            )
        if result["decision"] == "accepted":
            require(
                result["candidate_sha256"]
                in (
                    {settings["deterministic_sha256"]}
                    if job["arm"] == "D"
                    else {c["candidate_sha256"] for c in checked_calls if c["candidate_sha256"]}
                ),
                "COMPARISON_CANDIDATE_NOT_FROM_DECLARED_SOURCE",
            )
        receipt = digest(
            {
                "result_sha256": hashlib.sha256(raw).hexdigest(),
                "calls": checked_calls,
                "proofs": proofs,
            }
        )
        normalized.append(
            record(
                freeze["plan"],
                job,
                result,
                checked_calls,
                receipt,
                reconciled_cleanup=corrected_cleanup,
            )
        )
        details.append(
            {
                "run_id": job["run_id"],
                "calls": checked_calls,
                "proofs": len(proofs),
                "cleanup_reconciled": corrected_cleanup is not None,
            }
        )
    require(set(requests) <= seen, "COMPARISON_ORPHAN_REQUEST")
    report = summarize(freeze["plan"], normalized)
    report.update(
        evidence_validation="ACTUAL_PRIVATE_RECEIPTS_RECONCILED",
        held_out_claim="PROSPECTIVE_SYNTHETIC_SHARED_TEMPLATE_NO_HUMAN_ORACLE_REVIEW",
        source_amendment="polling-only after first4 dispatches; first A interrupted and preserved",
        actual_confirmed_http_calls=sum(
            c["confirmed_http"] for row in details for c in row["calls"]
        ),
    )
    save(root, "normalized-records.json", normalized)
    save(root, "receipt-audit.json", details)
    save(root, "report.json", report)
    print(
        json.dumps(
            {
                "jobs": len(normalized),
                "confirmed_http_calls": report["actual_confirmed_http_calls"],
                "reserved_micro": sum(r["reserved_micro_usd"] for r in normalized),
                "report": "private_reconciled_no_publication",
            }
        )
    )


if __name__ == "__main__":
    main()
