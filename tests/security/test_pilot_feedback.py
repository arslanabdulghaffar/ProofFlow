"""Trusted feedback adapters only, no model or candidate execution."""

import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="controller Linux imports")


def test_ablation_and_generic_loop_cannot_receive_witness_rows():
    from eval.pilot_controller import feedback_for

    sample = {"code": "CONTRACT_MISMATCH", "findings": [{"source_row_id": "private-canary"}],
              "ownership_witnesses": [{"expected_owner": "hidden"}]}
    assert feedback_for("A", sample, True) == sample
    assert feedback_for("C", sample, True) == {"code": "CONTRACT_MISMATCH"}
    assert feedback_for("B", sample, True) == {"code": "EXECUTION_EXIT_ZERO"}
    assert feedback_for("B", sample, False) == {"code": "CANDIDATE_EXECUTION_FAILED"}
