"""Read-only provider metering on the control host; no completion or settlement."""

import hashlib
import json
from datetime import UTC, datetime

import httpx

from orchestrator.provider_setup import load_provider_secrets

secrets = load_provider_secrets()
with httpx.Client(verify=True, trust_env=False, follow_redirects=False, timeout=15) as client:
    with client.stream("GET", "https://api.vultrinference.com/v1/usage",
                       headers={"Authorization": "Bearer " + secrets.vultr_api_key}) as response:
        if response.status_code != 200:
            raise RuntimeError("PROVIDER_USAGE_UNAVAILABLE")
        raw = bytearray()
        for chunk in response.iter_bytes():
            raw.extend(chunk)
            if len(raw) > 262144:
                raise RuntimeError("USAGE_RESPONSE_LIMIT")
value = json.loads(raw)
print(json.dumps({"observed_at": datetime.now(UTC).isoformat(),
                  "response_sha256": hashlib.sha256(raw).hexdigest(),
                  "usage": value["usage"], "settled_reservations": False}))
