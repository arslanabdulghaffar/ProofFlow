"""Synthetic Docker inspect records: reject concrete privilege/mount/resource drift."""

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from install_product_services import IMAGE, expected_mounts, validate_container  # noqa: E402

ENV = ["PYTHONDONTWRITEBYTECODE=1", "PYTHONUNBUFFERED=1"]


def fixture(role="api"):
    return {
        "Image": "sha256:" + IMAGE,
        "Config": {"User": "10003:10003", "WorkingDir": "/app", "Env": ENV[:],
                   "Labels": {"proofflow.role": "product-" + role}, "Entrypoint": None,
                   "Cmd": ["python", "-m", "api.app.product_bootstrap" if role == "api"
                           else "orchestrator.product_bootstrap"]},
        "HostConfig": {
            "ReadonlyRootfs": True, "Privileged": False, "CapDrop": ["ALL"], "CapAdd": None,
            "SecurityOpt": ["no-new-privileges"], "Memory": 402653184, "MemorySwap": 402653184,
            "NanoCpus": 1000000000, "PidsLimit": 64, "GroupAdd": ["10001"],
            "Ulimits": [{"Name": "core", "Soft": 0, "Hard": 0},
                        {"Name": "nofile", "Soft": 128, "Hard": 128}],
            "NetworkMode": "none" if role == "api" else "host", "PortBindings": {},
            "PublishAllPorts": False, "PidMode": "", "IpcMode": "private", "UTSMode": "",
            "UsernsMode": "", "CgroupnsMode": "private", "Runtime": "runc"},
        "Mounts": [{"Destination": dst, "Source": src, "RW": rw,
                    "Type": "bind", "Propagation": "rprivate"}
                   for dst, (src, rw) in expected_mounts(role).items()],
    }


@pytest.mark.parametrize("role", ["api", "dispatcher"])
def test_fixed_role_configuration_passes(role):
    validate_container(fixture(role), role, ENV)


@pytest.mark.parametrize("key,value", [
    ("Privileged", True), ("SecurityOpt", []), ("SecurityOpt", ["seccomp=unconfined"]),
    ("CapAdd", ["SYS_ADMIN"]), ("MemorySwap", -1), ("NanoCpus", 0), ("PidsLimit", -1),
    ("GroupAdd", ["0", "10001"]), ("NetworkMode", "host"), ("PidMode", "host"),
    ("IpcMode", "host"), ("CgroupnsMode", "host"), ("Runtime", "unreviewed"),
    ("Devices", [{"PathOnHost": "/dev/kvm"}]), ("Tmpfs", {"/app": "rw"}),
    ("Binds", ["/var/run/docker.sock:/docker.sock"]), ("VolumesFrom", ["other"]),
    ("Ulimits", [{"Name": "core", "Soft": -1, "Hard": -1}]),
])
def test_security_drift_cannot_be_accepted(key, value):
    item = fixture()
    item["HostConfig"][key] = value
    with pytest.raises(RuntimeError, match="PRODUCT_CONTAINER_CONFIGURATION_CHANGED"):
        validate_container(item, "api", ENV)


@pytest.mark.parametrize("mutation", ["source", "writable_secret", "extra", "duplicate",
                                     "propagation", "entrypoint", "env", "command"])
def test_mount_and_command_substitution_denied(mutation):
    item = copy.deepcopy(fixture())
    if mutation == "source":
        item["Mounts"][0]["Source"] = "/"
    elif mutation == "writable_secret":
        item["Mounts"][1]["RW"] = True
    elif mutation == "extra":
        item["Mounts"].append({"Destination": "/docker.sock", "Source": "/run/docker.sock",
                               "RW": True, "Type": "bind", "Propagation": "rprivate"})
    elif mutation == "duplicate":
        item["Mounts"].append(copy.deepcopy(item["Mounts"][0]))
    elif mutation == "propagation":
        item["Mounts"][0]["Propagation"] = "rshared"
    elif mutation == "entrypoint":
        item["Config"]["Entrypoint"] = ["/bin/sh"]
    elif mutation == "env":
        item["Config"]["Env"].append("PYTHONPATH=/untrusted")
    else:
        item["Config"]["Cmd"] = ["python", "-m", "untrusted"]
    with pytest.raises(RuntimeError, match="PRODUCT_CONTAINER_CONFIGURATION_CHANGED"):
        validate_container(item, "api", ENV)
