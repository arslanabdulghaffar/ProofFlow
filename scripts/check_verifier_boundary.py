"""Trusted Linux verifier smoke check. Only data enters the fixed bounded process."""

import argparse
import json
from pathlib import Path

from contracts.codec import canonical_bytes
from verifier.host import run
from verifier.protocol import encode


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    raw = canonical_bytes({"operation": "canary", "seed": "ab" * 32, "case": "ownership",
                           "contract": encode(Path("contracts/examples/synthetic-v1.1.json")
                                              .read_bytes())})
    receipt = run(raw, image=args.image, image_sha256=args.sha256)
    if receipt["report"]["status"] != "processed" or receipt["cleanup_confirmed"] is not True:
        raise RuntimeError("VERIFIER_SMOKE_FAILED")
    print(json.dumps({"check": "bounded_canary_generation", "status": "passed",
                      "rootfs_sha256": receipt["rootfs_sha256"],
                      "report_sha256": receipt["report_sha256"], "cleanup_confirmed": True}))


if __name__ == "__main__":
    main()
