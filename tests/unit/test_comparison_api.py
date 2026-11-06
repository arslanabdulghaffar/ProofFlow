"""A adapter doubles and synthetic proof tampering. No real I/O or code execution."""

import copy
import hashlib
import json
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from orchestrator.repair_proposal import RepairRejected
from scripts import comparison_api as module
from worker.protocol import runtime_identity_digest


def proof_fixture():
    files = {"contract.json": b"{}", "transactions.csv": b"t", "customers.csv": b"c"}
    source = b"inert candidate"

    def sha(raw):
        return hashlib.sha256(raw).hexdigest()

    policy = {"runtime_sha256": runtime_identity_digest({}), "verifier_sha256": "3" * 64}
    export = {
        "candidate_source": source.decode(),
        "candidate_sha256": sha(source),
        "activation_approved": False,
    }
    output_hashes = {"ledger.jsonl": "1" * 64, "unresolved.jsonl": "2" * 64}
    executions = []
    job = uuid4().hex
    for number, purpose in enumerate(("candidate", "canary_ownership", "canary_quarantine"), 1):
        identifier = uuid4()
        intent = {
            "execution": identifier.hex,
            "job": job,
            "generation": number,
            "manifest_sha256": "a" * 64,
            "purpose": purpose,
            "pipeline_sha256": sha(source),
            "contract_raw_sha256": sha(files["contract.json"]),
            "contract_sha256": "d" * 64,
            "transactions_sha256": sha(files["transactions.csv"]),
            "customers_sha256": sha(files["customers.csv"]),
            "runtime_sha256": policy["runtime_sha256"],
            "verifier_rootfs": policy["verifier_sha256"],
        }
        semantic = {
            "operation": "verify",
            "comparison": "match",
            "finding_count": 0,
            "findings": [],
            "blocking_occurrences": int(purpose == "canary_quarantine"),
            "output_hashes": output_hashes,
            **{
                k: intent[k] for k in ("contract_sha256", "transactions_sha256", "customers_sha256")
            },
        }
        receipt = {
            "intent": copy.deepcopy(intent),
            "worker": {
                "execution": identifier.hex,
                "job": job,
                "generation": number,
                "manifest": intent["manifest_sha256"],
                "runtime": {},
                "cleanup": "confirmed",
                "collected": True,
                "runtime_client_exit_code": 0,
                "unit_result": "success",
                "files": [{"name": k, "sha256": v} for k, v in output_hashes.items()],
            },
            "semantic": {
                "cleanup_confirmed": True,
                "rootfs_sha256": policy["verifier_sha256"],
                "report": {
                    "version": "proofflow-verifier-v1",
                    "status": "processed",
                    "result": semantic,
                },
            },
        }
        executions.append(
            {
                "execution_id": str(identifier),
                "purpose": purpose,
                "attempt": 1,
                "intent": intent,
                "result": receipt,
            }
        )
    return export, executions, files, policy


def test_real_classifier_requires_fresh_exact_proofs():
    export, executions, files, policy = proof_fixture()
    assert module.grade_export(export, executions, files, policy) == export["candidate_sha256"]


@pytest.mark.parametrize(
    "fault",
    [
        "duplicate",
        "source",
        "approved",
        "missing",
        "cleanup",
        "runtime",
        "output",
        "attempt",
        "source_bytes",
    ],
)
def test_proof_tampering_cannot_pass(fault):
    export, executions, files, policy = proof_fixture()
    if fault == "duplicate":
        executions[-1]["execution_id"] = executions[0]["execution_id"]
    elif fault == "source":
        export["candidate_source"] = "changed"
    elif fault == "approved":
        export["activation_approved"] = True
    elif fault == "missing":
        executions.pop()
    elif fault == "cleanup":
        executions[0]["result"]["worker"]["cleanup"] = "unknown"
    elif fault == "runtime":
        executions[-1]["result"]["worker"]["runtime"] = {"changed": True}
    elif fault == "output":
        executions[0]["result"]["semantic"]["report"]["result"]["output_hashes"] = {}
    elif fault == "attempt":
        executions[-1]["attempt"] = 2
    elif fault == "source_bytes":
        files["transactions.csv"] = b"different"
    with pytest.raises((RuntimeError, RepairRejected)):
        module.grade_export(export, executions, files, policy)


def call_fixture(known=True, usage=True):
    body = {
        "id": "chatcmpl-synthetic",
        "object": "chat.completion",
        "model": "qwen3.8-flash-next",
        "choices": [
            {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "{}"}}
        ],
    }
    if usage:
        body["usage"] = {"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70}
    return {
        "request_id": str(uuid4()),
        "reserved_micro": 27853,
        "outcome": "PARSED_RESPONSE" if known else "OUTCOME_UNKNOWN",
        "quote": "\\x"
        + json.dumps({"model": "qwen3.8-flash-next", "input_rate": 100000, "output_rate": 200000})
        .encode()
        .hex(),
        "response": "\\x" + json.dumps(body).encode().hex(),
    }


def test_provider_usage_is_estimate_and_missing_delivery_stays_unknown():
    rows = [call_fixture(), call_fixture(False), call_fixture(usage=False)]
    calls = module.calls_from_rows(rows)
    assert calls[0]["estimated_micro_usd"] == 9
    assert calls[0]["delivery_confirmed"] and calls[2]["delivery_confirmed"]
    assert not calls[1]["delivery_confirmed"]
    assert calls[1]["estimated_micro_usd"] is None and calls[2]["input_tokens"] is None
    with pytest.raises(RuntimeError):
        module.calls_from_rows(rows + [call_fixture()])


def api_fixture(tmp_path, *, blocked=0, unknown_unit=False, failed=False):
    export, executions, files, policy = proof_fixture()
    files["pipeline.py.txt"] = b"inert original"
    case = {
        "files": files,
        "file_hashes": {k: hashlib.sha256(v).hexdigest() for k, v in files.items()},
    }
    job = {"arm": "A", "case": "test-case", "repeat": 1, "run_id": str(uuid4())}
    posts, sql = [], []
    call = call_fixture()

    def response(status, body):
        return SimpleNamespace(status_code=status, json=lambda: body)

    class Client:
        def post(self, path, *, content=None, json=None):
            assert (tmp_path / job["run_id"] / "intent.json").exists()
            posts.append(path)
            if path.startswith("/v1/assets/"):
                return response(201, {"sha256": hashlib.sha256(content).hexdigest()})
            if path.startswith("/v1/contracts/"):
                return (
                    response(422, {"error": {"code": "UNKNOWN_UNIT"}})
                    if unknown_unit
                    else response(200, {})
                )
            if path == "/v1/jobs":
                return response(202, {"job_id": str(uuid4())})
            if path == "/v1/repairs":
                return response(202, {"repair_id": str(uuid4())})
            if path == "/v1/workspace/delete":
                return response(200, {"access_revoked": True})
            raise AssertionError(path)

        def get(self, path):
            if path.startswith("/v1/jobs/"):
                return response(
                    200,
                    {
                        "state": "FAILED_INFRA" if failed else "NEEDS_REVIEW",
                        "outcome": "mismatch",
                        "report": {
                            "worker": {"cleanup": "confirmed"},
                            "semantic": {"report": {"result": {"blocking_occurrences": blocked}}},
                        },
                    },
                )
            if path.endswith("/export"):
                return response(200, export)
            return response(
                200,
                {
                    "state": "AWAITING_APPROVAL",
                    "outcome": "candidate_passed",
                    "calls": 1,
                    "reserved_micro": 27853,
                },
            )

    class Live:
        def __init__(self):
            self.policy = policy

        def sql(self, statement):
            sql.append(statement)
            if "repair_executions" in statement:
                return json.dumps(executions).encode()
            if "repair_calls" in statement:
                return json.dumps([call]).encode()
            if "deletions" in statement:
                return b"1"
            assert (tmp_path / job["run_id"] / "intent.json").exists()
            return b""

        def login(self, workspace):
            UUID(workspace)
            return Client()

        def host(self, command):
            return b"retired" if "test ! -e" in command else b""

    return Live(), job, case, posts, sql


def test_full_api_flow_preserves_evidence_then_retires_without_activation(tmp_path):
    live, job, case, posts, sql = api_fixture(tmp_path)
    result = module.run(live, job, case, tmp_path)
    assert result["decision"] == "accepted" and result["grade"] == "correct"
    assert len(result["calls"]) == 1 and len(result["executions"]) == 3
    assert not any("activate" in path or "github" in path or "versions" in path for path in posts)
    module.retire(live, result, tmp_path)
    assert posts[-1] == "/v1/workspace/delete"
    assert (tmp_path / job["run_id"] / "retirement-completed.json").exists()
    before = len(posts)
    with pytest.raises(FileExistsError):
        module.run(live, job, case, tmp_path)
    assert len(posts) == before
    with pytest.raises(FileExistsError):
        module.retire(live, result, tmp_path)
    assert len(posts) == before


@pytest.mark.parametrize(
    "condition,decision", [("blocked", "held"), ("unknown", "clarification"), ("failed", "failed")]
)
def test_no_repair_after_held_intake_or_critical_infrastructure(tmp_path, condition, decision):
    live, job, case, posts, sql = api_fixture(
        tmp_path,
        blocked=int(condition == "blocked"),
        unknown_unit=condition == "unknown",
        failed=condition == "failed",
    )
    result = module.run(live, job, case, tmp_path)
    assert result["decision"] == decision and not result["calls"]
    assert "/v1/repairs" not in posts
    if condition == "failed":
        assert result["critical"] and result["cleanup"] == "unknown"
        with pytest.raises(RuntimeError):
            module.retire(live, result, tmp_path)
        assert "/v1/workspace/delete" not in posts
