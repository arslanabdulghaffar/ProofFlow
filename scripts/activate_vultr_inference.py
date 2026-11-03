"""Create the authorized usage-only subscription and provision its control-host key.

No completion request here. Management credentials stay on the administrator PC;
the inference key is transferred only as SSH stdin, never logged or stored in Git.
"""

import hashlib
import json
from datetime import UTC, datetime

import httpx
from vultr_credit_guard import run as credit_check
from vultr_phase1 import LABEL, PRIVATE, Admin


def main():
    admin = Admin()
    try:
        credit = credit_check(admin, datetime.now(UTC))
        if credit["credit_guard"] != "within_early_cutoff":
            raise RuntimeError("CREDIT_ADMISSION_CLOSED")
        for name in ("budget-auth.json", "budget-restore.json"):
            if not (PRIVATE / "evidence" / name).is_file():
                raise RuntimeError("DEPLOYED_DATABASE_EVIDENCE_REQUIRED")
        label = LABEL + "-inference"
        existing = admin.request("GET", "/inference")["subscriptions"]
        if existing and "inference" not in admin.state.get("resources", {}):
            raise RuntimeError("EXISTING_SUBSCRIPTION_REQUIRES_READBACK")
        identifier = admin.create_once("inference", "/inference", {"label": label}, "subscription")
        subscription = admin.request("GET", "/inference/" + identifier)["subscription"]
        if subscription["id"] != identifier or subscription["label"] != label:
            raise RuntimeError("SUBSCRIPTION_IDENTITY_CHANGED")
        key = subscription["api_key"]
        if (
            type(key) is not str
            or not 32 <= len(key) <= 512
            or any(not 33 <= ord(char) <= 126 for char in key)
        ):
            raise RuntimeError("INVALID_INFERENCE_KEY")
        result = admin.host(
            "control",
            "set -C; umask 077; cat > /etc/proofflow/credentials/vultr-api-key",
            stdin=key.encode(),
        )
        if result.returncode:
            raise RuntimeError("INFERENCE_KEY_INSTALL_REQUIRES_READBACK")
        result = admin.host(
            "control",
            "chown 10001:10001 /etc/proofflow/credentials/vultr-api-key "
            "&& chmod 0400 /etc/proofflow/credentials/vultr-api-key",
        )
        if result.returncode:
            raise RuntimeError("INFERENCE_KEY_PERMISSION_FAILED")
        with httpx.Client(
            verify=True, trust_env=False, follow_redirects=False, timeout=20
        ) as client:
            with client.stream(
                "GET",
                "https://api.vultrinference.com/v1/models",
                headers={"Authorization": "Bearer " + key},
            ) as response:
                if response.status_code != 200:
                    raise RuntimeError("INFERENCE_MODELS_HTTP_REJECTED")
                raw = bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk)
                    if len(raw) > 4 * 1024 * 1024:
                        raise RuntimeError("INFERENCE_MODELS_LIMIT")
        models = json.loads(raw)
        selected = [m for m in models["data"] if m["id"] in ("qwen3.8-27b", "qwen3.8-flash-next")]
        if len(selected) != 2:
            raise RuntimeError("APPROVED_MODELS_NOT_AVAILABLE")
        evidence = {
            "observed_at": datetime.now(UTC).isoformat(),
            "catalog_sha256": hashlib.sha256(raw).hexdigest(),
            "models": selected,
            "subscription": "created_and_read_back",
            "completion_calls": 0,
            "credit_remaining_observed": credit["remaining_credit"],
        }
        (PRIVATE / "evidence/inference-models.json").write_text(
            json.dumps(evidence, sort_keys=True, indent=2)
        )
        admin.state["inference_credential_installed"] = True
        admin.save()
        print(json.dumps(evidence))
    finally:
        admin.close()


if __name__ == "__main__":
    main()
