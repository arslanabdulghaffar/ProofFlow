"""Explicit trusted Linux image-build tool. Never starts worker or candidate code."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worker.rootfs import build_image  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--image-sha256", required=True)
parser.add_argument("--destination", type=Path, required=True)
args = parser.parse_args()
print(json.dumps(build_image(args.image_sha256, args.destination), sort_keys=True))
