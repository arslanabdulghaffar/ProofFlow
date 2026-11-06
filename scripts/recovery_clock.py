"""Wait for a small observed clock lead; never widen snapshot lifetime or accept future time."""

import time
from datetime import UTC, datetime


def wait_for_observation(value):
    observed = datetime.fromisoformat(value)
    if observed.tzinfo is None:
        raise RuntimeError("RECOVERY_CLOCK_INVALID")
    start = time.monotonic()
    while True:
        now = datetime.now(UTC)
        ahead = (observed - now).total_seconds()
        if ahead <= 0:
            return now
        if ahead > 5 or time.monotonic() - start >= 6:
            raise RuntimeError("RECOVERY_CLOCK_NOT_CAUGHT_UP")
        time.sleep(min(ahead, 0.1))
