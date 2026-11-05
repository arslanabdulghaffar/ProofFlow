"""Fixed private development pilot. Candidate source is NEVER executed in this process.

A/C use production repair prompts, independent checks and protected canaries.
B accepts exit-zero execution, then gets the same separate protected grading.
This evaluates the repair core, not API/queue/approval UX or held-out quality.
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

sys.path.insert(0, "/pilot")
sys.path.append("/app")

from eval.pilot_budget import PilotJournal  # noqa: E402
from orchestrator.budget_store import BudgetConnection  # noqa: E402
from orchestrator.probe_journal import ProbeJournal  # noqa: E402
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
from verifier.protocol import decode  # noqa: E402
from worker.wire import tls_context  # noqa: E402


def feedback_for(arm, feedback, execution_ok):
    if arm == "A":
        return feedback
    if arm == "B":
        return {"code": "EXECUTION_EXIT_ZERO" if execution_ok else "CANDIDATE_EXECUTION_FAILED"}
    return {"code": feedback.get("code", "CONTRACT_MISMATCH")}


async def run(job, settings, root):
    started = time.monotonic()
    folder = root / job["run_id"]
    folder.mkdir(mode=0o700)  # Existing/uncertain runs are never silently retried.
    (folder / "intent.json").write_text(json.dumps(job, sort_keys=True))
    private = Path("/etc/proofflow-product/worker")
    config = json.loads((private / "worker.json").read_bytes())
    worker = WorkerClient(config["worker_address"], tls_context(
        private / "ca.pem", private / "controller.pem", private / "controller.key", server=False),
        config["worker_certificate_sha256"], config["runtime_sha256"])
    journal = folder / "executions"
    journal.mkdir(mode=0o700)
    runner = VerificationRun(worker, Path("/unused-admin-image"), config["verifier_sha256"],
                             journal,
                             verifier=VerifierClient(config["verifier_sha256"]))
    files = {}
    case = settings["cases"][job["case"]]
    for name, digest in case["file_hashes"].items():
        raw = (Path("/pilot/cases") / job["case"] / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise RuntimeError("PILOT_SOURCE_CHANGED")
        files[name] = raw
    contract = files["contract.json"]
    txs, customers = files["transactions.csv"], files["customers.csv"]
    result = {**job, "decision": "failed", "grade": "unknown", "cleanup": "no_execution",
              "calls": [], "executions": [], "started_at": datetime.now(UTC).isoformat()}

    async def execute(source, transactions, lookup, purpose):
        result["stage"] = "execution"
        checked = await asyncio.to_thread(runner.execute, execution=uuid4(),
            job=UUID(job["run_id"]),
            generation=len(result["executions"]) + 1, pipeline=source, contract=contract,
            transactions=transactions, customers=lookup, purpose=purpose)
        intent = checked["intent"]
        bind_sources(intent, source=source, contract=contract, transactions=transactions,
                     customers=lookup, runtime=config["runtime_sha256"],
                     verifier=config["verifier_sha256"], purpose=purpose)
        decision, feedback = classify(checked, intent, config["runtime_sha256"],
                                      config["verifier_sha256"])
        result["executions"].append({"execution": intent["execution"], "purpose": purpose,
            "manifest": intent["manifest_sha256"], "decision": decision,
            "cleanup": checked["worker"]["cleanup"],
            "verifier_report": (checked.get("semantic") or {}).get("report_sha256")})
        result["cleanup"] = "confirmed"
        if checked["worker"]["outcome"] == "infrastructure_failure":
            raise RuntimeError("CRITICAL_WORKER_FAILURE")
        ok = (checked["worker"].get("collected") is True
              and type(checked["worker"].get("runtime_client_exit_code")) is int
              and checked["worker"]["runtime_client_exit_code"] == 0)
        return decision, feedback, ok, checked

    try:
        original, feedback, ok, checked = await execute(files["pipeline.py.txt"], txs, customers,
                                                        "original")
        if checked.get("semantic") and checked["semantic"]["report"]["status"] == "processed":
            feedback = {**checked["semantic"]["report"]["result"], "code": "CONTRACT_MISMATCH"}
        provider = load_provider_secrets("/etc/proofflow-repair/credentials")
        quote_data = dict(settings["provider"]["quote"])
        for field in ("observed_at", "valid_until"):
            quote_data[field] = datetime.fromisoformat(quote_data[field])
        quote = RateQuote(**quote_data)
        budget = RepairBudget(BudgetConnection(provider.database_password),
                              UUID(settings["provider"]["account_id"]))
        history = []
        for attempt in range(1, 4):
            if time.monotonic() - started > 165:
                result["decision"] = "timeout"
                break
            prompt = build_prompt(pipeline=files["pipeline.py.txt"], contract=contract,
                                  interface=INTERFACE, previous=history,
                                  feedback=feedback_for(job["arm"], feedback, ok))
            plan = prepare_repair_plan(prompt, quote, datetime.now(UTC))
            request = uuid4()
            call = {"request": str(request), "reserved_micro_usd": plan.reserve_micro_usd,
                    "estimated_micro_usd": None, "input_tokens": None, "output_tokens": None}
            result["calls"].append(call)
            result["stage"] = "provider"
            response = await _run_prepared(budget=budget, request_id=request, plan=plan,
                quote=quote,
                max_completion_tokens=COMPLETION_TOKENS, api_key=provider.vultr_api_key,
                journal=PilotJournal(root / "budget", job["run_id"], ProbeJournal(budget)))
            call["response_sha256"] = response.response_sha256
            if response.usage is None or response.usage.prompt_tokens > PROMPT_TOKEN_RESERVE:
                raise RuntimeError("PILOT_USAGE_UNKNOWN")
            usage = response.usage
            call.update(input_tokens=usage.prompt_tokens, output_tokens=usage.completion_tokens,
                        estimated_micro_usd=(usage.prompt_tokens * quote.input_micro_usd_per_million
                        + usage.completion_tokens * quote.output_micro_usd_per_million + 999999)
                        // 1000000)
            try:
                proposal = parse_proposal(response.content_json)
            except Exception:
                feedback, ok = {"code": "INVALID_PROPOSAL"}, False
                history.append({"attempt": attempt, "code": "INVALID_PROPOSAL",
                                "candidate_sha256": None})
                continue
            if proposal.kind == "needs_clarification":
                result["decision"] = "clarification"
                # This dataset has explicit hold rules; no automatic oracle approval
                # of model-authored questions. Human question review remains unknown.
                break
            if time.monotonic() - started > 165:
                result["decision"] = "timeout"
                break
            decision, feedback, ok, checked = await execute(proposal.source, txs, customers,
                                                           "candidate")
            result["candidate_sha256"] = proposal.sha256
            accepted = ok if job["arm"] == "B" else decision == "match"
            if decision == "held" and job["arm"] != "B":
                result.update(decision="held", grade="correct")
                break
            if accepted:
                # B's acceptance is fixed before seeing the protected final grade.
                result["decision"] = "accepted"
                passed = decision == "match"
                if passed:
                    for check in ("ownership", "quarantine"):
                        result["stage"] = "canary"
                        canary = await asyncio.to_thread(runner.canary, contract, check)
                        data = canary["report"]["result"]
                        outcome, feedback, _, _ = await execute(proposal.source,
                            decode(data["transactions_csv"], 5242880),
                            decode(data["customers_csv"], 5242880), "canary_" + check)
                        if outcome not in (("match", "held") if check == "quarantine"
                                           else ("match",)):
                            passed = False
                            break
                result["grade"] = "correct" if passed else "incorrect"
                if job["arm"] == "B" or passed:
                    break
                result["decision"] = "failed"
            history.append({"attempt": attempt, "code": feedback.get("code", "REJECTED"),
                            "candidate_sha256": proposal.sha256})
    except Exception as error:
        result["error_type"] = type(error).__name__  # Never raw provider/secret/exception text.
        result["decision"] = "failed"
        result["critical"] = result.get("stage") in ("execution", "canary")
        if result["critical"]:
            result["cleanup"] = "unknown"
    finally:
        result["elapsed_ms"] = round((time.monotonic() - started) * 1000)
        raw = json.dumps(result, sort_keys=True).encode()
        with (folder / "result.json").open("xb") as file:
            file.write(raw)
            file.flush()
            os.fsync(file.fileno())
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    os.umask(0o077)
    settings = json.loads(Path("/pilot/settings.json").read_bytes())
    job = next(j for j in settings["jobs"] if j["run_id"] == str(UUID(sys.argv[1])))
    asyncio.run(run(job, settings, Path("/var/lib/proofflow-pilot")))
