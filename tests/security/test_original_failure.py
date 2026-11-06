"""Controller doubles and data only. Candidate source is never executed here."""

import os
from types import SimpleNamespace
from uuid import uuid4

import pytest

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Linux controller imports")


def receipt():
    from worker.protocol import runtime_identity_digest

    intent = {
        "execution": uuid4().hex,
        "job": uuid4().hex,
        "generation": 1,
        "manifest_sha256": "a" * 64,
        "runtime_sha256": runtime_identity_digest({"pin": "x"}),
    }
    worker = {
        "execution": intent["execution"],
        "job": intent["job"],
        "generation": 1,
        "manifest": intent["manifest_sha256"],
        "runtime": {"pin": "x"},
        "cleanup": "confirmed",
        "outcome": "output_rejected",
        "collected": False,
        "runtime_client_exit_code": 1,
        "runtime_exit_code": "1",
        "runtime_exit_kind": "1",
        "resource_observation": {
            "source": "host_cgroup_v2",
            "samples": 1,
            "limits": {
                "cpu_cores": 1,
                "memory_bytes": 805306368,
                "swap_bytes": 0,
                "host_tasks": 128,
            },
        },
        "unit_result": "exit-code",
    }
    return intent, worker


def test_retained_failure_receipt_retires_raw_preview_without_changing_identity():
    import hashlib
    import json

    from orchestrator.verification_run import retained_receipt

    _, worker = receipt()
    preview = {"stderr": "synthetic-private-preview"}
    worker["failure_log_preview"] = preview
    clean = retained_receipt(worker)
    assert "failure_log_preview" in worker  # Do not mutate the live response.
    assert "synthetic-private-preview" not in json.dumps(clean)
    assert (
        clean["failure_log_preview_sha256"]
        == hashlib.sha256(json.dumps(preview, sort_keys=True).encode()).hexdigest()
    )
    assert clean["failure_log_preview_retired"] is True
    assert retained_receipt(clean) == clean
    for key in ("execution", "job", "generation", "manifest", "runtime", "cleanup"):
        assert clean[key] == worker[key]


@pytest.mark.parametrize(
    "change",
    [
        {"cleanup": "uncertain"},
        {"outcome": "timeout"},
        {"outcome": "cancelled"},
        {"outcome": "infrastructure_failure"},
        {"unit_result": "oom-kill"},
        {"unit_result": "signal"},
        {"runtime_exit_kind": "2"},
        {"runtime_exit_code": "0"},
        {"runtime_client_exit_code": True},
        {"runtime_client_exit_code": 127},
        {"runtime_client_exit_code": -1},
        {"generation": True},
        {"job": "wrong"},
        {"manifest": "b" * 64},
        {"runtime": {"pin": "foreign"}},
        {"unit_result": None},
        {"resource_observation": None},
        {"resource_observation": {"source": "guest", "samples": 1}},
    ],
)
def test_uncertain_or_infrastructure_failure_is_never_repairable(change):
    from orchestrator.verification_run import repairable_failure

    intent, worker = receipt()
    assert repairable_failure(worker, intent)
    assert not repairable_failure({**worker, **change}, intent)


def test_zero_exit_missing_output_is_failure_but_successful_output_is_not():
    from orchestrator.verification_run import repairable_failure

    intent, worker = receipt()
    worker.update(runtime_client_exit_code=0, runtime_exit_code="0", unit_result="success")
    assert repairable_failure(worker, intent)
    worker["runtime_exit_kind"] = "0"
    assert repairable_failure(worker, intent)
    worker["resource_observation"]["samples"] = 0
    assert not repairable_failure(worker, intent)
    worker["resource_observation"]["samples"] = 1
    worker.update(outcome="exited", collected=True)
    assert not repairable_failure(worker, intent)


@pytest.mark.parametrize("purpose,blocked", [("original", 0), ("original", 4), ("candidate", 0)])
def test_failure_has_separate_source_diagnosis_and_no_output_proof(tmp_path, purpose, blocked):
    from contracts.codec import canonical_bytes, parse_object
    from orchestrator.verification_run import VerificationRun
    from verifier.protocol import encode
    from worker.protocol import runtime_identity_digest

    operations = []

    def verifier(raw):
        message = parse_object(raw)
        operations.append(message["operation"])
        result = (
            {
                "transactions_jsonl": encode(b"{}\n"),
                "customers_jsonl": encode(b"{}\n"),
                "requirements": encode(b"{}"),
                "include_rollups": False,
                "contract_sha256": "c" * 64,
            }
            if message["operation"] == "prepare"
            else {"operation": "source", "blocking_occurrences": blocked}
        )
        return {"cleanup_confirmed": True, "report": {"status": "processed", "result": result}}

    def create(request):
        _, value = receipt()
        value.update(
            execution=request.execution_id.hex,
            job=request.job_id.hex,
            manifest=request.manifest_hash(),
        )
        return value

    client = SimpleNamespace(runtime_digest=runtime_identity_digest({"pin": "x"}), create=create)
    (tmp_path / "journal").mkdir(mode=0o700)
    runner = VerificationRun(
        client, tmp_path / "unused", "d" * 64, tmp_path / "journal", verifier=verifier
    )
    result = runner.execute(
        execution=uuid4(),
        job=uuid4(),
        generation=1,
        pipeline=b"inert",
        contract=b"{}",
        transactions=b"t",
        customers=b"c",
        purpose=purpose,
    )
    assert result["semantic"] is None
    assert operations == (["prepare", "source"] if purpose == "original" else ["prepare"])
    assert ("source" in result) == (purpose == "original")
    assert "output_hashes" not in canonical_bytes(result).decode()
