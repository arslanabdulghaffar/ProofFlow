"""Install reviewed product SQL separately from budget data, with no new cloud resource."""

import hashlib
import io
import json
import tarfile
from datetime import UTC, datetime

from vultr_credit_guard import run as credit_guard
from vultr_phase1 import PRIVATE, ROOT, Admin


def main():
    paths = {name: ROOT / "db/phase2" / name for name in
             ("001_identity_assets.sql", "002_upload_reservations.sql", "003_original_queue.sql",
              "004_termination_evidence.sql")}
    files = {name: path.read_bytes() for name, path in paths.items()}
    manifest = {"migrations": {
        name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}}
    files["manifest.json"] = json.dumps(manifest, sort_keys=True).encode()
    files["original-pg_hba.conf"] = (ROOT / "infra/postgres/pg_hba.conf").read_bytes()
    files["install_product_database.py"] = (
        ROOT / "scripts/install_product_database.py").read_bytes()
    hashes = {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}
    revision = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    target = "/var/lib/proofflow-product-setup/revisions/" + revision
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        for name, raw in files.items():
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(raw), 0o400
            archive.addfile(info, io.BytesIO(raw))
    admin = Admin()
    try:
        if credit_guard(admin, datetime.now(UTC)).get("credit_guard") != "within_early_cutoff":
            raise RuntimeError("CREDIT_GUARD_NOT_ADMITTING")

        def host(command, raw=None):
            result = admin.host("control", command, stdin=raw, timeout=120)
            if result.returncode:
                raise RuntimeError("PRODUCT_DATABASE_DEPLOYMENT_FAILED_RECONCILE_BEFORE_RETRY")
            return result.stdout

        if host("cat /etc/machine-id").decode().strip() != admin.state["control_machine_id"]:
            raise RuntimeError("DESIGNATED_CONTROL_CHANGED")
        host("/bin/sh -s", (ROOT / "scripts/prepare_product_identity.sh").read_bytes())
        present = host("test -d " + target + " && echo present || echo absent").strip()
        if present == b"absent":
            host("install -d -m 0700 /var/lib/proofflow-product-setup "
                 "/var/lib/proofflow-product-setup/revisions && mkdir -m 0700 " + target)
            host("tar -xf - --no-same-owner -C " + target, stream.getvalue())
        for name, digest in hashes.items():
            if host("sha256sum " + target + "/" + name).decode().split()[0] != digest:
                raise RuntimeError("PRODUCT_MIGRATION_READBACK_CHANGED")
        result = json.loads(host(
            "/usr/bin/python3 -I -B " + target + "/install_product_database.py"))
        evidence = {"observed_at": datetime.now(UTC).isoformat(), "revision": revision,
                    "migrations": manifest["migrations"], "result": result}
        (PRIVATE / "evidence/product-database-install.json").write_bytes(
            json.dumps(evidence, sort_keys=True).encode())
        print(json.dumps(result, sort_keys=True))
    finally:
        admin.close()


if __name__ == "__main__":
    main()
