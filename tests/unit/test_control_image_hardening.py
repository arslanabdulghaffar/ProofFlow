"""Synthetic observations test fail-closed checks, not deployed containment."""

from copy import deepcopy

import pytest

from scripts.check_control_image import validate_hardening

BASE = {
    "pid1": {
        "Uid": "10001\t10001\t10001\t10001",
        "Gid": "10001\t10001\t10001\t10001",
        "CapInh": "0000000000000000",
        "CapPrm": "0000000000000000",
        "CapEff": "0000000000000000",
        "CapBnd": "0000000000000000",
        "CapAmb": "0000000000000000",
        "NoNewPrivs": "1",
    },
    "setid_files_under_usr": [],
    "inventory_errors": [],
    "fstab_entries": [],
    "usr_aliases": {"/bin": "/usr/bin", "/sbin": "/usr/sbin", "/lib": "/usr/lib"},
}


def test_expected_observation():
    validate_hardening(BASE)


@pytest.mark.parametrize("field,value", [
    ("Uid", "10001 0 0 10001"), ("Gid", "0 0 0 0"),
    ("CapInh", "1"), ("CapPrm", "1"), ("CapEff", "200000"),
    ("CapBnd", "1"), ("CapAmb", "1"), ("NoNewPrivs", "0"),
])
def test_unexpected_service_privilege_rejected(field, value):
    observed = deepcopy(BASE)
    observed["pid1"][field] = value
    with pytest.raises(RuntimeError):
        validate_hardening(observed)


@pytest.mark.parametrize("field", [
    "setid_files_under_usr", "inventory_errors", "fstab_entries",
])
def test_unsafe_or_incomplete_filesystem_observation_rejected(field):
    observed = deepcopy(BASE)
    observed[field] = ["synthetic unexpected entry"]
    with pytest.raises(RuntimeError):
        validate_hardening(observed)


def test_missing_evidence_cannot_pass():
    observed = deepcopy(BASE)
    del observed["pid1"]["NoNewPrivs"]
    with pytest.raises(KeyError):
        validate_hardening(observed)


def test_inventory_scope_mismatch_rejected():
    observed = deepcopy(BASE)
    observed["usr_aliases"]["/bin"] = "/bin"
    with pytest.raises(RuntimeError):
        validate_hardening(observed)
