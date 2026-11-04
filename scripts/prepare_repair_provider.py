"""Read existing subscription/catalogue and save a short-lived quote. No activation/call."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import httpx
from vultr_credit_guard import run as credit_guard
from vultr_phase1 import LABEL, PRIVATE, Admin


def main():
    admin = Admin()
    try:
        guard = credit_guard(admin, datetime.now(UTC))
        if guard["credit_guard"] != "within_early_cutoff":
            raise RuntimeError("CREDIT_ADMISSION_CLOSED")
        identifier = admin.state["resources"]["inference"]
        subscription = admin.request("GET", "/inference/" + identifier)["subscription"]
        if subscription["id"] != identifier or subscription["label"] != LABEL + "-inference":
            raise RuntimeError("SUBSCRIPTION_IDENTITY_CHANGED")
        with httpx.Client(
            verify=True, trust_env=False, follow_redirects=False, timeout=20
        ) as client:
            with client.stream(
                "GET",
                "https://api.vultrinference.com/v1/models",
                headers={"Authorization": "Bearer " + subscription["api_key"]},
            ) as response:
                if response.status_code != 200:
                    raise RuntimeError("MODEL_CATALOGUE_UNAVAILABLE")
                raw = bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk)
                    if len(raw) > 4 * 1024 * 1024:
                        raise RuntimeError("MODEL_CATALOGUE_LIMIT")
        model = next(m for m in json.loads(raw)["data"] if m["id"] == "qwen3.8-flash-next")
        if model.get("reasoning", {}).get("mandatory") is not False:
            raise RuntimeError("OPTIONAL_REASONING_REQUIRED")
        rates = []
        for direction in ("input_modalities", "output_modalities"):
            text = next(item for item in model[direction] if item["type"] == "text")
            price = text["pricing"][0]
            rate = Decimal(price["cost_usd"]) * 1000000000000
            if price["unit"] != "token" or rate != rate.to_integral_value() or rate <= 0:
                raise RuntimeError("UNREVIEWED_MODEL_RATE")
            rates.append(int(rate))
        # Existing reviewed rates only. A changed rate needs fresh engineering
        # review rather than silently treating the old quote as still current.
        if rates != [100000, 200000]:
            raise RuntimeError("MODEL_RATE_CHANGED")
        now = datetime.now(UTC)
        quote = {
            "model": model["id"],
            "input_micro_usd_per_million": rates[0],
            "output_micro_usd_per_million": rates[1],
            "observed_at": now.isoformat(),
            "valid_until": (now + timedelta(hours=1)).isoformat(),
            "evidence_sha256": hashlib.sha256(raw).hexdigest(),
        }
        config = {
            "account_id": str(UUID(admin.state["budget_install_intent"]["account_id"])),
            "quote": quote,
        }
        (PRIVATE / "repair-provider.json").write_bytes(json.dumps(config, sort_keys=True).encode())
        (PRIVATE / "evidence/repair-model-catalogue.json").write_bytes(
            json.dumps(
                {
                    "observed_at": now.isoformat(),
                    "catalog_sha256": quote["evidence_sha256"],
                    "model": model,
                    "credit": guard["remaining_credit"],
                    "completion_calls": 0,
                },
                sort_keys=True,
            ).encode()
        )
        print(
            json.dumps(
                {
                    "quote": quote,
                    "credit": guard["remaining_credit"],
                    "new_subscriptions": 0,
                    "completion_calls": 0,
                }
            )
        )
    finally:
        admin.close()


if __name__ == "__main__":
    main()
