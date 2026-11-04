"""Inspect only trusted product image modules; never imports or runs uploaded code."""

import hashlib
import json
import subprocess
from pathlib import Path

IMAGE = "886e5044e05ce84b78c2fc10ae19019d577338b66e7808475d0020a4fb452bab"
PROBE = """
import hashlib,json,os,stat
from pathlib import Path
import api.app.product_bootstrap,orchestrator.product_bootstrap
assert os.getuid()==10003 and os.getgid()==10003
result={}
for p in Path('/app').rglob('*'):
    assert not p.is_symlink()
    if p.is_file():
        assert p.suffix in ('.py','.html','.js','.css') and stat.S_IMODE(p.stat().st_mode)==0o444
        result[str(p.relative_to('/app'))]=hashlib.sha256(p.read_bytes()).hexdigest()
    elif p.is_dir(): assert stat.S_IMODE(p.stat().st_mode)==0o555
print(json.dumps(result,sort_keys=True))
"""


def main():
    result = subprocess.run(  # noqa: S603 - reviewed trusted product imports/inventory only
        ["C:/Windows/System32/wsl.exe", "-d", "Ubuntu-24.04", "--", "docker", "run", "--rm",
         "--pull=never", "--network=none", "--read-only", "--cap-drop=ALL",
         "--security-opt=no-new-privileges", "--memory=256m", "--memory-swap=256m",
         "--cpus=1", "--pids-limit=32", "--user=10003:10003", "--entrypoint=python",
         "sha256:" + IMAGE, "-c", PROBE], capture_output=True, check=True, timeout=30)
    inventory = json.loads(result.stdout)
    packages = ("!api/", "!contracts/", "!orchestrator/",
                "!integrations/", "!verifier/", "!worker/")
    expected = {line[1:] for line in Path(".dockerignore").read_text().splitlines()
                if line.startswith(packages)
                and line.endswith((".py", ".html", ".js", ".css"))}
    if inventory.keys() != expected:
        raise RuntimeError("PRODUCT_IMAGE_CONTENT_INVENTORY_CHANGED")
    for name, digest in inventory.items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest() != digest:
            raise RuntimeError("PRODUCT_IMAGE_SOURCE_CHANGED: " + name)
    print(json.dumps({"image": IMAGE, "approved_modules": len(inventory),
                      "source_hashes_match": True, "unexpected_files": 0, "user": "10003:10003"}))


if __name__ == "__main__":
    main()
