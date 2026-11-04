"""Admin provisions short-lived synthetic probe sessions; all job work uses real HTTP/queue."""

import base64
import hashlib
import json
import shlex
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vultr_credit_guard import run as credit_guard  # noqa: E402
from vultr_phase1 import PRIVATE, ROOT, Admin  # noqa: E402

from api.app.auth import SessionSecrets, csrf_digest, session_digest  # noqa: E402
from contracts.policy import parse_contract  # noqa: E402

RUNTIME = "04725fb06c6b3f8005c744ba78c1b2f632033d2309783a5198e8c453174a7188"
VERIFIER = "82ea34b7184e893907626f38a62f558d2fd48890a86caae2c860eec4c4c7a37f"


def main():
    identifier = uuid4().hex
    workspace, foreign = uuid4(), uuid4()
    secret, other = SessionSecrets.create(), SessionSecrets.create()
    contract = json.loads((ROOT / "contracts/examples/synthetic-v1.1.json").read_bytes())
    transactions = (b"merchant_id,transaction_id,customer_id,amount,currency,occurred_at\n"
        b"A,t1,shared,1.00,USD,2026-11-01T00:00:00Z\n"
        b"B,t2,shared,2.00,USD,2026-11-01T00:00:00Z\n")
    customers = (b"merchant_id,customer_id,canonical_customer_id\n"
                 b"A,shared,owner-A\nB,shared,owner-B\n")
    def case(name, fixture, tx, customer, policy, expected):
        parse_contract(json.dumps(policy).encode())  # Probe must obey the frozen policy.
        value = {"name": name, "expected": expected, "idempotency_key": str(uuid4())}
        blobs = {"pipeline": (ROOT / "tests/fixtures/phase2" / (fixture + ".py.txt")).read_bytes(),
                 "transactions": tx, "customers": customer, "contract": json.dumps(policy).encode()}
        return {**value, **{key: base64.b64encode(raw).decode() for key, raw in blobs.items()}}
    cases = [case("wrong_owner", "wrong_owner", transactions, customers, contract, "mismatch")]
    held = json.loads(json.dumps(contract))
    held["downstream"]["customer_attributes"] = ["segment"]
    held["downstream"]["occurred_at_from_utc"] = "2026-11-02T00:00:00.000000Z"
    held["downstream"]["occurred_at_before_utc"] = "2026-11-03T00:00:00.000000Z"
    cases.append(case("excluded_missing_attribute", "correct_held", transactions,
        b"merchant_id,customer_id,canonical_customer_id,segment\n"
        b"A,shared,owner-A,\nB,shared,owner-B,\n", held, "held"))
    cases.append(case("invalid_csv", "wrong_owner", b"not,the,approved,columns\nx,y,z,w\n",
                      customers, contract, "input_rejected"))
    payload = {"workspace": str(workspace), "session": secret.token, "csrf": secret.csrf,
               "foreign_session": other.token, "cases": cases}
    intent = {"probe": identifier, "workspace": str(workspace), "foreign_workspace": str(foreign),
              "cases": [{"name": c["name"], "idempotency_key": c["idempotency_key"]}
                        for c in cases],
              "observed_at": datetime.now(UTC).isoformat(), "fixture_only": True}
    path = PRIVATE / "evidence" / (identifier + ".product-intent.json")
    with path.open("x", encoding="utf-8") as file:
        json.dump(intent, file, sort_keys=True)
    admin = Admin()
    try:
        if credit_guard(admin, datetime.now(UTC)).get("credit_guard") != "within_early_cutoff":
            raise RuntimeError("CREDIT_GUARD_NOT_ADMITTING")
        def host(command, raw=None, timeout=45):
            result = admin.host("control", command, stdin=raw, timeout=timeout)
            if result.returncode:
                # Fixed script exceptions contain no credential values. Save diagnostics privately.
                (PRIVATE / "evidence" / (identifier + ".product-failure.txt")).write_bytes(
                    result.stdout + result.stderr)
                raise RuntimeError("PRODUCT_PROBE_FAILED_RECONCILE_NO_AUTOMATIC_RETRY")
            return result.stdout
        if host("cat /etc/machine-id").decode().strip() != admin.state["control_machine_id"]:
            raise RuntimeError("DESIGNATED_CONTROL_CHANGED")
        psql = ("docker exec -i --user=70:70 proofflow-budget psql -X -qAt "
                "-h /run/proofflow-budget -U postgres -d proofflow_product --set ON_ERROR_STOP=1")
        policy = host(psql, b"SELECT row_to_json(p) FROM pf_product.execution_policy p;\n").strip()
        if policy:
            current = json.loads(policy)
            if current["runtime_sha256"] != RUNTIME or current["verifier_sha256"] != VERIFIER:
                raise RuntimeError("EXISTING_EXECUTION_POLICY_CHANGED")
        sql = "BEGIN; SET ROLE pf_product_provisioner;\n"
        if not policy or not current["enabled"]:
            sql += f"SELECT pf_product.configure_execution('{RUNTIME}','{VERIFIER}',true);\n"
        for wid, creds in ((workspace, secret), (foreign, other)):
            sql += (f"SELECT pf_product.create_workspace('{wid}','operator',"
                    "clock_timestamp()+interval '23 hours');\n"
                    f"SELECT pf_product.create_session('{wid}','{session_digest(creds.token)}',"
                    f"'{csrf_digest(creds.csrf)}',clock_timestamp()+interval '2 hours');\n")
        host(psql, (sql + "COMMIT;\n").encode())
        script = (ROOT / "scripts/probe_product_http.py").read_text(encoding="utf-8")
        raw = host("docker exec -i proofflow-product-api python -c " + shlex.quote(script),
                   json.dumps(payload).encode(), timeout=330)
        result = json.loads(raw)
        invalid = str(UUID(result["jobs"][-1]["id"]))
        observed = host(psql, ("SELECT execution_id IS NULL AND manifest_sha256 IS NULL "
            "FROM pf_product.jobs WHERE workspace_id='" + str(workspace)
            + "' AND id='" + invalid
            + "';\n").encode()).strip()
        if observed != b"t":
            raise RuntimeError("INVALID_INPUT_EXECUTION_INTENT_PRESENT")
        result["probe"] = identifier
        result["observed_at"] = datetime.now(UTC).isoformat()
        result["client_sha256"] = hashlib.sha256(script.encode()).hexdigest()
        (PRIVATE / "evidence/product-http-latest.json").write_bytes(json.dumps(result).encode())
        print(json.dumps({"groups": len(result["checks"]), "jobs": len(result["jobs"]),
                          "provider_calls": 0}))
    finally:
        admin.close()


if __name__ == "__main__":
    main()
