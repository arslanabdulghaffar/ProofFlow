"""Synthetic receipt tampering checks. No worker or generated code runs."""

import copy

import pytest

from orchestrator.repair_evidence import bind_sources, classify
from orchestrator.repair_proposal import RepairRejected
from worker.protocol import runtime_identity_digest


def receipt(purpose="candidate", comparison="match", blocking=0):
    intent = {
        "execution": "a" * 32,
        "job": "b" * 32,
        "generation": 1,
        "manifest_sha256": "c" * 64,
        "purpose": purpose,
        "contract_sha256": "d" * 64,
        "transactions_sha256": "e" * 64,
        "customers_sha256": "f" * 64,
    }
    hashes = {"ledger.jsonl": "1" * 64, "unresolved.jsonl": "2" * 64}
    worker = {
        "execution": intent["execution"],
        "job": intent["job"],
        "generation": 1,
        "manifest": intent["manifest_sha256"],
        "runtime": {},
        "cleanup": "confirmed",
        "collected": True,
        "runtime_client_exit_code": 0,
        "unit_result": "success",
        "files": [{"name": k, "sha256": v} for k, v in hashes.items()],
    }
    semantic = {
        "operation": "verify",
        "comparison": comparison,
        "blocking_occurrences": blocking,
        "finding_count": int(comparison == "mismatch"),
        "findings": [],
        "output_hashes": hashes,
        **{
            key: intent[key]
            for key in ("contract_sha256", "transactions_sha256", "customers_sha256")
        },
    }
    if comparison == "mismatch":
        semantic["findings"] = [{"check": "V04", "code": "OWNER_MISMATCH", "source": "hidden"}]
        semantic["ownership_witnesses"] = [{"expected_owner": "secret_canary_owner"}]
    return intent, {
        "intent": copy.deepcopy(intent),
        "worker": worker,
        "semantic": {
            "cleanup_confirmed": True,
            "rootfs_sha256": "3" * 64,
            "report": {
                "version": "proofflow-verifier-v1",
                "status": "processed",
                "result": semantic,
            },
        },
    }


def test_match_held_and_canary_feedback_distinct():
    for purpose in ("candidate", "canary_ownership", "canary_quarantine"):
        intent, result = receipt(purpose, "mismatch")
        code, feedback = classify(result, intent, runtime_identity_digest({}), "3" * 64)
        assert code == "mismatch"
        if purpose != "candidate":
            assert feedback == {"code": "PROTECTED_CHECK_FAILED"}
    intent, result = receipt(blocking=1)
    assert classify(result, intent, runtime_identity_digest({}), "3" * 64)[0] == "held"


@pytest.mark.parametrize(
    "path,value",
    [
        (("intent", "purpose"), "original"),
        (("worker", "cleanup"), "unknown"),
        (("worker", "generation"), 2),
        (("worker", "manifest"), "0" * 64),
        (("worker", "runtime"), {"changed": True}),
        (("semantic", "rootfs_sha256"), "0" * 64),
        (("semantic", "cleanup_confirmed"), False),
        (("semantic", "report", "result", "contract_sha256"), "0" * 64),
        (("semantic", "report", "result", "output_hashes"), {}),
        (("semantic", "report", "result", "finding_count"), 1),
        (("semantic", "report", "result", "blocking_occurrences"), True),
    ],
)
def test_tampered_proof_cannot_pass(path, value):
    intent, result = receipt()
    target = result
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value
    with pytest.raises(RepairRejected):
        classify(result, intent, runtime_identity_digest({}), "3" * 64)


def test_exit_zero_alone_and_source_swap_never_pass():
    intent, result = receipt()
    result["semantic"] = None
    with pytest.raises(RepairRejected):
        classify(result, intent, runtime_identity_digest({}), "3" * 64)
    with pytest.raises(RepairRejected):
        bind_sources(
            intent,
            source=b"changed",
            contract=b"{}",
            transactions=b"x",
            customers=b"y",
            runtime="r",
            verifier="v",
            purpose="candidate",
        )
