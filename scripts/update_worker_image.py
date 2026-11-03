"""Reviewed administrator image update; retains the previous immutable artifact."""

import hashlib
import json
import re
import subprocess

from deploy_worker import IMAGE, ROOTFS, checked_host
from vultr_phase1 import Admin


def main():
    admin = Admin()
    try:
        if admin.state.get("credit_guard", {}).get("admission_closed"):
            raise RuntimeError("CREDIT_ADMISSION_CLOSED")
        old = json.loads(checked_host(admin, "cat /etc/proofflow-worker/service.json"))
        if old["machine_id"] != admin.state["worker_machine_id"]:
            raise RuntimeError("WORKER_IDENTITY_CHANGED")
        if not re.fullmatch("[a-f0-9]{64}", old["image_sha256"]):
            raise RuntimeError("INVALID_PREVIOUS_IMAGE")
        if old["image_sha256"] == IMAGE:
            raise RuntimeError("IMAGE_ALREADY_CONFIGURED_CHECK_READBACK")
        # Service stops admission and drains existing writers before this returns.
        checked_host(admin, "systemctl stop proofflow-worker.service")
        check = """from pathlib import Path
assert not list(Path('/var/lib/proofflow-worker/state/executions').iterdir())
"""
        checked_host(admin, "/usr/bin/python3 -I -S -B -", stdin=check.encode())
        directory = "/var/lib/proofflow-worker/images/" + IMAGE
        checked_host(admin, "install -d -m 0700 " + directory)
        records = {}
        for name in ("rootfs.squashfs", "import.json"):
            data = subprocess.run(  # noqa: S603 - fixed trusted build artifact, never executed
                ["C:/Windows/System32/wsl.exe", "-d", "Ubuntu-24.04", "--", "cat",
                 "/var/tmp/proofflow-rootfs-tmp-fixed-final/" + name],  # noqa: S108
                capture_output=True, check=True, timeout=60).stdout
            sha = hashlib.sha256(data).hexdigest()
            if name == "rootfs.squashfs" and sha != ROOTFS:
                raise RuntimeError("ROOTFS_CHANGED")
            if name == "import.json":
                receipt = json.loads(data)
                if (receipt["docker_image_sha256"] != IMAGE
                        or receipt["rootfs_sha256"] != ROOTFS or receipt["image_started"]):
                    raise RuntimeError("IMPORT_RECEIPT_CHANGED")
            target = directory + "/" + name
            checked_host(admin, "set -C; umask 077; cat > " + target, stdin=data, timeout=120)
            if checked_host(admin, "sha256sum " + target).decode().split()[0] != sha:
                raise RuntimeError("IMAGE_UPLOAD_CHANGED")
            checked_host(admin, "chmod 0400 " + target)
            records["image/" + name] = {"destination": target, "mode": 0o400, "sha256": sha}
        old_image = old["image_sha256"]
        old.update(image_sha256=IMAGE, rootfs_sha256=ROOTFS)
        raw = json.dumps(old, sort_keys=True).encode()
        checked_host(admin, "umask 077; cat > /etc/proofflow-worker/service.json.reviewed",
                     stdin=raw)
        checked_host(admin, "mv /etc/proofflow-worker/service.json.reviewed "
                     "/etc/proofflow-worker/service.json")
        records["service.json"] = {"destination": "/etc/proofflow-worker/service.json",
                                   "mode": 0o600, "sha256": hashlib.sha256(raw).hexdigest()}
        update = """import json,os
from pathlib import Path
p=Path('/var/lib/proofflow-setup/worker-install.json')
m=json.loads(p.read_bytes())
m['files'].update(RECORDS)
with p.open('w') as f:
    json.dump(m,f,sort_keys=True)
    f.flush()
    os.fsync(f.fileno())
""".replace("RECORDS", repr(records))
        checked_host(admin, "/usr/bin/python3 -I -S -B -", stdin=update.encode())
        checked_host(admin, "umount /var/lib/proofflow-worker/images/" + old_image + "/rootfs")
        checked_host(admin, "systemctl start proofflow-worker.service")
        checked_host(admin, "systemctl is-active --quiet proofflow-worker.service")
        admin.state.setdefault("reviewed_updates", []).append({
            "old_image": old_image, "image": IMAGE, "rootfs": ROOTFS,
            "reason": "Real /tmp directory plus explicit bounded bind prevents automatic tmpfs"})
        admin.save()
        print(json.dumps({"image": IMAGE, "rootfs": ROOTFS, "service": "started",
                          "acceptance": "RETEST_REQUIRED"}))
    finally:
        admin.close()


if __name__ == "__main__":
    main()
