"""Comparison orchestration doubles only; candidate text is NEVER executed."""

import asyncio
import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Linux controller imports")


def setup(
    tmp_path, monkeypatch, arm, sequence, *, blocked=0, unknown_unit=False, unknown_usage=False
):
    from eval import comparison_controller as module
    from verifier.protocol import encode

    base = tmp_path / "mock-root"
    base.mkdir()

    def path(value):
        raw = str(value)
        return base / raw.lstrip("/") if raw.startswith("/") else Path(raw)

    config = path("/etc/proofflow-product/worker/worker.json")
    config.parent.mkdir(parents=True)
    config.write_text(
        json.dumps(
            {
                "runtime_sha256": "r" * 64,
                "verifier_sha256": "v" * 64,
                "worker_address": "inert",
                "worker_certificate_sha256": "p" * 64,
            }
        )
    )
    provider_config = path("/etc/proofflow-repair/config.json")
    provider_config.parent.mkdir(parents=True)
    now = datetime.now(UTC)
    provider_config.write_text(
        json.dumps(
            {
                "account_id": str(uuid4()),
                "quote": {
                    "model": "qwen3.8-flash-next",
                    "input_micro_usd_per_million": 100000,
                    "output_micro_usd_per_million": 200000,
                    "evidence_sha256": "a" * 64,
                    "observed_at": now.isoformat(),
                    "valid_until": (now + timedelta(hours=1)).isoformat(),
                },
            }
        )
    )
    files = {
        "pipeline.py.txt": b"inert original",
        "transactions.csv": b"t",
        "customers.csv": b"c",
        "contract.json": b"{}",
    }
    folder = path("/comparison/cases/test-case")
    folder.mkdir(parents=True)
    for name, raw in files.items():
        (folder / name).write_bytes(raw)
    path("/comparison/deterministic.py.txt").write_bytes(b"inert deterministic")
    root = tmp_path / "state"
    root.mkdir(mode=0o700)
    calls, executed = [], []
    monkeypatch.setattr(module, "Path", path)
    monkeypatch.setattr(module, "tls_context", lambda *a, **k: None)
    monkeypatch.setattr(module, "WorkerClient", lambda *a: SimpleNamespace())
    monkeypatch.setattr(module, "bind_sources", lambda *a, **k: None)
    monkeypatch.setattr(module, "runtime_identity_digest", lambda raw: "r" * 64)
    monkeypatch.setattr(module, "ComparisonJournal", lambda *a: None)
    monkeypatch.setattr(
        module,
        "load_provider_secrets",
        lambda *a: SimpleNamespace(database_password="synthetic" * 8, vultr_api_key="synthetic"),
    )

    class Runner:
        def __init__(self, *a, **k):
            self.after_capture = k["after_capture"]

        def bounded(self, message):
            assert message["operation"] == "source"
            return {
                "report": {"status": "rejected", "code": "UNKNOWN_UNIT"}
                if unknown_unit
                else {"status": "processed", "result": {"blocking_occurrences": blocked}}
            }

        def canary(self, contract, case):
            return {
                "report": {
                    "result": {
                        "transactions_csv": encode(b"protected"),
                        "customers_csv": encode(b"protected"),
                    }
                }
            }

        def execute(self, **values):
            executed.append(values["purpose"])
            decision = sequence[len(executed) - 1]
            execution = values["execution"].hex
            result = {
                "intent": {
                    "execution": execution,
                    "manifest_sha256": "m" * 64,
                    "job": values["job"].hex,
                    "generation": values["generation"],
                },
                "desired": decision,
                "worker": {
                    "cleanup": "confirmed",
                    "outcome": "exited",
                    "collected": True,
                    "runtime_client_exit_code": 0,
                    "unit_result": "success",
                    "execution": execution,
                    "job": values["job"].hex,
                    "generation": values["generation"],
                    "manifest": "m" * 64,
                },
                "semantic": {
                    "report_sha256": "s" * 64,
                    "report": {
                        "status": "processed",
                        "result": {
                            "findings": [{"code": "DO_NOT_LEAK"}],
                            "ownership_witnesses": [{"expected_owner": "DO_NOT_LEAK"}],
                        },
                    },
                },
            }
            self.after_capture(
                SimpleNamespace(
                    execution_id=values["execution"],
                    job_id=values["job"],
                    generation=values["generation"],
                    pipeline=values["pipeline"],
                    manifest_hash=lambda: "m" * 64,
                ),
                result["worker"],
            )
            return result

    monkeypatch.setattr(module, "VerificationRun", Runner)
    monkeypatch.setattr(
        module,
        "classify",
        lambda result, *a: (
            result["desired"],
            {"code": "CONTRACT_MISMATCH", "ownership_witnesses": ["DO_NOT_LEAK"]},
        ),
    )

    async def provider(**values):
        payload = json.loads(values["plan"].payload)
        assert "DO_NOT_LEAK" not in json.dumps(payload)
        assert "/comparison" not in json.dumps(payload)
        calls.append(payload)
        return SimpleNamespace(
            response_sha256="a" * 64,
            content_json=b"{}",
            usage=None if unknown_usage else SimpleNamespace(prompt_tokens=5, completion_tokens=5),
        )

    monkeypatch.setattr(module, "_run_prepared", provider)
    monkeypatch.setattr(
        module,
        "parse_proposal",
        lambda raw: SimpleNamespace(kind="propose_patch", source=b"inert patch", sha256="c" * 64),
    )
    settings = {
        "runtime_sha256": "r" * 64,
        "verifier_sha256": "v" * 64,
        "account_id": json.loads(provider_config.read_bytes())["account_id"],
        "campaign_sha256": "f" * 64,
        "deterministic_sha256": hashlib.sha256(b"inert deterministic").hexdigest(),
        "cases": {
            "test-case": {
                "file_hashes": {k: hashlib.sha256(v).hexdigest() for k, v in files.items()}
            }
        },
    }
    job = {"run_id": str(uuid4()), "case": "test-case", "arm": arm, "repeat": 1}
    return module, job, settings, root, calls, executed


@pytest.mark.parametrize(
    "arm,sequence,decision,grade,calls",
    [
        ("B", ["mismatch", "mismatch"], "accepted", "incorrect", 1),
        ("C", ["mismatch", "mismatch", "match", "match", "held"], "accepted", "correct", 2),
        (
            "C",
            ["mismatch", "match", "mismatch", "match", "match", "held"],
            "accepted",
            "correct",
            2,
        ),
        ("D", ["match", "match", "held"], "accepted", "correct", 0),
    ],
)
def test_arm_acceptance_fresh_protected_grading_no_feedback_leak(
    tmp_path, monkeypatch, arm, sequence, decision, grade, calls
):
    module, job, settings, root, recorded, executed = setup(tmp_path, monkeypatch, arm, sequence)
    result = asyncio.run(module.run(job, settings, root))
    assert result["decision"] == decision and result["grade"] == grade
    assert len(recorded) == calls
    assert len(executed) == len(sequence)
    assert json.loads((root / job["run_id"] / "result.json").read_bytes()) == result


@pytest.mark.parametrize(
    "arm,unknown,executions",
    [("C", False, 1), ("D", False, 0), ("B", True, 0), ("C", True, 0), ("D", True, 0)],
)
def test_source_hold_and_unknown_unit_are_not_model_success(
    tmp_path, monkeypatch, arm, unknown, executions
):
    module, job, settings, root, calls, executed = setup(
        tmp_path, monkeypatch, arm, ["held"], blocked=2, unknown_unit=unknown
    )
    result = asyncio.run(module.run(job, settings, root))
    assert result["decision"] == ("clarification" if unknown else "held")
    assert result["grade"] == "correct"
    assert len(executed) == executions and not calls
    if unknown:
        assert result["intake_rejection"] == "UNKNOWN_UNIT"


def test_unknown_usage_does_not_retry_or_claim_repair_success(tmp_path, monkeypatch):
    module, job, settings, root, calls, executed = setup(
        tmp_path, monkeypatch, "C", ["mismatch"], unknown_usage=True
    )
    result = asyncio.run(module.run(job, settings, root))
    assert result["decision"] == "failed" and result["grade"] == "unknown"
    assert len(calls) == 1 and executed == ["original"]


@pytest.mark.parametrize("arm", ["B", "C"])
def test_grader_failure_preserves_baseline_acceptance_only(tmp_path, monkeypatch, arm):
    module, job, settings, root, calls, executed = setup(
        tmp_path, monkeypatch, arm, ["mismatch", "match"]
    )
    original = module.classify

    def grade(result, *args):
        if len(executed) == 2:
            raise RuntimeError("synthetic grader outage")
        return original(result, *args)

    monkeypatch.setattr(module, "classify", grade)
    result = asyncio.run(module.run(job, settings, root))
    assert result["decision"] == ("accepted" if arm == "B" else "failed")
    assert result["grade"] == "unknown" and result["critical"]
    assert len(calls) == 1
    assert (root / job["run_id"] / "baseline-acceptance.json").exists() == (arm == "B")


@pytest.mark.parametrize("arm", ["B", "C"])
def test_grading_timeout_does_not_erase_baseline_decision(tmp_path, monkeypatch, arm):
    module, job, settings, root, calls, executed = setup(
        tmp_path, monkeypatch, arm, ["mismatch", "match"]
    )
    # Patch only the controller's clock, not asyncio's event-loop clock.
    monkeypatch.setattr(
        module, "time", SimpleNamespace(monotonic=lambda: 170 if len(executed) == 2 else 0)
    )
    result = asyncio.run(module.run(job, settings, root))
    assert result["decision"] == ("accepted" if arm == "B" else "timeout")
    assert result["grade"] == "unknown" and result["grading_timeout"]
    assert len(calls) == 1 and len(executed) == 2


def test_three_calls_no_fourth_or_uncertain_replay(tmp_path, monkeypatch):
    module, job, settings, root, calls, executed = setup(
        tmp_path, monkeypatch, "C", ["mismatch"] * 4
    )
    result = asyncio.run(module.run(job, settings, root))
    assert result["decision"] == "failed" and len(calls) == 3 and len(executed) == 4
    before = (root / job["run_id"] / "result.json").read_bytes()
    with pytest.raises(FileExistsError):
        asyncio.run(module.run(job, settings, root))
    assert len(calls) == 3 and len(executed) == 4
    assert (root / job["run_id"] / "result.json").read_bytes() == before


def test_worker_identity_cannot_grant_baseline_acceptance(tmp_path, monkeypatch):
    module, job, settings, root, calls, executed = setup(tmp_path, monkeypatch, "B", ["mismatch"])
    monkeypatch.setattr(module, "runtime_identity_digest", lambda raw: "x" * 64)
    result = asyncio.run(module.run(job, settings, root))
    assert result["decision"] == "failed" and result["critical"] and not calls
    assert not (root / job["run_id"] / "baseline-acceptance.json").exists()
