"""Controller doubles, no external calls; SQL checks enforce the durable authority separately."""

import asyncio
import copy
import hashlib
from dataclasses import asdict
from uuid import uuid4

import pytest

from api.app.product_store import ProductFailure
from integrations.github_app import GitHubConfig, GitHubFailure, GitHubUncertain
from orchestrator.github_dispatcher import GitHubDispatcher, inspection


class App:
    config = GitHubConfig("Iv1.fixture", 12, 34)

    def __init__(self):
        self.head = None
        self.writes = []
        self.uncertain = False
        self.accept = True
        self.base = "a" * 40

    async def token(self):
        return "fixture-token"

    async def inspect_base(self, token):
        return {
            "base_sha": self.base,
            "base_tree_sha": "b" * 40,
            "prior_blob": None,
            "original": b"",
        }

    async def read_branch(self, *args):
        return self.head

    async def request(self, method, path, token, payload):
        self.writes.append((method, path, payload))
        if self.accept:
            self.head = payload["sha"]
        if self.uncertain:
            raise GitHubUncertain("GITHUB_WRITE_UNCONFIRMED")
        return {"not_evidence": "intentionally untrusted reply"}


class Store:
    def __init__(self, job):
        self.job, self.calls = job, []
        self.fail_begin = False
        self.fail_record = False

    async def call(self, op, *args):
        self.calls.append((op, args))
        if op == "pr_claim":
            return (copy.deepcopy(self.job),)
        if op == "pr_begin":
            self.job["state"] = "BRANCH_PENDING"
            if self.fail_begin:
                raise ProductFailure("PRODUCT_OPERATION_UNCERTAIN")
            return (
                {
                    "method": "POST",
                    "path": "/repos/arslanabdulghaffar/ProofFlow-Demo/git/refs",
                    "payload": {
                        "ref": "refs/heads/proofflow/intent-" + self.job["id"].replace("-", ""),
                        "sha": "a" * 40,
                    },
                },
            )
        if op == "pr_readback":
            if self.fail_record:
                raise ProductFailure("PRODUCT_OPERATION_UNCERTAIN")
            self.job["state"] = "BRANCH_READY"
        return (True,)


def fixture(state="APPROVED"):
    source = "# inert synthetic bytes\n"
    app = App()
    job = {
        "id": str(uuid4()),
        "workspace_id": str(uuid4()),
        "generation": 1,
        "state": state,
        "configuration": asdict(app.config),
        "candidate_source": source,
        "binding": {"candidate_sha256": hashlib.sha256(source.encode()).hexdigest()},
        "preview": {"candidate_source": source, "inspection": {"base_sha": "a" * 40}},
        "head_sha": None,
    }
    store = Store(job)
    return GitHubDispatcher(store, app), store, app


@pytest.mark.parametrize("accept", [True, False])
def test_uncertain_write_recovery_only_reads_and_never_resends(accept):
    async def check():
        dispatcher, store, app = fixture()
        app.uncertain, app.accept = True, accept
        assert await dispatcher.once()
        assert len(app.writes) == 1
        if accept:
            assert store.job["state"] == "BRANCH_READY"
            assert any(op == "pr_readback" for op, _ in store.calls)
        else:
            assert store.job["state"] == "BRANCH_PENDING"
            assert await dispatcher.once()
            assert len(app.writes) == 1
            assert any(op == "pr_defer" and args[-1] is False for op, args in store.calls)

    asyncio.run(check())


def test_lost_db_preparation_ack_never_sends_external_write():
    async def check():
        dispatcher, store, app = fixture()
        store.fail_begin = True
        assert await dispatcher.once()
        assert not app.writes and store.job["state"] == "BRANCH_PENDING"
        store.fail_begin = False
        assert await dispatcher.once()
        assert not app.writes

    asyncio.run(check())


def test_lost_readback_ack_only_reconciles_same_branch():
    async def check():
        dispatcher, store, app = fixture()
        store.fail_record = True
        assert await dispatcher.once()
        assert len(app.writes) == 1 and store.job["state"] == "BRANCH_PENDING"
        store.fail_record = False
        assert await dispatcher.once()
        assert len(app.writes) == 1 and store.job["state"] == "BRANCH_READY"

    asyncio.run(check())


def test_base_change_stops_before_preparing_a_write():
    async def check():
        dispatcher, store, app = fixture()
        app.base = "c" * 40
        assert await dispatcher.once()
        assert not app.writes and not any(op == "pr_begin" for op, _ in store.calls)
        assert store.calls[-1][0] == "pr_defer" and store.calls[-1][1][-1] is True

    asyncio.run(check())


def test_inspection_diff_is_inert_fixed_path_and_no_change_rejected():
    base = {"base_sha": "a" * 40, "base_tree_sha": "b" * 40, "prior_blob": None, "original": b""}
    result = inspection(base, b"# inert\n")
    assert result["diff"].startswith("--- a/pipeline.py\n+++ b/pipeline.py\n")
    with pytest.raises(GitHubFailure, match="GITHUB_NO_CHANGE"):
        inspection({**base, "original": b"# inert\n"}, b"# inert\n")
