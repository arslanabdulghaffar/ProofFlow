"""Real GitHub reads + disposable real SQL recovery; never writes to GitHub/production.

Models missing PR acknowledgement in an isolated database, then deliberately loses
one real GET response. This does not reproduce the original create-PR timeout.
"""

import asyncio
import hashlib
import json
import queue
import subprocess
import threading
import time
from datetime import UTC, datetime
from uuid import UUID

from prepare_github_app import protected_local
from product_live_session import PRIVATE, LiveSession, require
from vultr_phase1 import ROOT

from api.app.product_store import ProductFailure
from integrations.github_app import PERMISSIONS, GitHubApp, GitHubConfig, app_jwt
from orchestrator.github_dispatcher import GitHubDispatcher

INTENT = "b34e8d47-ab50-4527-a83f-c72feca85c40"


class ReadOnlyApp(GitHubApp):
    """Read-only installation token AND a pre-network write prohibition."""

    def __init__(self, config, pem):
        super().__init__(config, pem)
        self.calls, self.denied_writes = [], 0
        self.drop_next_pr_read, self.dropped = False, False
        self.cached_token = None

    async def request(self, method, path, token, payload=None, **kwargs):
        issuance = "/app/installations/" + str(self.config.installation_id) + "/access_tokens"
        if method != "GET":
            if not (method == "POST" and path == issuance and payload == {
                "repository_ids": [self.config.repository_id],
                "permissions": {"contents": "read", "pull_requests": "read"},
            }):
                self.denied_writes += 1
                raise RuntimeError("RECOVERY_GITHUB_WRITE_FORBIDDEN")
        value = await super().request(method, path, token, payload, **kwargs)
        self.calls.append({"method": method, "path": path})
        if self.drop_next_pr_read and path.startswith(self.config.prefix + "/pulls?"):
            require(type(value) is list and len(value) == 1, "EXISTING_PR_REQUIRED")
            self.drop_next_pr_read, self.dropped = False, True
            raise ProductFailure("PRODUCT_OPERATION_UNCERTAIN")
        return value

    async def token(self):
        if self.cached_token:
            return self.cached_token
        jwt = app_jwt(self.pem, self.config.client_id, int(datetime.now(UTC).timestamp()))
        installation = await self.request(
            "GET", "/app/installations/" + str(self.config.installation_id), jwt)
        require(installation.get("permissions") == PERMISSIONS
                and installation.get("repository_selection") == "selected"
                and installation.get("account", {}).get("login") == self.config.owner
                and installation.get("suspended_at") is None, "INSTALLATION_SCOPE_CHANGED")
        issued = await self.request(
            "POST", "/app/installations/" + str(self.config.installation_id) + "/access_tokens",
            jwt, {"repository_ids": [self.config.repository_id],
                  "permissions": {"contents": "read", "pull_requests": "read"}})
        require(issued.get("permissions") == {
            "contents": "read", "pull_requests": "read", "metadata": "read",
        }, "READ_ONLY_TOKEN_REQUIRED")
        expiry = datetime.fromisoformat(issued["expires_at"].replace("Z", "+00:00"))
        require(600 < (expiry - datetime.now(UTC)).total_seconds() <= 3660,
                "RECOVERY_TOKEN_LIFETIME_INVALID")
        token = issued["token"]
        allowed = await self.request("GET", "/installation/repositories?per_page=100", token)
        require(allowed.get("total_count") == 1 and len(allowed.get("repositories", [])) == 1,
                "READ_ONLY_TOKEN_REPOSITORY_SCOPE")
        repo = allowed["repositories"][0]
        require(repo.get("id") == self.config.repository_id and repo.get("private") is True,
                "PRIVATE_REPOSITORY_REQUIRED")
        self.cached_token = token
        return token


class Fixture:
    def __enter__(self):
        self.process = subprocess.Popen(  # noqa: S603 - fixed local fixture, no secrets
            ["C:/Windows/System32/wsl.exe", "-d", "Ubuntu-24.04", "--cd",
             "/mnt/a/hackathon/ProofFlow", "--", "python3", "-m",
             "scripts.github_recovery_fixture"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.replies = queue.Queue()

        def read():
            while raw := self.process.stdout.readline(1048577):
                self.replies.put(raw)
            self.replies.put(b"")

        threading.Thread(target=read, daemon=True).start()
        try:
            require(self.receive().get("ready") is True, "FIXTURE_START_FAILED")
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def receive(self):
        raw = self.replies.get(timeout=90)
        require(0 < len(raw) <= 1048576 and raw.endswith(b"\n"), "FIXTURE_REPLY_INVALID")
        return json.loads(raw)

    def request(self, operation, **values):
        raw = (json.dumps({"operation": operation, **values}) + "\n").encode()
        require(len(raw) <= 1048576, "FIXTURE_REQUEST_LIMIT")
        self.process.stdin.write(raw)
        self.process.stdin.flush()
        return self.receive()["result"]

    def __exit__(self, *_):
        try:
            if self.process.poll() is None:
                self.process.stdin.write(b'{"operation":"close"}\n')
                self.process.stdin.flush()
                require(self.receive() == {"cleanup": "confirmed"}, "FIXTURE_CLEANUP_UNPROVEN")
            require(self.process.wait(timeout=30) == 0, "FIXTURE_FAILED")
        finally:
            self.process.stdin.close()
            if self.process.poll() is None:
                self.process.terminate()  # Linux fixture has its own bounded finally cleanup.
            self.process.stdout.close()


class FixtureStore:
    def __init__(self, fixture):
        self.fixture = fixture
        self.operations = []

    async def call(self, operation, *args):
        require(operation in {"pr_claim", "pr_readback", "pr_defer"},
                "RECOVERY_STORE_WRITE_DISPATCH_FORBIDDEN")
        self.operations.append(operation)
        values = [v.obj if hasattr(v, "obj") else str(v) for v in args]
        return self.fixture.request("call", name=operation, args=values)


def production_snapshot(live):
    return json.loads(live.sql(
        "SELECT jsonb_build_object('intent',to_jsonb(p),'writes',(SELECT jsonb_agg(to_jsonb(w) "
        "ORDER BY stage) FROM pf_product.pr_writes w WHERE w.intent_id=p.id)) "
        "FROM pf_product.pr_intents p WHERE p.id='b34e8d47-ab50-4527-a83f-c72feca85c40';"))


def binding(job, controller):
    return {"w": job["workspace_id"], "intent": job["id"],
            "controller": str(controller), "fence": job["generation"]}


async def exercise(fixture, app, original):
    seeded = fixture.request("seed", snapshot=original)
    require(seeded["intent"]["state"] == "PR_PENDING", "RECOVERY_SEED_INVALID")
    store = FixtureStore(fixture)
    first = GitHubDispatcher(store, app)
    app.drop_next_pr_read = True
    started = time.monotonic()
    require(await first.once() and app.dropped, "REAL_READ_RESPONSE_NOT_DROPPED")
    pending = fixture.request("snapshot")
    job = pending["intent"]
    require(job["state"] == "PR_PENDING" and job["lease_owner"] == str(first.controller)
            and sum(w["confirmed_at"] is None for w in pending["writes"]) == 1,
            "LOST_READ_NOT_PENDING")
    fixture.request("deny_write", binding=binding(job, first.controller))
    fixture.request("restart")
    require(fixture.request("snapshot") == pending, "PENDING_RESTART_CHANGED")
    second = GitHubDispatcher(store, app)
    require((await store.call("pr_claim", second.controller))[0] is None,
            "LIVE_LEASE_STOLEN")
    print("Real read response discarded; database restart preserved pending state. "
          "Waiting for the unchanged 180-second lease.", flush=True)
    claimed = None
    while time.monotonic() - started < 240:
        await asyncio.sleep(5)
        claimed = (await store.call("pr_claim", second.controller))[0]
        if claimed:
            break
    require(claimed is not None and claimed["generation"] > job["generation"]
            and time.monotonic() - started >= 180, "NATURAL_LEASE_RECOVERY_NOT_PROVEN")
    fixture.request("stale", binding=binding(job, first.controller),
                    receipt=original["intent"]["result"])
    fixture.request("deny_write", binding=binding(claimed, second.controller))
    await second.run(claimed, (UUID(claimed["workspace_id"]), UUID(INTENT),
                               second.controller, claimed["generation"]))
    complete = fixture.request("snapshot")
    require(complete["intent"]["state"] == "COMPLETE"
            and complete["intent"]["result"] == original["intent"]["result"]
            and len(complete["writes"]) == 3
            and all(w["confirmed_at"] for w in complete["writes"]), "REAL_READBACK_FAILED")
    require([w["request_sha256"] for w in complete["writes"]]
            == [w["request_sha256"] for w in original["writes"]], "WRITE_INTENTS_CHANGED")
    fixture.request("restart")
    require(fixture.request("snapshot") == complete, "COMPLETE_RESTART_CHANGED")
    require(not await GitHubDispatcher(store, app).once(), "COMPLETE_REDISPATCHED")
    return {"pending_generation": job["generation"],
            "recovered_generation": complete["intent"]["generation"],
            "elapsed_seconds": round(time.monotonic() - started, 2),
            "result": complete["intent"]["result"], "write_intents": 3,
            "lost_real_get_reply": True, "pending_and_complete_restart": "passed",
            "stale_controller_and_new_write_rejected": True,
            "completed_redelivery_noop": True, "store_operations": sorted(set(store.operations))}


def main():
    destination = PRIVATE / "evidence/phase4-existing-pr-recovery-20261105.json"
    require(not destination.exists(), "RECOVERY_RECEIPT_EXISTS_RECONCILE")
    metadata, pem = protected_local()
    metadata["installation_id"] = int(metadata["installation_id"])
    app = ReadOnlyApp(GitHubConfig(**metadata, repository_id=1445855571), pem)
    with LiveSession() as live:
        before = production_snapshot(live)
        require(before["intent"]["state"] == "COMPLETE", "PRODUCTION_PR_NOT_COMPLETE")
        require(live.sql("SELECT bool_and(blocked) FROM pf_budget.accounts;", "proofflow_budget")
                == b"t", "INFERENCE_NOT_BLOCKED")
        # Bind local controller/adapter to the actual installed production source.
        for path in ("orchestrator/github_dispatcher.py", "integrations/github_app.py"):
            observed = live.host("docker exec proofflow-product-dispatcher sha256sum /app/" + path)
            expected = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
            require(observed.decode().split()[0] == expected,
                    "DEPLOYED_RECOVERY_SOURCE_CHANGED")
        with Fixture() as fixture:
            result = asyncio.run(exercise(fixture, app, before))
        require(production_snapshot(live) == before, "PRODUCTION_RECEIPTS_CHANGED")
        receipt = {"observed_at": datetime.now(UTC).isoformat(), "intent": INTENT,
                   "scenario": "isolated_pending_ack_fixture_real_sql_and_real_readonly_github",
                   "original_create_response_loss": "NOT_REPRODUCED",
                   "recovery": result, "fixture_cleanup": "confirmed",
                   "production_snapshot_unchanged": True,
                   "github_calls": app.calls, "github_mutations": 0,
                   "token_permissions": "contents/read,pull_requests/read,metadata/read",
                   "new_prs": 0, "new_cloud_resources": 0, "provider_calls": 0,
                   "credit": live.credit}
        destination.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(receipt))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("READ_ONLY_RECOVERY_DRILL_FAILED_RECONCILE") from None
