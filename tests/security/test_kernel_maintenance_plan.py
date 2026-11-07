"""Package-plan fixtures only; never installs or reboots a host."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from update_host_kernel import PACKAGES, VERSION, validate_simulation  # noqa: E402


def simulation():
    return "\n".join(f"Inst {p} ({VERSION} Ubuntu:24.04/noble-updates [amd64])"
                     for p in PACKAGES)


def test_exact_signed_update_plan():
    validate_simulation(simulation())


@pytest.mark.parametrize("change", [
    lambda s: s + "\nRemv unrelated",
    lambda s: s + "\nInst unrelated (1 Ubuntu:24.04/noble-updates [amd64])",
    lambda s: s.replace(VERSION, "6.8.0-147.147", 1),
    lambda s: s.replace("noble-updates", "noble-proposed", 1),
    lambda s: "\n".join(s.splitlines()[1:]),
    lambda s: s + "\n" + s.splitlines()[0],
    lambda s: s + "\nInst unparseable",
])
def test_drift_refused(change):
    with pytest.raises(RuntimeError):
        validate_simulation(change(simulation()))
