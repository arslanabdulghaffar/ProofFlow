"""Real isolated unchanged-source proof and read-only GitHub preview; never approves a PR."""

import json
import os
import re
import subprocess
import time
from datetime import UTC, datetime
from uuid import uuid4

from product_live_session import PRIVATE, LiveSession, require

WORKSPACE = "1c7529c0-b6c4-4f83-919a-d10942dce4ff"
PARENT = "3a0b0fe9-ab79-4616-b2e5-b7b3a10012d2"


def save_session(secret, name="phase4-pr-session.dpapi"):
    require(
        name == "phase4-pr-session.dpapi"
        or re.fullmatch(r"phase4-pr-[a-f0-9]{32}\.dpapi", name) is not None,
        "PRIVATE_SESSION_NAME_INVALID",
    )
    # Explicit owner/DACL at creation also works in an elevated terminal, where
    # the default owner would be Administrators. Never relax the readback check.
    script = r"""
$ErrorActionPreference='Stop'
$root=Join-Path $env:USERPROFILE '.proofflow\deployment'
$sid=[Security.Principal.WindowsIdentity]::GetCurrent().User
foreach($path in @((Split-Path -Parent $root),$root)) {
  $item=Get-Item -LiteralPath $path -Force
  if(-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)){
    throw 'path'
  }
  if($path -ne $root){continue}
  $parentAcl=[IO.Directory]::GetAccessControl($path)
  if($parentAcl.GetOwner([Security.Principal.SecurityIdentifier]).Value -ne $sid.Value){
    throw 'owner'
  }
  foreach($rule in $parentAcl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])){
    if($rule.IdentityReference.Value -notin @($sid.Value,'S-1-5-18')){throw 'scope'}
  }
}
$acl=[Security.AccessControl.FileSecurity]::new()
$acl.SetOwner($sid)
$acl.SetAccessRuleProtection($true,$false)
foreach($principal in @($sid,[Security.Principal.SecurityIdentifier]::new('S-1-5-18'))){
  $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
    $principal,'FullControl','Allow'))
}
$value=[Console]::In.ReadToEnd()
$secret=ConvertTo-SecureString -String $value -AsPlainText -Force
try {
  $bytes=[Text.Encoding]::UTF8.GetBytes((ConvertFrom-SecureString -SecureString $secret))
  $target=Join-Path $root $env:PROOFFLOW_SESSION_FILE
  $stream=[IO.FileStream]::new($target,[IO.FileMode]::CreateNew,
    [Security.AccessControl.FileSystemRights]::Write,[IO.FileShare]::None,
    4096,[IO.FileOptions]::None,$acl)
  try {$stream.Write($bytes,0,$bytes.Length);$stream.Flush($true)}
  finally {$stream.Dispose()}
} finally {$secret.Dispose();$value=$null}
"""
    result = subprocess.run(  # noqa: S603 - fixed encryption helper, secrets only on stdin
        [
            "C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe",
            "-NoProfile",
            "-Command",
            script,
        ],
        input=json.dumps({"token": secret.token, "csrf": secret.csrf}).encode(),
        capture_output=True,
        timeout=20,
        env={
            **{k: v for k, v in os.environ.items() if k.upper() != "PSMODULEPATH"},
            "PROOFFLOW_SESSION_FILE": name,
        },
    )
    require(result.returncode == 0 and result.stdout == b"", "PRIVATE_SESSION_SAVE_FAILED")


def main():
    path = PRIVATE / "evidence/phase4-pr-preview-intent.json"
    require(not path.exists(), "RECONCILE_EXISTING_PR_PREVIEW_INTENT")
    intent = {
        "workspace": WORKSPACE,
        "parent": PARENT,
        "repair_request": {"parent_id": PARENT, "idempotency_key": str(uuid4())},
        "activation_intent": str(uuid4()),
        "pr_intent": str(uuid4()),
        "synthetic_activation_not_human_signoff": True,
        "external_approval": False,
    }

    def save():
        path.write_text(json.dumps(intent, indent=2), encoding="utf-8")

    with path.open("x", encoding="utf-8") as output:
        json.dump(intent, output)
    with LiveSession() as live:
        client = live.login(WORKSPACE)
        save_session(live.secret)
        require(
            live.sql("SELECT bool_and(blocked) FROM pf_budget.accounts;", "proofflow_budget")
            == b"t",
            "INFERENCE_MUST_REMAIN_BLOCKED",
        )
        reservations = live.sql("SELECT count(*) FROM pf_budget.reservations;", "proofflow_budget")
        require(
            live.sql("SELECT count(*) FROM pf_product.pr_writes;") == b"0",
            "REVIEW_EXISTING_EXTERNAL_WRITES",
        )
        parent = client.get("/v1/jobs/" + PARENT)
        require(
            parent.status_code == 200 and parent.json()["outcome"] == "match", "PARENT_NOT_MATCHED"
        )
        live.admission(True)
        response = client.post("/v1/repairs", json=intent["repair_request"])
        require(response.status_code == 202, "FRESH_PROOF_NOT_ACCEPTED")
        version = response.json()["repair_id"]
        intent["version"] = version
        save()
        for _ in range(240):
            response = client.get("/v1/repairs/" + version)
            require(response.status_code == 200, "FRESH_PROOF_STATUS_UNAVAILABLE")
            proof = response.json()
            if proof["state"] not in ("QUEUED", "RUNNING", "RECONCILING"):
                break
            time.sleep(1)
        intent["proof"] = proof
        save()
        require(
            proof["state"] == "AWAITING_APPROVAL"
            and proof["calls"] == 0
            and proof["mode"] == "original"
            and proof["reserved_micro"] == 0
            and len(proof["checks"]) == 3
            and all(c["cleanup_confirmed"] and c["comparison"] == "match" for c in proof["checks"]),
            "FRESH_ISOLATED_PROOF_FAILED",
        )
        require(
            client.post(
                "/v1/repairs/" + version + "/version", json={"prepare_verified_source": True}
            ).status_code
            == 200,
            "VERSION_PREPARATION_FAILED",
        )
        response = client.post(
            "/v1/versions/" + version + "/preview", json={"intent_id": intent["activation_intent"]}
        )
        require(response.status_code == 200, "ACTIVATION_PREVIEW_FAILED")
        activation = response.json()
        intent["activation"] = activation
        save()
        require(
            client.post(
                "/v1/versions/" + version + "/approve",
                json={
                    "intent_id": intent["activation_intent"],
                    "bundle_sha256": activation["bundle_sha256"],
                    "confirm": True,
                },
            ).status_code
            == 200,
            "EXACT_SYNTHETIC_ACTIVATION_FAILED",
        )
        live.admission(False)
        response = client.post(
            "/v1/versions/" + version + "/pr-preview", json={"intent_id": intent["pr_intent"]}
        )
        require(response.status_code == 202, "PR_PREVIEW_NOT_ACCEPTED")
        for _ in range(90):
            response = client.get("/v1/pr-intents/" + intent["pr_intent"])
            require(response.status_code == 200, "PR_PREVIEW_STATUS_UNAVAILABLE")
            preview = response.json()
            if preview["state"] != "PREPARING":
                break
            time.sleep(1)
        intent["pr"] = preview
        intent["credit"] = live.credit
        intent["observed_at"] = datetime.now(UTC).isoformat()
        save()
        require(preview["state"] == "PREVIEW", "REAL_GITHUB_PREVIEW_FAILED")
        require(
            live.sql("SELECT count(*) FROM pf_product.pr_writes;") == b"0",
            "UNAPPROVED_WRITE_PRESENT",
        )
        require(
            live.sql("SELECT count(*) FROM pf_budget.reservations;", "proofflow_budget")
            == reservations,
            "UNEXPECTED_INFERENCE_RESERVATION",
        )
        print(
            json.dumps(
                {
                    "status": "preview_ready",
                    "version": version,
                    "intent": intent["pr_intent"],
                    "preview_sha256": preview["preview_sha256"],
                    "expires_at": preview["expires_at"],
                    "isolated_checks": 3,
                    "provider_calls": 0,
                    "external_writes": 0,
                }
            )
        )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("PR_PREVIEW_PREPARATION_FAILED_RECONCILE_PRIVATE_INTENT") from None
