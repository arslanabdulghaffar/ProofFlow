"""Pure request/OCI policy tests: no runtime, host mutation or candidate execution."""

from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest

from worker.protocol import ExecutionRequest, SupervisorError, execution_name
from worker.runtime import RuntimePolicy, oci_config


def request():
    return ExecutionRequest(uuid4(), uuid4(), 1, b"# inert", b"", b"", b"{}")


def test_exact_inputs_and_rollup_are_manifest_bound():
    item = request()
    digest = item.manifest_hash()
    changes = [replace(item, pipeline=b"# other"), replace(item, requirements=b'{"x":1}'),
               replace(item, transactions=b"x"), replace(item, customers=b"x"),
               replace(item, include_rollups=True), replace(item, generation=2)]
    assert all(other.manifest_hash() != digest for other in changes)
    assert execution_name(item.execution_id) == "proofflow-exec-" + item.execution_id.hex


@pytest.mark.parametrize("change", [{"generation": True}, {"generation": 0},
                                   {"include_rollups": "yes"}, {"pipeline": "text"},
                                   {"pipeline": b"x" * 16385},
                                   {"requirements": b"x" * 32769},
                                   {"execution_id": "../../host"}])
def test_invalid_request_cannot_be_admitted(change):
    with pytest.raises(SupervisorError):
        replace(request(), **change).manifest_hash()


def test_prepared_input_aggregate_bound():
    with pytest.raises(SupervisorError, match="STAGED_INPUT_LIMIT"):
        replace(request(), transactions=b"x" * (10 * 1024 * 1024), customers=b"x").manifest_hash()


def test_oci_fixed_mounts_capabilities_and_scratch_sharing():
    policy = RuntimePolicy("a" * 32, "b" * 64, "c" * 64, Path("/trusted/rootfs"))
    item = request()
    config = oci_config(policy, item, Path("/trusted/execution"))
    assert config["root"]["readonly"] is True
    assert config["process"]["user"] == {"uid": 10001, "gid": 10001, "additionalGids": []}
    assert not any(config["process"]["capabilities"].values())
    mounts = {mount["destination"]: mount for mount in config["mounts"]}
    assert "ro" in mounts["/input"]["options"]
    assert mounts["/scratch"]["source"] == mounts["/dev/shm"]["source"]  # noqa: S108 - guest mount
    assert mounts["/scratch"]["source"] == mounts["/tmp"]["source"]  # noqa: S108
    assert "path" not in config["linux"]["namespaces"][0]
    assert "--rollups" not in config["process"]["args"]
    assert oci_config(policy, replace(item, include_rollups=True), Path("/trusted/execution"))[
        "process"]["args"][-1] == "--rollups"
