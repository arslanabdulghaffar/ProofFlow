"""Real Linux publication probe under the service's restrictive root umask."""

import json
import os
import stat
import tempfile
from pathlib import Path

import judging_guard
from judging_guard import publish_quote


def main():
    with tempfile.TemporaryDirectory(prefix="proofflow-judge-quote-") as tmp:
        judging_guard.QUOTE = Path(tmp) / "config.json"
        prior = os.umask(0o077)
        try:
            publish_quote({"quote": "synthetic-public-data"})
            if stat.S_IMODE(judging_guard.QUOTE.stat().st_mode) != 0o444:
                raise RuntimeError("QUOTE_NOT_READABLE_BY_DISPATCHER")
            if json.loads(judging_guard.QUOTE.read_bytes()) != {"quote": "synthetic-public-data"}:
                raise RuntimeError("QUOTE_BYTES_CHANGED")
            # An interrupted/conflicting stage is never overwritten blindly.
            pending = judging_guard.QUOTE.with_suffix(".judging-pending")
            pending.symlink_to(judging_guard.QUOTE)
            try:
                publish_quote({"quote": "replacement"})
            except FileExistsError:
                pass
            else:
                raise RuntimeError("CONFLICTING_STAGE_ACCEPTED")
            if json.loads(judging_guard.QUOTE.read_bytes()) != {"quote": "synthetic-public-data"}:
                raise RuntimeError("PRIOR_QUOTE_CHANGED")
        finally:
            os.umask(prior)
    print("LINUX_077_QUOTE_READABILITY_AND_CONFLICT_PASS")


if __name__ == "__main__":
    main()
