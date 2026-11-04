"""Socket-activated control helper at the immutable administrator installation."""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.append("/opt/proofflow-control/lib")

from verifier.socket_service import activated_socket, serve  # noqa: E402

if __name__ == "__main__":
    config = json.loads((HERE / "deployment.json").read_bytes())
    with activated_socket() as listener:
        serve(listener, image=HERE / "rootfs.squashfs", image_sha256=config["rootfs_sha256"])
