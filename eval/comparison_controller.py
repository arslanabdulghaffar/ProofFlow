"""Bounded B/C/D comparison. Candidate source NEVER executes in this process.

C uses production repair prompts/checks with verdict-only feedback; B accepts a
clean exit before independent grading. D runs a fixed rebuild on the worker.
A uses the real API separately. No arm activates code or creates an external PR.
"""

import asyncio
import hashlib
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

sys.path.insert(0, "/comparison")
sys.path.append("/app")

from eval.comparison_journal import ComparisonJournal  # noqa: E402
from orchestrator.budget_store import BudgetConnection  # noqa: E402
from orchestrator.probe_plan import RateQuote  # noqa: E402
from orchestrator.provider_setup import load_provider_secrets  # noqa: E402
from orchestrator.repair_evidence import bind_sources, classify  # noqa: E402
from orchestrator.repair_proposal import (  # noqa: E402
    COMPLETION_TOKENS,
    INTERFACE,
    PROMPT_TOKEN_RESERVE,
    build_prompt,
    parse_proposal,
)
from orchestrator.repair_provider import RepairBudget, prepare_repair_plan  # noqa: E402
from orchestrator.verification_run import VerificationRun  # noqa: E402
from orchestrator.verifier_client import VerifierClient  # noqa: E402
from orchestrator.vultr_probe import _run_prepared  # noqa: E402
from orchestrator.worker_client import WorkerClient  # noqa: E402
from verifier.protocol import decode, encode  # noqa: E402
from worker.protocol import runtime_identity_digest  # noqa: E402
from worker.wire import tls_context  # noqa: E402


def feedback_for(arm, feedback, execution_ok):
    if arm == "B":
        return {"code": "EXECUTION_EXIT_ZERO" if execution_ok else "CANDIDATE_EXECUTION_FAILED"}
    return {"code": feedback.get("code", "CONTRACT_MISMATCH")}


def baseline_exit_ok(checked, intent, runtime):
    """B accepts only an authenticated, source-bound, cleaned, collected zero exit.

    Output semantics are deliberately excluded from this baseline policy.
    """
    worker = checked["worker"]
    if (
        checked.get("intent") != intent
        or worker.get("cleanup") != "confirmed"
        or any(
            worker.get(k) != intent[v]
            for k, v in (
                ("execution", "execution"),
                ("job", "job"),
                ("generation", "generation"),
                ("manifest", "manifest_sha256"),
            )
        )
        or runtime_identity_digest(worker.get("runtime", {})) != runtime
    ):
        raise RuntimeError("COMPARISON_WORKER_BINDING")
    return (
        worker.get("outcome") == "exited"
        and worker.get("collected") is True
        and type(worker.get("runtime_client_exit_code")) is int
        and worker["runtime_client_exit_code"] == 0
        and worker.get("unit_result") == "success"
    )


async def run(job, settings, root):
    started = time.monotonic()
    if job["arm"] not in ("B", "C", "D"):
        raise RuntimeError("COMPARISON_ARM_INVALID")
    folder = root / job["run_id"]
    folder.mkdir(mode=0o700)  # Existing/uncertain runs are never silently retried.
    persist(folder / "intent.json", job)
    private = Path("/etc/proofflow-product/worker")
    config = json.loads((private / "worker.json").read_bytes())
    if (
        config["runtime_sha256"] != settings["runtime_sha256"]
        or config["verifier_sha256"] != settings["verifier_sha256"]
    ):
        raise RuntimeError("COMPARISON_RUNTIME_CHANGED")
    worker = WorkerClient(
        config["worker_address"],
        tls_context(
            private / "ca.pem", private / "controller.pem", private / "controller.key", server=False
        ),
        config["worker_certificate_sha256"],
        config["runtime_sha256"],
    )
    journal = folder / "executions"
    journal.mkdir(mode=0o700)
    pending = {}

    def captured(request, worker_receipt):
        if job["arm"] != "B" or pending.get("purpose") != "candidate":
            return
        if (
            request.execution_id != pending["execution"]
            or request.job_id != UUID(job["run_id"])
            or request.generation != pending["generation"]
            or hashlib.sha256(request.pipeline).hexdigest() != pending["source_sha256"]
        ):
            raise RuntimeError("COMPARISON_CAPTURE_BINDING")
        intent = {
            "execution": request.execution_id.hex,
            "job": request.job_id.hex,
            "generation": request.generation,
            "manifest_sha256": request.manifest_hash(),
        }
        if not baseline_exit_ok(
            {"intent": intent, "worker": worker_receipt}, intent, config["runtime_sha256"]
        ):
            raise RuntimeError("COMPARISON_CAPTURE_NOT_ELIGIBLE")
        result.update(decision="accepted", baseline_accepted=True, cleanup="confirmed")
        persist(
            folder / "baseline-acceptance.json",
            {
                "execution": intent["execution"],
                "manifest": intent["manifest_sha256"],
                "candidate_sha256": pending["source_sha256"],
            },
        )

    runner = VerificationRun(
        worker,
        Path("/unused-admin-image"),
        config["verifier_sha256"],
        journal,
        verifier=VerifierClient(config["verifier_sha256"]),
        after_capture=captured,
    )
    files = {}
    case = settings["cases"][job["case"]]
    for name, digest in case["file_hashes"].items():
        raw = (Path("/comparison/cases") / job["case"] / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise RuntimeError("COMPARISON_SOURCE_CHANGED")
        files[name] = raw
    contract = files["contract.json"]
    txs, customers = files["transactions.csv"], files["customers.csv"]
    result = {
        **job,
        "decision": "failed",
        "grade": "unknown",
        "cleanup": "no_execution",
        "calls": [],
        "executions": [],
        "started_at": datetime.now(UTC).isoformat(),
    }

    async def execute(source, transactions, lookup, purpose):
        result["stage"] = "execution"
        execution, generation = uuid4(), len(result["executions"]) + 1
        pending.update(
            execution=execution,
            generation=generation,
            purpose=purpose,
            source_sha256=hashlib.sha256(source).hexdigest(),
        )
        checked = await asyncio.to_thread(
            runner.execute,
            execution=execution,
            job=UUID(job["run_id"]),
            generation=generation,
            pipeline=source,
            contract=contract,
            transactions=transactions,
            customers=lookup,
            purpose=purpose,
        )
        intent = checked["intent"]
        bind_sources(
            intent,
            source=source,
            contract=contract,
            transactions=transactions,
            customers=lookup,
            runtime=config["runtime_sha256"],
            verifier=config["verifier_sha256"],
            purpose=purpose,
        )
        ok = baseline_exit_ok(checked, intent, config["runtime_sha256"])
        decision, feedback = classify(
            checked, intent, config["runtime_sha256"], config["verifier_sha256"]
        )
        result["executions"].append(
            {
                "execution": intent["execution"],
                "purpose": purpose,
                "manifest": intent["manifest_sha256"],
                "decision": decision,
                "cleanup": checked["worker"]["cleanup"],
                "verifier_report": (checked.get("semantic") or {}).get("report_sha256"),
            }
        )
        result["cleanup"] = "confirmed"
        if checked["worker"]["outcome"] == "infrastructure_failure":
            raise RuntimeError("CRITICAL_WORKER_FAILURE")
        return decision, feedback, ok, checked

    try:
        result["stage"] = "source"
        source = await asyncio.to_thread(
            runner.bounded,
            {
                "operation": "source",
                "contract": encode(contract),
                "transactions": encode(txs),
                "customers": encode(customers),
            },
        )
        if source["report"]["status"] != "processed":
            if source["report"].get("code") != "UNKNOWN_UNIT":
                raise RuntimeError("COMPARISON_SOURCE_UNEXPECTED_REJECTION")
            result.update(
                decision="clarification", grade="correct", intake_rejection="UNKNOWN_UNIT"
            )
            return result
        if job["arm"] == "D":
            if source["report"]["result"]["blocking_occurrences"] > 0:
                result.update(decision="held", grade="correct")
                return result
            rebuilt = Path("/comparison/deterministic.py.txt").read_bytes()
            if hashlib.sha256(rebuilt).hexdigest() != settings["deterministic_sha256"]:
                raise RuntimeError("COMPARISON_DETERMINISTIC_SOURCE_CHANGED")
            decision, _, _, _ = await execute(rebuilt, txs, customers, "candidate")
            passed = decision == "match"
            if passed:
                for check in ("ownership", "quarantine"):
                    result["stage"] = "canary"
                    canary = await asyncio.to_thread(runner.canary, contract, check)
                    data = canary["report"]["result"]
                    outcome, _, _, _ = await execute(
                        rebuilt,
                        decode(data["transactions_csv"], 5242880),
                        decode(data["customers_csv"], 5242880),
                        "canary_" + check,
                    )
                    if outcome not in (("match", "held") if check == "quarantine" else ("match",)):
                        passed = False
                        break
            result.update(
                decision="accepted" if passed else "failed",
                grade="correct" if passed else "incorrect",
                candidate_sha256=hashlib.sha256(rebuilt).hexdigest(),
            )
            return result
        original, feedback, ok, checked = await execute(
            files["pipeline.py.txt"], txs, customers, "original"
        )
        result["original_decision"] = original
        if job["arm"] == "C" and source["report"]["result"]["blocking_occurrences"] > 0:
            result.update(decision="held", grade="correct")
            return result
        if checked.get("semantic") and checked["semantic"]["report"]["status"] == "processed":
            feedback = {**checked["semantic"]["report"]["result"], "code": "CONTRACT_MISMATCH"}
        else:
            feedback = {"code": "ORIGINAL_EXECUTION_FAILED", "output_verified": False}
        repair_started = time.monotonic()
        result["stage"] = "provider_setup"
        provider = load_provider_secrets("/etc/proofflow-repair/credentials")
        provider_config = json.loads(Path("/etc/proofflow-repair/config.json").read_bytes())
        if provider_config["account_id"] != settings["account_id"]:
            raise RuntimeError("COMPARISON_ACCOUNT_CHANGED")
        quote_data = dict(provider_config["quote"])
        if (
            quote_data["model"] != "qwen3.8-flash-next"
            or quote_data["input_micro_usd_per_million"] != 100000
            or quote_data["output_micro_usd_per_million"] != 200000
        ):
            raise RuntimeError("COMPARISON_RATE_CHANGED")
        result["quote"] = dict(quote_data)
        for field in ("observed_at", "valid_until"):
            quote_data[field] = datetime.fromisoformat(quote_data[field])
        quote = RateQuote(**quote_data)
        budget = RepairBudget(
            BudgetConnection(provider.database_password), UUID(settings["account_id"])
        )
        history = []
        for attempt in range(1, 4):
            if time.monotonic() - repair_started > 235:
                result["decision"] = "timeout"
                break
            prompt = build_prompt(
                pipeline=files["pipeline.py.txt"],
                contract=contract,
                interface=INTERFACE,
                previous=history,
                feedback=feedback_for(job["arm"], feedback, ok),
            )
            plan = prepare_repair_plan(prompt, quote, datetime.now(UTC))
            request = uuid4()
            call = {
                "request": str(request),
                "reserved_micro_usd": plan.reserve_micro_usd,
                "estimated_micro_usd": None,
                "input_tokens": None,
                "output_tokens": None,
            }
            result["calls"].append(call)
            result["stage"] = "provider"
            response = await _run_prepared(
                budget=budget,
                request_id=request,
                plan=plan,
                quote=quote,
                max_completion_tokens=COMPLETION_TOKENS,
                api_key=provider.vultr_api_key,
                journal=ComparisonJournal(
                    root / "budget", job["run_id"], settings["campaign_sha256"]
                ),
            )
            call["response_sha256"] = response.response_sha256
            if response.usage is None or response.usage.prompt_tokens > PROMPT_TOKEN_RESERVE:
                raise RuntimeError("COMPARISON_USAGE_UNKNOWN")
            usage = response.usage
            call.update(
                input_tokens=usage.prompt_tokens,
                output_tokens=usage.completion_tokens,
                estimated_micro_usd=(
                    usage.prompt_tokens * quote.input_micro_usd_per_million
                    + usage.completion_tokens * quote.output_micro_usd_per_million
                    + 999999
                )
                // 1000000,
            )
            try:
                proposal = parse_proposal(response.content_json)
            except Exception:
                feedback, ok = {"code": "INVALID_PROPOSAL"}, False
                history.append(
                    {"attempt": attempt, "code": "INVALID_PROPOSAL", "candidate_sha256": None}
                )
                continue
            if proposal.kind == "needs_clarification":
                result["decision"] = "clarification"
                # This dataset has explicit hold rules; no automatic oracle approval
                # of model-authored questions. Human question review remains unknown.
                break
            if time.monotonic() - repair_started > 165:
                result["decision"] = "timeout"
                break
            decision, feedback, ok, checked = await execute(
                proposal.source, txs, customers, "candidate"
            )
            result["candidate_sha256"] = proposal.sha256
            accepted = ok if job["arm"] == "B" else decision == "match"
            if decision == "held" and job["arm"] != "B":
                result.update(decision="held", grade="correct")
                break
            if accepted:
                # B's acceptance is fixed before seeing the protected final grade.
                if job["arm"] == "B":
                    result["decision"] = "accepted"
                    result["baseline_accepted"] = True
                passed = decision == "match"
                if passed:
                    for check in ("ownership", "quarantine"):
                        if time.monotonic() - repair_started > 165:
                            result.update(
                                decision="accepted" if job["arm"] == "B" else "timeout",
                                grade="unknown",
                                grading_timeout=True,
                            )
                            return result
                        result["stage"] = "canary"
                        canary = await asyncio.to_thread(runner.canary, contract, check)
                        data = canary["report"]["result"]
                        outcome, feedback, _, _ = await execute(
                            proposal.source,
                            decode(data["transactions_csv"], 5242880),
                            decode(data["customers_csv"], 5242880),
                            "canary_" + check,
                        )
                        if outcome not in (
                            ("match", "held") if check == "quarantine" else ("match",)
                        ):
                            passed = False
                            break
                result["grade"] = "correct" if passed else "incorrect"
                if job["arm"] == "B" or passed:
                    result["decision"] = "accepted"
                    break
                result["decision"] = "failed"
            history.append(
                {
                    "attempt": attempt,
                    "code": feedback.get("code", "REJECTED"),
                    "candidate_sha256": proposal.sha256,
                }
            )
    except Exception as error:
        result["error_type"] = type(error).__name__  # Never raw provider/secret/exception text.
        result["decision"] = "accepted" if result.get("baseline_accepted") else "failed"
        result["grade"] = "unknown"
        result["critical"] = result.get("stage") in ("source", "execution", "canary")
        if result["critical"]:
            result["cleanup"] = "unknown"
    finally:
        result["elapsed_ms"] = round((time.monotonic() - started) * 1000)
        persist(folder / "result.json", result)
    return result


def persist(path, value):
    raw = json.dumps(value, sort_keys=True).encode()
    with path.open("xb") as output:
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())
    fd = os.open(path.parent, os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


if __name__ == "__main__":
    os.umask(0o077)
    settings = json.loads(Path("/comparison/settings.json").read_bytes())
    job = next(j for j in settings["jobs"] if j["run_id"] == str(UUID(sys.argv[1])))
    print(
        json.dumps(asyncio.run(run(job, settings, Path("/var/lib/proofflow-comparison")))),
        flush=True,
    )
