"""Trusted test administration of the existing private product; no new cloud service."""

import json
import re
import ssl
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vultr_credit_guard import run as credit_guard  # noqa: E402
from vultr_phase1 import PRIVATE, Admin  # noqa: E402

from api.app.auth import SessionSecrets, csrf_digest, session_digest  # noqa: E402

ORIGIN = "https://127.0.0.1:18443"


def require(value, code):
    if not value:
        raise RuntimeError(code)


class LiveSession:
    def __enter__(self):
        self.admin, self.tunnel, self.client = Admin(), None, None
        self.opened = False
        try:
            self.credit = credit_guard(self.admin, datetime.now(UTC))
            require(
                self.credit["credit_guard"] == "within_early_cutoff", "CREDIT_GUARD_NOT_ADMITTING"
            )
            require(
                self.host("cat /etc/machine-id").decode() == self.admin.state["control_machine_id"],
                "CONTROL_IDENTITY_CHANGED",
            )
            self.policy = json.loads(
                self.sql("SELECT row_to_json(p) FROM pf_product.execution_policy p;")
            )
            require(not self.policy["enabled"], "ADMISSION_MUST_START_CLOSED")
            require(
                self.sql(
                    "SELECT count(*) FROM pf_product.repairs WHERE state IN "
                    "('QUEUED','RUNNING','RECONCILING');"
                )
                == b"0",
                "REPAIR_NOT_IDLE",
            )
            args = [
                "C:/Windows/System32/OpenSSH/ssh.exe",
                "-F",
                "NUL",
                "-N",
                "-o",
                "BatchMode=yes",
                "-o",
                "StrictHostKeyChecking=yes",
                "-o",
                "HostKeyAlgorithms=ssh-ed25519",
                "-o",
                "IdentitiesOnly=yes",
                "-o",
                "ExitOnForwardFailure=yes",
                "-o",
                "ConnectTimeout=10",
                "-o",
                "UserKnownHostsFile=" + str(PRIVATE / "known_hosts"),
                "-p",
                "443",
                "-i",
                str(PRIVATE / "operator_ed25519"),
                "-L",
                "127.0.0.1:18443:/run/proofflow-product-api/api.sock",
                "root@" + self.admin.state["hosts"]["control"]["address"],
            ]
            self.tunnel = subprocess.Popen(  # noqa: S603 - fixed pinned SSH, no candidate argv
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            for attempt in range(40):
                try:
                    self.cert = ssl.get_server_certificate(
                        ("127.0.0.1", 18443), ca_certs=str(PRIVATE / "tls/ca.pem"), timeout=2
                    )
                    break
                except OSError:
                    if self.tunnel.poll() is not None or attempt == 39:
                        raise RuntimeError("PRIVATE_TUNNEL_UNAVAILABLE") from None
                    time.sleep(0.25)
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def host(self, command, raw=None):
        result = self.admin.host("control", command, stdin=raw, timeout=60)
        if result.returncode:
            (PRIVATE / "evidence/phase3-final-host-failure.txt").write_bytes(result.stderr)
            raise RuntimeError("PRIVATE_HOST_OPERATION_FAILED")
        return result.stdout.strip()

    def sql(self, statement, database="proofflow_product"):
        require(database in ("proofflow_product", "proofflow_budget"), "DATABASE_NOT_ALLOWED")
        return self.host(
            "docker exec -i --user=70:70 proofflow-budget psql -X -qAt "
            "-h /run/proofflow-budget -U postgres -d " + database + " --set ON_ERROR_STOP=1",
            statement.encode(),
        )

    def login(self, workspace):
        self.workspace, self.secret = str(UUID(str(workspace))), SessionSecrets.create()
        self.sql(
            "SET ROLE pf_product_provisioner; "
            f"SELECT pf_product.create_session('{self.workspace}',"
            f"'{session_digest(self.secret.token)}',"
            f"'{csrf_digest(self.secret.csrf)}',clock_timestamp()+interval '40 minutes');"
        )
        if self.client:
            self.client.close()
        self.client = httpx.Client(
            base_url=ORIGIN,
            trust_env=False,
            timeout=20,
            verify=ssl.create_default_context(cafile=str(PRIVATE / "tls/ca.pem")),
            headers={
                "Cookie": "__Host-proofflow=" + self.secret.token,
                "Origin": ORIGIN,
                "X-ProofFlow-CSRF": self.secret.csrf,
            },
        )
        return self.client

    def admission(self, enabled):
        require(
            all(
                re.fullmatch("[a-f0-9]{64}", self.policy[k])
                for k in ("runtime_sha256", "verifier_sha256")
            ),
            "POLICY_IDENTITY_INVALID",
        )
        self.sql(
            "SET ROLE pf_product_provisioner; SELECT pf_product.configure_execution('"
            + self.policy["runtime_sha256"]
            + "','"
            + self.policy["verifier_sha256"]
            + "',"
            + ("true" if enabled else "false")
            + ");"
        )
        self.opened = enabled

    def __exit__(self, *_):
        try:
            if self.opened:
                self.admission(False)
        finally:
            if self.client:
                self.client.close()
            if self.tunnel:
                self.tunnel.terminate()
                self.tunnel.wait(timeout=10)
            self.admin.close()
