"""Deploy reviewed judge-only public API and fixed guard; leave admission closed."""

import hashlib
import io
import json
import shlex
import tarfile
from datetime import UTC, datetime

from vultr_credit_guard import run as credit_guard
from vultr_phase1 import PRIVATE, ROOT, Admin


def main():
    admin = Admin()
    try:
        if credit_guard(admin, datetime.now(UTC))["credit_guard"] != "within_early_cutoff":
            raise RuntimeError("CREDIT_CLOSED")

        def host(command, raw=None):
            result = admin.host("control", command, stdin=raw, timeout=180)
            if result.returncode:
                (PRIVATE / "evidence/judge-install-error.txt").write_bytes(
                    result.stderr + result.stdout
                )
                raise RuntimeError("JUDGE_INSTALL_FAILED_RECONCILE_PRIVATE_EVIDENCE")
            return result.stdout

        if host("cat /etc/machine-id").decode().strip() != admin.state["control_machine_id"]:
            raise RuntimeError("CONTROL_IDENTITY_CHANGED")
        now = datetime.now(UTC)
        config = {
            "enabled": True,
            "reviewed_at": now.isoformat(),
            "funded_until": admin.state["review_due_at"],
            "boot_id": host("cat /proc/sys/kernel/random/boot_id").decode().strip(),
        }
        names = (
            "judging_guard.py",
            "guest_demo_guard.py",
            "install_provider_quote.py",
            "install_product_services.py",
            "public_api_policy.py",
            "install_judge_access.py",
        )
        files = {n: (ROOT / "scripts" / n).read_bytes() for n in names}
        files["judging.json"] = json.dumps(config).encode()
        hashes = {n: hashlib.sha256(v).hexdigest() for n, v in files.items()}
        revision = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
        target = "/var/lib/proofflow-product-setup/judging-" + revision
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w") as archive:
            for name, raw in files.items():
                item = tarfile.TarInfo(name)
                item.size = len(raw)
                item.mode = 0o400
                archive.addfile(item, io.BytesIO(raw))
        host("install -d -m 700 " + target + " && tar -xf - -C " + target, stream.getvalue())
        for name, digest in hashes.items():
            if host("sha256sum " + shlex.quote(target + "/" + name)).decode().split()[0] != digest:
                raise RuntimeError("JUDGE_DEPLOY_HASH_CHANGED")
        result = json.loads(host("/usr/bin/python3 " + target + "/install_judge_access.py"))
        (PRIVATE / "evidence/judge-access-install.json").write_text(
            json.dumps(result | {"hashes": hashes}, indent=2)
        )
        print(json.dumps(result))
    finally:
        admin.close()


if __name__ == "__main__":
    main()
