"""Explicit two-mount variant, all other existing container limits stay enforced."""

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from public_api_policy import PUBLIC_MOUNTS, validate_public_container  # noqa: E402

from tests.security.test_product_container_drift import ENV, fixture  # noqa: E402


def public():
    value = copy.deepcopy(fixture())
    value["Config"]["Labels"]["proofflow.role"] = "product-public-api"
    for mount in value["Mounts"]:
        if mount["Destination"] in PUBLIC_MOUNTS:
            mount["Source"], mount["RW"] = PUBLIC_MOUNTS[mount["Destination"]]
    return value


def test_public_policy_requires_explicit_socket_and_tls_only():
    validate_public_container(public(), ENV)
    with pytest.raises(RuntimeError):
        validate_public_container(fixture(), ENV)


@pytest.mark.parametrize("drift", ["socket", "tls", "network", "privileged", "label", "env"])
def test_public_variant_does_not_widen_other_mounts_or_privileges(drift):
    value = public()
    if drift in ("socket", "tls"):
        target = "/run/proofflow-product-api" if drift == "socket" else "/etc/proofflow-product/tls"
        next(m for m in value["Mounts"] if m["Destination"] == target)["Source"] += "-changed"
    elif drift == "network":
        value["HostConfig"]["NetworkMode"] = "host"
    elif drift == "privileged":
        value["HostConfig"]["Privileged"] = True
    elif drift == "label":
        value["Config"]["Labels"]["proofflow.role"] = "product-api"
    else:
        value["Config"]["Env"].append("UNREVIEWED=1")
    with pytest.raises(RuntimeError):
        validate_public_container(value, ENV)
