"""Only source data parsing/hashing; pipeline payloads remain inert bytes."""

from collections import Counter

from eval.development import cases, check_oracle, inventory


def test_twelve_reproducible_disclosed_development_cases():
    first, second = cases(), cases()
    assert first == second and len(first) == 12
    assert len({c["sha256"] for c in first}) == 12
    assert Counter(c["kind"] for c in first) == {"repairable": 6, "ambiguous": 6}
    for case in first:
        assert len(case["files"]["pipeline.py.txt"]) <= 16384
        expected = check_oracle(case)
        assert expected["ledger_rows"] == 3 and expected["net_minor_units"] == 0
        assert (expected["blocking_occurrences"] > 0) == (case["kind"] == "ambiguous")
    summary = inventory()
    assert summary["model_calls"] == 0 and summary["manual_owner_oracle_review"] == "NOT_AVAILABLE"
    assert "files" not in summary["cases"][0]
