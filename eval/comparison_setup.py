"""Initialize one finite private comparison book. No provider/worker calls."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, "/comparison")
sys.path.append("/app")

from eval.comparison_journal import initialize  # noqa: E402

if __name__ == "__main__":
    os.umask(0o077)
    settings = json.loads(Path("/comparison/settings.json").read_bytes())
    initialize(
        Path("/var/lib/proofflow-comparison/budget"),
        settings["campaign_sha256"],
        {j["run_id"]: j["arm"] for j in settings["jobs"] if j["arm"] in ("B", "C")},
    )
    print("COMPARISON_BOOK_INITIALIZED")
