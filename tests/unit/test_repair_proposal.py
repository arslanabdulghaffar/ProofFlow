"""Untrusted proposal parsing only; no candidate source is executed here."""

import json

import pytest

from orchestrator.probe_response import ProviderResponseError
from orchestrator.repair_proposal import INTERFACE, RepairRejected, build_prompt, parse_proposal


def patch(**changes):
    return {
        "kind": "propose_patch",
        "diagnosis": "Bad composite join",
        "changed_file": "pipeline.py",
        "candidate_source": "untrusted source text",
        "expected_effect": "Match both IDs",
        "uncertainties": [],
        **changes,
    }


def parse(value):
    return parse_proposal(json.dumps(value).encode())


def test_source_is_inert_hash_bound_and_strict_variant():
    proposal = parse(patch(candidate_source="raise SystemExit('must never execute')"))
    assert proposal.sha256 and proposal.source.startswith(b"raise SystemExit")
    assert parse({"kind": "needs_clarification", "questions": ["Which unit?"]}).source is None


@pytest.mark.parametrize(
    "change",
    [
        {"changed_file": "../verifier.py"},
        {"changed_file": "contract.json"},
        {"candidate_source": "x" * 16385},
        {"candidate_source": "\x00"},
        {"candidate_source": " "},
        {"expected_effect": False},
        {"uncertainties": ["x"] * 6},
        {"tools": ["shell"]},
        {"limits": {"network": True}},
    ],
)
def test_invalid_patch_has_no_authority(change):
    with pytest.raises(RepairRejected):
        parse(patch(**change))


@pytest.mark.parametrize(
    "value",
    [
        {"kind": "needs_clarification", "questions": []},
        {"kind": "needs_clarification", "questions": ["?"], "candidate_source": "x"},
        {"kind": "needs_clarification", "questions": ["x" * 513]},
        {"kind": "PASS"},
    ],
)
def test_invalid_abstention(value):
    with pytest.raises(RepairRejected):
        parse(value)


def test_duplicate_keys_and_escaped_unicode_limits():
    with pytest.raises(ProviderResponseError):
        parse_proposal(b'{"kind":"needs_clarification","kind":"propose_patch"}')
    with pytest.raises(RepairRejected):
        parse(patch(candidate_source="\U0001f600" * 4097))


def test_prompt_excludes_canary_material_and_arbitrary_report_keys():
    prompt = build_prompt(
        pipeline=b"untrusted",
        contract=b"{}",
        interface=INTERFACE,
        feedback={
            "findings": [],
            "seed": "SECRET_SEED",
            "expected_rows": "ORACLE",
            "worker_log": "CREDENTIAL",
            "ownership_witnesses": [],
        },
        previous=[],
    )
    assert not any(secret in prompt for secret in ("SECRET_SEED", "ORACLE", "CREDENTIAL"))
    assert "untrusted" in prompt and "pipeline.py" in prompt
    with pytest.raises(RepairRejected):
        build_prompt(
            pipeline=b"x" * 16384, contract=b"{}", interface=INTERFACE, feedback={}, previous=[]
        )


def test_history_accepts_only_fixed_summary_fields():
    with pytest.raises(RepairRejected):
        build_prompt(
            pipeline=b"x",
            contract=b"{}",
            interface=INTERFACE,
            feedback={},
            previous=[{"hidden_canary": "source"}],
        )
