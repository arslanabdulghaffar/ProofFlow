"""Install reviewed retention only on the existing designated control after credit guard."""

import hashlib
import io
import json
import tarfile
from datetime import UTC, datetime

from vultr_credit_guard import run as credit_guard
from vultr_phase1 import PRIVATE, ROOT, Admin


def main():
    files = {name: (ROOT / "scripts" / name).read_bytes() for name in (
        "install_product_retention.py", "install_product_services.py", "product_retention_host.py")}
    files["retention.py"] = (ROOT / "orchestrator/retention.py").read_bytes()
    hashes = {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}
    revision = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    target = "/opt/proofflow-retention/" + revision
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as tar:
        for name, raw in files.items():
            entry = tarfile.TarInfo(name)
            entry.size, entry.mode = len(raw), 0o444 if name == "retention.py" else 0o400
            tar.addfile(entry, io.BytesIO(raw))
    admin = Admin()
    try:
        guard = credit_guard(admin, datetime.now(UTC))
        if guard.get("credit_guard") != "within_early_cutoff":
            raise RuntimeError("CREDIT_GUARD_NOT_ADMITTING")
        def host(command, raw=None, timeout=60):
            result = admin.host("control", command, stdin=raw, timeout=timeout)
            if result.returncode:
                (PRIVATE / "evidence/retention-deploy-failure.txt").write_bytes(result.stderr)
                raise RuntimeError("RETENTION_DEPLOYMENT_FAILED_RECONCILE")
            return result.stdout
        if host("cat /etc/machine-id").decode().strip() != admin.state["control_machine_id"]:
            raise RuntimeError("DESIGNATED_CONTROL_CHANGED")
        if host("test -d " + target + " && echo present || echo absent").strip() == b"absent":
            host("install -d -m 0755 /opt/proofflow-retention && mkdir -m 0755 " + target)
            host("tar -xf - --no-same-owner -C " + target, archive.getvalue())
        for name, digest in hashes.items():
            if host("sha256sum " + target + "/" + name).decode().split()[0] != digest:
                raise RuntimeError("RETENTION_SOURCE_CHANGED")
        result = json.loads(host("/usr/bin/python3 -I -B " + target
                                 + "/install_product_retention.py", timeout=250))
        receipt = {"revision": revision, "result": result, "sources": hashes,
                   "observed_at": datetime.now(UTC).isoformat(), "credit_guard": guard}
        (PRIVATE / "evidence/product-retention-install.json").write_bytes(
            json.dumps(receipt).encode())
        print(json.dumps(result))
    finally:
        admin.close()


if __name__ == "__main__":
    main()
