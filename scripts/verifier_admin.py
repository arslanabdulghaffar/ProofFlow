"""Pinned control administrator transport; this file is not a public API."""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.append("/opt/proofflow-control/lib")

from verifier.host import run  # noqa: E402
from verifier.protocol import MAX_REQUEST  # noqa: E402


def main():
    config = json.loads((HERE / "deployment.json").read_bytes())
    raw = sys.stdin.buffer.read(MAX_REQUEST + 1)
    receipt = run(raw, image=HERE / "rootfs.squashfs", image_sha256=config["rootfs_sha256"])
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
