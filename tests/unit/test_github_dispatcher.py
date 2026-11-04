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
        self.pr = None

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
            if path.endswith("/git/refs"):
                self.head = payload["sha"]
            elif path.endswith("/contents/pipeline.py"):
                self.head = "c" * 40
            else:
                assert path.endswith("/pulls")
                self.pr = {"number": 1}
        if self.uncertain:
            raise GitHubUncertain("GITHUB_WRITE_UNCONFIRMED")
        return {"not_evidence": "intentionally untrusted reply"}

    async def verify_commit(self, token, intent, head, base, source):
        assert head == "c" * 40 and base == self.base

    async def find_pr(self, token, intent):
        return self.pr

    def verify_pr(self, value, intent, head, base, title, body):
        assert value == self.pr and title == "fixture" and body == "inert"
        return {"head_sha": head, "base_sha": base, "draft": True, "number": 1}


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
            stage = args[-1]
            self.job["state"] = stage.upper() + "_PENDING"
            if self.fail_begin:
                raise ProductFailure("PRODUCT_OPERATION_UNCERTAIN")
            if stage != "branch":
                return ({"method": "PUT" if stage == "commit" else "POST",
                         "path": "/repos/arslanabdulghaffar/ProofFlow-Demo/"
                         + ("contents/pipeline.py" if stage == "commit" else "pulls"),
                         "payload": {}},)
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
            stage = args[-2]
            self.job["state"] = {
                "branch": "BRANCH_READY", "commit": "COMMIT_READY", "pr": "COMPLETE"
            }[stage]
            self.job["head_sha"] = args[-1].obj["head_sha"]
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
        "preview": {"candidate_source": source, "inspection": {"base_sha": "a" * 40},
                    "title": "fixture", "body": "inert"},
        "head_sha": None,
    }
    if state == "BRANCH_READY":
        app.head = "a" * 40
        job["head_sha"] = app.head
    elif state == "COMMIT_READY":
        app.head = "c" * 40
        job["head_sha"] = app.head
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


@pytest.mark.parametrize("state", ["APPROVED", "BRANCH_READY", "COMMIT_READY"])
@pytest.mark.parametrize("fault", ["unaccepted", "accepted", "begin_ack", "readback_ack"])
def test_every_write_stage_recovers_without_resending(state, fault):
    async def check():
        dispatcher, store, app = fixture(state)
        app.uncertain = fault in ("accepted", "unaccepted")
        app.accept = fault != "unaccepted"
        store.fail_begin = fault == "begin_ack"
        store.fail_record = fault == "readback_ack"
        assert await dispatcher.once()
        expected_writes = 0 if fault == "begin_ack" else 1
        assert len(app.writes) == expected_writes
        pending = store.job["state"].endswith("_PENDING")
        assert pending == (fault != "accepted")
        if pending:
            store.fail_begin = store.fail_record = False
            # A fresh controller sees the durable pending stage, not the prior process memory.
            recovered = GitHubDispatcher(store, app)
            assert await recovered.once()
            assert len(app.writes) == expected_writes
            if fault == "readback_ack":
                assert not store.job["state"].endswith("_PENDING")
            else:
                assert store.job["state"].endswith("_PENDING")

    asyncio.run(check())
