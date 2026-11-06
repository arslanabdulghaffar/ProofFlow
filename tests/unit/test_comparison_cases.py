"""Source-data oracle checks only: candidate payloads remain inert bytes."""

from collections import Counter

import pytest

from eval.comparison_cases import cases, check_oracle


def test_families_and_independent_small_oracles():
    values = cases('a' * 64)
    assert len(values) == 24
    assert Counter((c['family'], c['kind']) for c in values) == {
        (f, k): n for f in ('schema', 'units', 'joins', 'duplicates', 'completeness', 'downstream')
        for k, n in (('repairable', 3), ('ambiguous', 1))}
    for case in values:
        assert check_oracle(case) == case['oracle_summary']
    assert values == cases('a' * 64)
    assert {c['sha256'] for c in values}.isdisjoint(c['sha256'] for c in cases('b' * 64))


def test_oracle_error_is_not_silently_accepted():
    case = cases('c' * 64)[0]
    case['oracle_summary']['net_minor_units'] += 1
    with pytest.raises(ValueError, match='ORACLE_DISAGREEMENT'):
        check_oracle(case)
