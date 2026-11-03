"""Transfer only the reviewed trusted control/database images over pinned SSH."""

import hashlib
import json
import subprocess

from vultr_phase1 import Admin

CONTROL = "f7e7c9f9642508862c95de8cd000b2235968c9399822e0e543449e2ea04bae17"
POSTGRES = "9ed8d24e2d804f04bd228a4619c9ed43c3a8d2f4a09fe947b44b112615eb010d"


def main():
    data = subprocess.run(  # noqa: S603 - fixed trusted image archive, never candidate content
        [
            "C:/Windows/System32/wsl.exe",
            "-d",
            "Ubuntu-24.04",
            "--",
            "cat",
            "/var/tmp/proofflow-control-images.tar",  # noqa: S108 - pinned trusted archive
        ],
        capture_output=True,
        check=True,
        timeout=90,
    ).stdout
    if not 1 <= len(data) <= 1024 * 1024 * 1024:
        raise RuntimeError("TRUSTED_IMAGE_ARCHIVE_SIZE_INVALID")
    digest = hashlib.sha256(data).hexdigest()
    admin = Admin()
    try:

        def host(command, payload=None, timeout=180):
            result = admin.host("control", command, stdin=payload, timeout=timeout)
            if result.returncode:
                raise RuntimeError("CONTROL_IMAGE_ADMIN_OPERATION_FAILED")
            return result.stdout

        if host("cat /etc/machine-id").decode().strip() != admin.state["control_machine_id"]:
            raise RuntimeError("CONTROL_HOST_CHANGED")
        target = "/var/lib/proofflow-setup/control-images.tar"
        host("umask 077; cat > " + target, data)
        if host("sha256sum " + target).decode().split()[0] != digest:
            raise RuntimeError("TRUSTED_IMAGE_UPLOAD_CHANGED")
        host("docker --host=unix:///var/run/docker.sock image load --input " + target)
        for image in (CONTROL, POSTGRES):
            observed = json.loads(
                host("docker --host=unix:///var/run/docker.sock image inspect sha256:" + image)
            )[0]
            if observed["Id"] != "sha256:" + image or observed["Architecture"] != "amd64":
                raise RuntimeError("LOADED_CONTROL_IMAGE_CHANGED")
        admin.state["control_images"] = {
            "control": CONTROL,
            "postgres": POSTGRES,
            "archive_sha256": digest,
            "bytes": len(data),
        }
        admin.save()
        print(json.dumps(admin.state["control_images"]))
    finally:
        admin.close()


if __name__ == "__main__":
    main()
