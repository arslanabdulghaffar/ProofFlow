"""Read the fixed provider catalogue; no completion, subscription or management call."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx

from orchestrator.provider_setup import load_provider_secrets


def catalogue_quote(raw, now):
    models = [m for m in json.loads(raw)["data"] if m["id"] == "qwen3.8-flash-next"]
    if len(models) != 1 or models[0].get("reasoning", {}).get("mandatory") is not False:
        raise RuntimeError("JUDGE_MODEL_CHANGED")
    model = models[0]
    rates = []
    for direction in ("input_modalities", "output_modalities"):
        items = [item for item in model[direction] if item["type"] == "text"]
        if len(items) != 1 or len(items[0]["pricing"]) != 1:
            raise RuntimeError("JUDGE_RATE_CHANGED")
        price = items[0]["pricing"][0]
        rate = Decimal(price["cost_usd"]) * 1000000000000
        if price["unit"] != "token" or rate != rate.to_integral_value():
            raise RuntimeError("JUDGE_RATE_CHANGED")
        rates.append(int(rate))
    if rates != [100000, 200000]:
        raise RuntimeError("JUDGE_RATE_CHANGED")
    return {
        "model": model["id"],
        "input_micro_usd_per_million": rates[0],
        "output_micro_usd_per_million": rates[1],
        "observed_at": now.isoformat(),
        "valid_until": (now + timedelta(hours=1)).isoformat(),
        "evidence_sha256": hashlib.sha256(raw).hexdigest(),
    }


def main():
    credentials = load_provider_secrets("/etc/proofflow-repair/credentials")
    with httpx.Client(verify=True, trust_env=False, follow_redirects=False, timeout=15) as client:
        with client.stream(
            "GET",
            "https://api.vultrinference.com/v1/models",
            headers={"Authorization": "Bearer " + credentials.vultr_api_key},
        ) as reply:
            if reply.status_code != 200:
                raise RuntimeError("JUDGE_CATALOGUE_UNAVAILABLE")
            raw = bytearray()
            for chunk in reply.iter_bytes():
                raw.extend(chunk)
                if len(raw) > 4 * 1024 * 1024:
                    raise RuntimeError("JUDGE_CATALOGUE_LIMIT")
    print(json.dumps(catalogue_quote(raw, datetime.now(UTC))))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("JUDGE_QUOTE_REFRESH_FAILED") from None
