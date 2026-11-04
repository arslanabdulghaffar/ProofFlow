"""Single-use committed GitHub writes; uncertain calls only receive bounded readback."""

import asyncio
import difflib
import hashlib
from dataclasses import asdict
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from api.app.product_store import ProductFailure
from integrations.github_app import GitHubFailure, GitHubUncertain, require


def inspection(base, source):
    require(type(source) is bytes and 0 < len(source) <= 16384, "GITHUB_CANDIDATE_INVALID")
    original = base["original"]
    require(original != source, "GITHUB_NO_CHANGE")
    try:
        before, after = original.decode("utf-8"), source.decode("utf-8")
    except UnicodeError:
        raise GitHubFailure("GITHUB_SOURCE_ENCODING_INVALID") from None
    diff = "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile="a/pipeline.py",
            tofile="b/pipeline.py",
        )
    )
    require(len(diff.encode()) <= 131072, "GITHUB_DIFF_LIMIT")
    return {
        "base_sha": base["base_sha"],
        "base_tree_sha": base["base_tree_sha"],
        "prior_blob": base["prior_blob"],
        "original_sha256": hashlib.sha256(original).hexdigest(),
        "diff": diff,
    }


class GitHubDispatcher:
    def __init__(self, store, app):
        self.store, self.app = store, app
        self.controller = uuid4()

    async def once(self):
        row = await self.store.call("pr_claim", self.controller)
        if row is None or row[0] is None:
            return False
        job = row[0]
        binding = (UUID(job["workspace_id"]), UUID(job["id"]), self.controller, job["generation"])
        try:
            # 180s DB lease; total operation lifetime120s, no background writes.
            async with asyncio.timeout(120):
                await self.run(job, binding)
        except ProductFailure:
            # Lost DB acknowledgement/fence: leave durable stage for the next claim.
            # In particular do not send a write whose preparation may not have committed.
            return True
        except (GitHubFailure, TimeoutError) as error:
            code = str(error) if isinstance(error, GitHubFailure) else "GITHUB_OPERATION_TIMEOUT"
            transient = code in (
                "GITHUB_READ_UNAVAILABLE",
                "GITHUB_READ_REJECTED",
                "GITHUB_WRITE_UNCONFIRMED",
                "GITHUB_READBACK_PENDING",
                "GITHUB_OPERATION_TIMEOUT",
            )
            try:
                await self.store.call("pr_defer", *binding, code, not transient)
            except ProductFailure:
                pass  # Claim expires; no repeated external write.
        return True

    async def run(self, job, binding):
        require(job["configuration"] == asdict(self.app.config), "GITHUB_CONFIGURATION_CHANGED")
        source = job["candidate_source"].encode("utf-8")
        require(
            hashlib.sha256(source).hexdigest() == job["binding"]["candidate_sha256"],
            "GITHUB_CANDIDATE_CHANGED",
        )
        token = await self.app.token()
        if job["state"] == "PREPARING":
            base = await self.app.inspect_base(token)
            await self.store.call("pr_preview_record", *binding, Jsonb(inspection(base, source)))
            return
        preview = job["preview"]
        require(preview["candidate_source"].encode("utf-8") == source, "GITHUB_CANDIDATE_CHANGED")
        if job["state"].endswith("_PENDING"):
            # Even revoked/expired approval permits read-only reconciliation of a prior write.
            await self.reconcile(job, binding, token, source, job["state"].split("_")[0].lower())
            return
        stage = {"APPROVED": "branch", "BRANCH_READY": "commit", "COMMIT_READY": "pr"}.get(
            job["state"]
        )
        require(stage is not None, "GITHUB_STAGE_INVALID")
        base = await self.app.inspect_base(token)
        require(base["base_sha"] == preview["inspection"]["base_sha"], "GITHUB_BASE_CHANGED")
        head = await self.app.read_branch(token, job["id"])
        if stage == "branch":
            require(head is None, "GITHUB_BRANCH_ALREADY_EXISTS")
        elif stage == "commit":
            require(head == base["base_sha"], "GITHUB_BRANCH_CHANGED")
        else:
            require(head == job["head_sha"], "GITHUB_BRANCH_CHANGED")
            await self.app.verify_commit(token, job["id"], head, base["base_sha"], source)
            require(await self.app.find_pr(token, job["id"]) is None, "GITHUB_PR_ALREADY_EXISTS")
        # Last local authority check and unique dispatch record are one transaction.
        # A revocation after this committed point cannot recall an already authorized HTTP call.
        request = (await self.store.call("pr_begin", *binding, stage))[0]
        try:
            await self.app.request(request["method"], request["path"], token, request["payload"])
        except GitHubUncertain:
            pass
        # A successful HTTP reply alone is never accepted as completion.
        await self.reconcile(job, binding, token, source, stage)

    async def reconcile(self, job, binding, token, source, stage):
        preview = job["preview"]
        base_sha = preview["inspection"]["base_sha"]
        # Check private repo/base again even for uncertain writes. Changed identity is a review gap.
        base = await self.app.inspect_base(token)
        require(base["base_sha"] == base_sha, "GITHUB_BASE_CHANGED")
        head = await self.app.read_branch(token, job["id"])
        if head is None:
            raise GitHubFailure("GITHUB_READBACK_PENDING")
        if stage == "branch":
            require(head == base_sha, "GITHUB_BRANCH_CHANGED")
            receipt = {"head_sha": head, "base_sha": base_sha}
        else:
            if head == base_sha:
                raise GitHubFailure("GITHUB_READBACK_PENDING")
            await self.app.verify_commit(token, job["id"], head, base_sha, source)
            receipt = {"head_sha": head, "base_sha": base_sha}
            if stage == "pr":
                require(head == job["head_sha"], "GITHUB_BRANCH_CHANGED")
                value = await self.app.find_pr(token, job["id"])
                if value is None:
                    raise GitHubFailure("GITHUB_READBACK_PENDING")
                receipt = self.app.verify_pr(
                    value, job["id"], head, base_sha, preview["title"], preview["body"]
                )
        await self.store.call("pr_readback", *binding, stage, Jsonb(receipt))
