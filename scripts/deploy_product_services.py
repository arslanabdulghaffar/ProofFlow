"""Deploy private fixed services on the existing control VM after credit checks."""

import hashlib
import io
import json
import subprocess
import tarfile
from datetime import UTC, datetime

from install_product_services import IMAGE
from vultr_credit_guard import run as credit_guard
from vultr_phase1 import PRIVATE, ROOT, Admin


def main():
    deployment = json.loads((PRIVATE / "evidence/verifier-deployment.json").read_bytes())
    provider = json.loads((PRIVATE / "repair-provider.json").read_bytes())
    quote_expired = datetime.fromisoformat(provider["quote"]["valid_until"]) <= datetime.now(UTC)
    settings = {"verifier_deployment": deployment["deployment"], "repair_provider": provider}
    files = {"settings.json": json.dumps(settings, sort_keys=True).encode(),
             "install_product_services.py": (
                 ROOT / "scripts/install_product_services.py").read_bytes()}
    hashes = {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}
    revision = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    target = "/var/lib/proofflow-product-setup/revisions/" + revision
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        for name, raw in files.items():
            item = tarfile.TarInfo(name)
            item.size, item.mode = len(raw), 0o400
            archive.addfile(item, io.BytesIO(raw))
    admin = Admin()
    try:
        if credit_guard(admin, datetime.now(UTC)).get("credit_guard") != "within_early_cutoff":
            raise RuntimeError("CREDIT_GUARD_NOT_ADMITTING")

        def host(command, raw=None, timeout=180):
            result = admin.host("control", command, stdin=raw, timeout=timeout)
            if result.returncode:
                raise RuntimeError("PRODUCT_SERVICE_DEPLOYMENT_FAILED_RECONCILE_BEFORE_RETRY")
            return result.stdout

        if host("cat /etc/machine-id").decode().strip() != admin.state["control_machine_id"]:
            raise RuntimeError("DESIGNATED_CONTROL_CHANGED")
        # Software-only work may retain an expired quote while paid dispatch is
        # durably blocked. The provider itself still refuses every stale quote.
        if quote_expired:
            blocked = host("docker exec --user=70:70 proofflow-budget psql -X -qAt "
                "-h /run/proofflow-budget -U postgres -d proofflow_budget -c "
                '"SELECT count(*)=1 AND bool_and(blocked) FROM pf_budget.accounts;"').strip()
            if blocked != b"t":
                raise RuntimeError("FRESH_REPAIR_QUOTE_OR_BLOCKED_INFERENCE_REQUIRED")
        present = host("docker image ls --no-trunc --quiet sha256:" + IMAGE).strip()
        if not present:
            exported = subprocess.run(  # noqa: S603 - trusted pinned image; no candidate execution
                ["C:/Windows/System32/wsl.exe", "-d", "Ubuntu-24.04", "--", "docker", "save",
                 "sha256:" + IMAGE], capture_output=True, check=True, timeout=120).stdout
            if not 1 <= len(exported) <= 512 * 1024 * 1024:
                raise RuntimeError("PRODUCT_IMAGE_ARCHIVE_LIMIT")
            digest = hashlib.sha256(exported).hexdigest()
            path = "/var/lib/proofflow-product-setup/product-image-" + digest + ".tar"
            host("umask 077; cat > " + path, exported)
            if host("sha256sum " + path).decode().split()[0] != digest:
                raise RuntimeError("PRODUCT_IMAGE_UPLOAD_CHANGED")
            host("docker image load --input " + path)
        if host("test -d " + target + " && echo present || echo absent").strip() == b"absent":
            host("mkdir -m 0700 " + target)
            host("tar -xf - --no-same-owner -C " + target, stream.getvalue())
        for name, digest in hashes.items():
            if host("sha256sum " + target + "/" + name).decode().split()[0] != digest:
                raise RuntimeError("PRODUCT_SERVICE_SOURCE_CHANGED")
        result = json.loads(host(
            "/usr/bin/python3 -I -B " + target + "/install_product_services.py"))
        receipt = {"observed_at": datetime.now(UTC).isoformat(), "revision": revision,
                   "sources": hashes, "result": result, "verifier": settings}
        (PRIVATE / "evidence/product-service-install.json").write_bytes(
            json.dumps(receipt, sort_keys=True).encode())
        print(json.dumps(result, sort_keys=True))
    finally:
        admin.close()


if __name__ == "__main__":
    main()
