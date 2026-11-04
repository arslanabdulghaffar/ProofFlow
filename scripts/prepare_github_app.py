"""Windows administrator setup. Development Git credentials perform read-only preflight only."""

import asyncio
import base64
import ctypes
import hashlib
import json
import os
import stat
import subprocess
import sys
from ctypes import wintypes
from dataclasses import asdict
from datetime import UTC, datetime

from vultr_credit_guard import run as credit_guard
from vultr_phase1 import PRIVATE, ROOT, Admin

sys.path.insert(0, str(ROOT))
from integrations.github_app import GitHubApp, GitHubConfig, app_jwt, require  # noqa: E402


def protected_local():
    require(sys.platform == "win32", "WINDOWS_ADMINISTRATOR_REQUIRED")
    root = PRIVATE.parent / "credentials"
    paths = (root, root / "github-app.json", root / "github-app.dpapi")
    for path in paths:
        info = path.lstat()
        require(
            not info.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT,
            "GITHUB_LOCAL_PATH_UNSAFE",
        )
    # Check ACLs without emitting identities, key bytes, or environment content.
    script = r"""
$ErrorActionPreference='Stop'
$sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$root=Join-Path $env:USERPROFILE '.proofflow\credentials'
foreach($p in @($root,(Join-Path $root 'github-app.json'),(Join-Path $root 'github-app.dpapi'))) {
  $acl=Get-Acl -LiteralPath $p
  if($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -ne $sid){throw 'owner'}
  foreach($rule in $acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])){
    if($rule.IdentityReference.Value -notin @($sid,'S-1-5-18')){throw 'scope'}
  }
}
[Console]::Write('safe')
"""
    result = subprocess.run(  # noqa: S603 - fixed non-secret ACL script
        [
            "C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe",
            "-NoProfile",
            "-EncodedCommand",
            base64.b64encode(script.encode("utf-16-le")).decode(),
        ],
        capture_output=True,
        timeout=20,
    )
    require(result.returncode == 0 and result.stdout == b"safe", "GITHUB_LOCAL_ACL_UNSAFE")
    metadata, encrypted = paths[1], paths[2]
    require(
        metadata.stat().st_size <= 4096 and encrypted.stat().st_size <= 262144,
        "GITHUB_LOCAL_SIZE_INVALID",
    )
    config = json.loads(metadata.read_bytes())
    encrypted_bytes = bytes.fromhex(encrypted.read_text().strip())

    class Blob(ctypes.Structure):
        _fields_ = [("length", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    source = (ctypes.c_ubyte * len(encrypted_bytes)).from_buffer_copy(encrypted_bytes)
    incoming, outgoing = Blob(len(source), source), Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    crypt.CryptUnprotectData.argtypes = [
        ctypes.POINTER(Blob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(Blob),
    ]
    crypt.CryptUnprotectData.restype = wintypes.BOOL
    require(
        crypt.CryptUnprotectData(
            ctypes.byref(incoming), None, None, None, None, 1, ctypes.byref(outgoing)
        ),
        "GITHUB_DECRYPTION_FAILED",
    )
    try:
        require(1024 <= outgoing.length <= 65536, "GITHUB_DECRYPTED_SIZE_INVALID")
        pem = ctypes.string_at(outgoing.data, outgoing.length).decode("utf-16-le").encode("ascii")
    finally:
        ctypes.memset(outgoing.data, 0, outgoing.length)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree.restype = ctypes.c_void_p
        kernel.LocalFree(outgoing.data)
    return config, pem


async def preflight(metadata, pem):
    # This credential is never written remotely, minted into product, or used for mutations.
    result = subprocess.run(
        ["C:/Program Files/Git/cmd/git.exe", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        text=True,
        capture_output=True,
        timeout=20,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"},
    )
    require(result.returncode == 0, "GITHUB_ADMIN_READ_PREFLIGHT_UNAVAILABLE")
    credential = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    config = dict(metadata)
    config["installation_id"] = int(config["installation_id"])
    require(
        set(config) == {"client_id", "installation_id", "owner", "repository", "base", "path"},
        "GITHUB_LOCAL_CONFIG_INVALID",
    )
    app_jwt(pem, config["client_id"], int(datetime.now(UTC).timestamp()))
    reader = GitHubApp(GitHubConfig(**config, repository_id=1), pem)
    token = credential["password"]
    repo = await reader.request("GET", reader.config.prefix, token)
    require(
        repo.get("private") is True
        and repo.get("default_branch") == "main"
        and type(repo.get("id")) is int,
        "GITHUB_PRIVATE_DEMO_REPO_REQUIRED",
    )
    actions = await reader.request("GET", reader.config.prefix + "/actions/permissions", token)
    hooks = await reader.request(
        "GET", reader.config.prefix + "/hooks?per_page=100", token, array=True
    )
    require(
        actions.get("enabled") is False and hooks == [], "GITHUB_ACTIONS_AND_HOOKS_MUST_BE_DISABLED"
    )
    app = GitHubApp(GitHubConfig(**config, repository_id=repo["id"]), pem)
    scoped = await app.token()
    base = await app.inspect_base(scoped)
    return app, base


def main():
    metadata, pem = protected_local()
    app, base = asyncio.run(preflight(metadata, pem))
    source = (ROOT / "scripts/install_github_app.py").read_bytes()
    digest = hashlib.sha256(source).hexdigest()
    destination = "/var/lib/proofflow-product-setup/github-installer-" + digest + ".py"
    admin = Admin()
    try:
        require(
            credit_guard(admin, datetime.now(UTC))["credit_guard"] == "within_early_cutoff",
            "CREDIT_GUARD_NOT_ADMITTING",
        )

        def host(command, raw=None):
            result = admin.host("control", command, stdin=raw, timeout=90)
            require(result.returncode == 0, "GITHUB_REMOTE_SETUP_FAILED_RECONCILE")
            return result.stdout.strip()

        require(
            host("cat /etc/machine-id").decode() == admin.state["control_machine_id"],
            "DESIGNATED_CONTROL_CHANGED",
        )
        exists = host("test -f " + destination + " && echo present || echo absent")
        if exists == b"absent":
            host("umask 077; set -C; cat > " + destination, source)
        require(
            host("sha256sum " + destination).decode().split()[0] == digest,
            "GITHUB_INSTALLER_SOURCE_CHANGED",
        )
        receipt = json.loads(
            host(
                "/usr/bin/python3 -I -B " + destination,
                json.dumps(
                    {
                        "configuration": asdict(app.config),
                        "private_key_base64": base64.b64encode(pem).decode(),
                    }
                ).encode(),
            )
        )
        evidence = {
            "observed_at": datetime.now(UTC).isoformat(),
            "installer_sha256": digest,
            "configuration": asdict(app.config),
            "base_sha": base["base_sha"],
            "result": receipt,
            "app_preflight": "real_scoped_token_private_repo_fixed_tree",
            "actions_disabled": True,
            "webhooks_absent": True,
        }
        (PRIVATE / "evidence/github-setup.json").write_bytes(json.dumps(evidence).encode())
        print(json.dumps(receipt))
    finally:
        admin.close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit(
            "GITHUB_SETUP_NOT_COMPLETED_CHECK_LOCAL_CONFIGURATION_NO_SECRETS_IN_CHAT"
        ) from None
