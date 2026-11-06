"""Add only the reviewed trusted verifier to the existing control VM. No new service charge."""

import hashlib
import io
import json
import subprocess
import sys
import tarfile
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vultr_credit_guard import run as credit_guard  # noqa: E402
from vultr_phase1 import PRIVATE, ROOT, Admin  # noqa: E402

IMAGE = "294a27ed5f8f2a6d35d473bf81b910c85cc2ed87c28bcd585717613cee0e471c"
ROOTFS = "0290920d63d9b55108c83d300922f5af84608147495f340e86025fc0e599e63b"
LOCAL = "/var/lib/proofflow-verifier-image-v7/rootfs.squashfs"
MODULES = {
    "contracts": ("__init__", "codec", "scalars", "source", "policy"),
    "verifier": ("__init__", "outputs", "lineage", "reference", "compare", "canaries",
                 "protocol", "entrypoint", "host", "socket_service"),
    "orchestrator": ("__init__", "worker_client", "verification_run", "verifier_client"),
}


def main():
    blob = subprocess.run(  # noqa: S603 - fixed trusted locally built image
        ["C:/Windows/System32/wsl.exe", "-d", "Ubuntu-24.04", "-u", "root", "--", "cat", LOCAL],
        capture_output=True, check=True, timeout=60).stdout
    if hashlib.sha256(blob).hexdigest() != ROOTFS:
        raise RuntimeError("VERIFIER_BUILD_HASH_CHANGED")
    files = {f"{package}/{name}.py": (ROOT / package / (name + ".py")).read_bytes()
             for package, names in MODULES.items() for name in names}
    files["verifier_admin.py"] = (ROOT / "scripts/verifier_admin.py").read_bytes()
    files["verifier_socket_admin.py"] = (ROOT / "scripts/verifier_socket_admin.py").read_bytes()
    hashes = {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}
    config = {"image_sha256": IMAGE, "rootfs_sha256": ROOTFS, "sources": hashes}
    config_raw = json.dumps(config, sort_keys=True).encode()
    deployment = hashlib.sha256(config_raw).hexdigest()
    target = "/opt/proofflow-verifier/" + deployment
    files["deployment.json"] = config_raw
    files["rootfs.squashfs"] = blob
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as tar:
        for name, raw in files.items():
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(raw), 0o400
            tar.addfile(info, io.BytesIO(raw))
    admin = Admin()
    try:
        guard = credit_guard(admin, datetime.now(UTC))
        if guard.get("credit_guard") != "within_early_cutoff":
            raise RuntimeError("CREDIT_GUARD_NOT_ADMITTING")

        def host(command, data=None, timeout=120):
            result = admin.host("control", command, stdin=data, timeout=timeout)
            if result.returncode:
                raise RuntimeError("VERIFIER_DEPLOYMENT_OPERATION_FAILED")
            return result.stdout

        if host("cat /etc/machine-id").decode().strip() != admin.state["control_machine_id"]:
            raise RuntimeError("DESIGNATED_CONTROL_CHANGED")
        host("/bin/sh -s", (ROOT / "scripts/prepare_verifier_identity.sh").read_bytes())
        # Unique content-addressed install; no in-place edits of a previous verifier.
        exists = host("test -d " + target + " && echo present || echo absent").strip()
        if exists == b"absent":
            host("install -d -m 0700 /opt/proofflow-verifier && mkdir -m 0700 " + target)
            host("tar -xf - --no-same-owner -C " + target, archive.getvalue())
        for name, raw in files.items():
            actual = host("sha256sum " + target + "/" + name).decode().split()[0]
            if actual != hashlib.sha256(raw).hexdigest():
                raise RuntimeError("VERIFIER_DEPLOYED_READBACK_CHANGED")
        result = host("/usr/bin/python3 -I -B " + target + "/verifier_admin.py", b"{}")
        receipt = json.loads(result)
        if (receipt["cleanup_confirmed"] is not True or receipt["rootfs_sha256"] != ROOTFS
                or receipt["report"]["status"] != "rejected"):
            raise RuntimeError("DEPLOYED_VERIFIER_SMOKE_FAILED")
        state = {"deployment": deployment, "directory": target, **config,
                 "observed_at": datetime.now(UTC).isoformat(), "smoke": "passed"}
        (PRIVATE / "evidence/verifier-deployment.json").write_text(json.dumps(state, indent=2))
        print(json.dumps({"deployment": deployment, "rootfs_sha256": ROOTFS,
                          "readback": "all_sources_and_image_match", "smoke": "passed"}))
    finally:
        admin.close()


if __name__ == "__main__":
    main()
