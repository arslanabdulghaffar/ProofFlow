"""Administrator composition of bounded, real deployed provider probes."""

import hashlib
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from deploy_control_images import CONTROL
from vultr_credit_guard import run as credit_check
from vultr_phase1 import PRIVATE, ROOT, Admin


def main():
    names = [
        f"{model}-{kind}"
        for model in ("dense", "flash")
        for kind in ("json", "coding", "ambiguity")
    ]
    names.extend(("dense-coding-extended", "flash-coding-extended"))
    if len(sys.argv) != 2 or sys.argv[1] not in names:
        raise RuntimeError("FIXED_PROBE_NAME_REQUIRED")
    name = sys.argv[1]
    admin = Admin()
    opened = False
    try:

        def host(command, payload=None, timeout=90):
            result = admin.host("control", command, stdin=payload, timeout=timeout)
            if result.returncode:
                # Scripts are trusted; exceptions deliberately omit secrets/raw HTTP.
                print(result.stderr.decode(errors="replace")[-2000:], file=sys.stderr)
                raise RuntimeError("DEPLOYED_PROVIDER_PROBE_FAILED_RECONCILE_NO_RESEND")
            return result.stdout

        account = str(UUID(admin.state["budget_install_intent"]["account_id"]))
        sql_command = (
            "docker exec -i --user=70:70 proofflow-budget psql -X -qAt "
            "-h /run/proofflow-budget -U postgres -d proofflow_budget "
            "--set ON_ERROR_STOP=1 --set=account=" + account
        )
        credit = credit_check(admin, datetime.now(UTC))
        if credit["credit_guard"] != "within_early_cutoff":
            raise RuntimeError("CREDIT_ADMISSION_CLOSED")
        if host("cat /etc/machine-id").decode().strip() != admin.state["control_machine_id"]:
            raise RuntimeError("CONTROL_HOST_CHANGED")
        config_path = PRIVATE / "inference-probes.json"
        if not config_path.exists():
            catalog = json.loads((PRIVATE / "evidence/inference-models.json").read_bytes())
            observed = datetime.fromisoformat(catalog["observed_at"])
            if datetime.now(UTC) - observed > timedelta(hours=1):
                raise RuntimeError("FRESH_MODEL_RATE_EVIDENCE_REQUIRED")
            probes = {}
            for short, model in (("dense", "qwen3.8-27b"), ("flash", "qwen3.8-flash-next")):
                metadata = next(m for m in catalog["models"] if m["id"] == model)
                rates = []
                for direction in ("input_modalities", "output_modalities"):
                    text = next(m for m in metadata[direction] if m["type"] == "text")
                    price = text["pricing"][0]
                    if price["unit"] != "token":
                        raise RuntimeError("UNKNOWN_RATE_UNIT")
                    rate = Decimal(price["cost_usd"]) * 1000000000000
                    if rate != rate.to_integral_value() or rate <= 0:
                        raise RuntimeError("INVALID_RATE")
                    rates.append(int(rate))
                quote = {
                    "model": model,
                    "input_micro_usd_per_million": rates[0],
                    "output_micro_usd_per_million": rates[1],
                    "observed_at": observed.isoformat(),
                    "valid_until": (observed + timedelta(hours=1)).isoformat(),
                    "evidence_sha256": catalog["catalog_sha256"],
                }
                for kind in ("json", "coding", "ambiguity"):
                    probes[short + "-" + kind] = {
                        "kind": kind,
                        "quote": quote,
                        "request_id": str(uuid4()),
                    }
            config = {"account_id": account, "probes": probes}
            with config_path.open("xb") as file:
                file.write(json.dumps(config, sort_keys=True).encode())
                file.flush()
                os.fsync(file.fileno())
        config = json.loads(config_path.read_bytes())
        if config["account_id"] != account:
            raise RuntimeError("BUDGET_ACCOUNT_CHANGED")
        if name.endswith("-extended") and name not in config["probes"]:
            # New request, not a replay or alteration of a rejected provider result.
            # The adapter's approved maximum remains 8192 and the ledger reserves it.
            config["probes"][name] = config["probes"][name.removesuffix("-extended")] | {
                "request_id": str(uuid4()),
                "max_completion_tokens": 8192,
            }
            temporary = config_path.with_suffix(".new")
            with temporary.open("xb") as file:
                file.write(json.dumps(config, sort_keys=True).encode())
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, config_path)
        path = "/var/lib/proofflow-provider-probe"
        host(
            "install -d -m 0755 "
            + path
            + "; install -d -o 10001 -g 10001 -m 0700 "
            + path
            + "/results"
        )
        script = (ROOT / "scripts/probe_vultr_deployed.py").read_bytes()
        host("cat > " + path + "/probe.py && chmod 0444 " + path + "/probe.py", script)
        host(
            "cat > " + path + "/config.json && chmod 0444 " + path + "/config.json",
            json.dumps(config, sort_keys=True).encode(),
        )
        if (
            host("sha256sum " + path + "/probe.py").decode().split()[0]
            != hashlib.sha256(script).hexdigest()
        ):
            raise RuntimeError("PROBE_SOURCE_CHANGED")
        # Real preconditions checked; this only opens the infrastructure ledger.
        # It never marks any candidate, verification or phase as successful.
        host(
            sql_command,
            (
                b"UPDATE pf_budget.accounts SET blocked=false WHERE id=:'account' "
                b"AND expires_at>clock_timestamp();"
            ),
        )
        opened = True
        raw = host(
            "docker run --rm --pull=never --name proofflow-provider-probe "
            "--label proofflow.role=provider-probe --user=10001:10001 "
            "--read-only --cap-drop=ALL --security-opt=no-new-privileges "
            "--memory=256m --memory-swap=256m --cpus=0.5 --pids-limit=32 "
            "--ulimit core=0 --ulimit nofile=128:128 --log-driver=none "
            "--mount type=bind,src=/run/proofflow-budget,dst=/run/proofflow-budget "
            "--mount type=bind,src=/etc/proofflow/credentials,"
            "dst=/etc/proofflow/credentials,readonly "
            "--mount type=bind,src=" + path + "/probe.py,dst=/app/probe.py,readonly "
            "--mount type=bind,src=" + path + "/config.json,dst=/probe/config.json,readonly "
            "--mount type=bind,src=" + path + "/results,dst=/probe/results "
            "sha256:" + CONTROL + " python /app/probe.py " + name
        )
        result = host("cat " + path + "/results/" + name + ".json")
        (PRIVATE / "evidence" / ("inference-" + name + ".json")).write_bytes(result)
        print(raw.decode())
    finally:
        try:
            if opened:
                result = admin.host(
                    "control",
                    sql_command,
                    stdin=b"UPDATE pf_budget.accounts SET blocked=true WHERE id=:'account';",
                )
                if result.returncode:
                    raise RuntimeError("BUDGET_REBLOCK_REQUIRES_ADMINISTRATOR")
        finally:
            admin.close()


if __name__ == "__main__":
    main()
