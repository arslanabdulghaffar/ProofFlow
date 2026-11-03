"""Trusted administrator one-time budget deployment; never retries partial setup."""

import json
from datetime import UTC, datetime
from uuid import uuid4

from vultr_phase1 import PRIVATE, ROOT, Admin

admin = Admin()
try:
    if admin.state.get("budget_install_intent"):
        raise RuntimeError("BUDGET_INSTALL_ALREADY_ATTEMPTED_REQUIRES_READBACK")
    if admin.state.get("credit_guard", {}).get("admission_closed"):
        raise RuntimeError("CREDIT_ADMISSION_CLOSED")

    def host(command, data=None, timeout=90):
        result = admin.host("control", command, stdin=data, timeout=timeout)
        if result.returncode:
            raise RuntimeError("BUDGET_DEPLOYMENT_FAILED_REQUIRES_READBACK")
        return result.stdout

    if host("cat /etc/machine-id").decode().strip() != admin.state["control_machine_id"]:
        raise RuntimeError("CONTROL_HOST_CHANGED")
    config = {
        "machine_id": admin.state["control_machine_id"],
        "account_id": str(uuid4()),
        "expires_at": admin.state["review_due_at"],
    }
    host("install -d -m 0700 /var/lib/proofflow-setup/postgres /var/lib/proofflow-setup/migrations")
    for name in ("postgresql.conf", "pg_hba.conf"):
        host(
            "umask 077; cat > /var/lib/proofflow-setup/postgres/" + name,
            (ROOT / "infra/postgres" / name).read_bytes(),
        )
    for name in ("001_budget.sql", "002_runtime_roles.sql", "003_probe_receipts.sql"):
        host(
            "umask 077; cat > /var/lib/proofflow-setup/migrations/" + name,
            (ROOT / "db/phase1" / name).read_bytes(),
        )
    host("umask 077; cat > /var/lib/proofflow-setup/budget-setup.json", json.dumps(config).encode())
    host(
        "umask 077; cat > /var/lib/proofflow-setup/install_budget_host.py",
        (ROOT / "scripts/install_budget_host.py").read_bytes(),
    )
    admin.state["budget_install_intent"] = {
        "started_at": datetime.now(UTC).isoformat(),
        "account_id": config["account_id"],
        "state": "OUTCOME_UNKNOWN",
    }
    admin.save()
    raw = host(
        "/usr/bin/python3 -I -S -B /var/lib/proofflow-setup/install_budget_host.py", timeout=180
    )
    receipt = json.loads(raw)
    admin.state["budget_install_intent"]["state"] = "INSTALLED_REQUIRES_ACCEPTANCE"
    admin.save()
    (PRIVATE / "evidence/budget-install.json").write_bytes(raw)
    print(json.dumps(receipt))
finally:
    admin.close()
