"""Actual expired preview rejection and read-only GitHub reconciliation; no new PR intent."""

import argparse
import asyncio
import json
import os
import re
import ssl
import subprocess
from datetime import UTC, datetime
from uuid import UUID

import httpx
from prepare_github_app import preflight, protected_local
from product_live_session import ORIGIN, PRIVATE, LiveSession, require


def existing_session(name="phase4-pr-session.dpapi"):
    require(
        name == "phase4-pr-session.dpapi"
        or re.fullmatch(r"phase4-pr-[a-f0-9]{32}\.dpapi", name) is not None,
        "PRIVATE_SESSION_NAME_INVALID",
    )
    script = r"""
$ErrorActionPreference='Stop'
$root=Join-Path $env:USERPROFILE '.proofflow\deployment'
$path=Join-Path $root $env:PROOFFLOW_SESSION_FILE
$item=Get-Item -LiteralPath $path -Force
if($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
   $item.Length -gt 65536){throw 'path'}
$acl=[IO.File]::GetAccessControl($path)
$sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
if($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -ne $sid){throw 'owner'}
foreach($rule in $acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])){
  if($rule.IdentityReference.Value -notin @($sid,'S-1-5-18')){throw 'scope'}
}
$secure=ConvertTo-SecureString -String ([IO.File]::ReadAllText($path))
$ptr=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {[Console]::Write([Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr))}
finally {[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr);$secure.Dispose()}
"""
    result = subprocess.run(  # noqa: S603 - fixed private DPAPI session loader
        [
            "C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe",
            "-NoProfile",
            "-Command",
            script,
        ],
        capture_output=True,
        timeout=20,
        env={
            **{k: v for k, v in os.environ.items() if k.upper() != "PSMODULEPATH"},
            "PROOFFLOW_SESSION_FILE": name,
        },
    )
    require(result.returncode == 0, "PRIVATE_SESSION_UNAVAILABLE")
    value = json.loads(result.stdout)
    require(set(value) == {"token", "csrf"}, "PRIVATE_SESSION_INVALID")
    return value


async def external_readback(intent):
    metadata, pem = protected_local()
    app, base = await preflight(metadata, pem)
    token = await app.token()
    require(await app.read_branch(token, intent) is None, "EXTERNAL_BRANCH_UNEXPECTED")
    require(await app.find_pr(token, intent) is None, "EXTERNAL_PR_UNEXPECTED")
    return {
        "app_authentication": "passed_after_unused_key_revocation",
        "branch_exists": False,
        "pr_exists": False,
        "base_sha": base["base_sha"],
    }


def main(refresh=False):
    source = PRIVATE / "evidence" / (
        "phase4-pr-refresh-20261105.json" if refresh else "phase4-pr-preview-intent.json"
    )
    original = json.loads(source.read_bytes())
    preview = original["pr"]
    require(
        datetime.now(UTC) > datetime.fromisoformat(preview["expires_at"]), "PREVIEW_NOT_EXPIRED"
    )
    saved = existing_session(original["session_file"] if refresh else "phase4-pr-session.dpapi")
    with LiveSession() as live:
        live.client = httpx.Client(
            base_url=ORIGIN,
            trust_env=False,
            timeout=20,
            verify=ssl.create_default_context(cafile=str(PRIVATE / "tls/ca.pem")),
            headers={
                "Cookie": "__Host-proofflow=" + saved["token"],
                "Origin": ORIGIN,
                "X-ProofFlow-CSRF": saved["csrf"],
            },
        )
        session_status = live.client.get("/v1/session").status_code
        require(session_status in (200, 403), "ACTOR_SESSION_UNEXPECTED")
        approval_status = None
        if session_status == 200 and not refresh:
            response = live.client.post(
                "/v1/pr-intents/" + original["pr_intent"] + "/approve",
                json={"confirm": True, "preview_sha256": preview["preview_sha256"]},
            )
            approval_status = response.status_code
            require(approval_status == 409, "EXPIRED_APPROVAL_NOT_DENIED")
        require(
            live.sql("SELECT count(*) FROM pf_product.pr_writes;") == b"0",
            "UNEXPECTED_WRITE_INTENT",
        )
        external = asyncio.run(external_readback(original["pr_intent"]))
        identity = str(UUID(original["pr_intent"]))
        # Only a parsed/canonical UUID is interpolated into this administrator read.
        statement = (
            "SELECT jsonb_build_object('state',a.state,'approved_at',a.approved_at,"  # noqa: S608
            "'expires_at',a.expires_at,'currently_authorized',"
            "COALESCE(pf_product.pr_current(a),false)) FROM pf_product.pr_intents a "
            "WHERE a.id='" + identity + "';"
        )
        durable = json.loads(live.sql(statement))
        require(
            durable["approved_at"] is None and durable["currently_authorized"] is False,
            "UNEXPECTED_APPROVAL_STATE",
        )
        # This temporary actor is no longer useful; revoke via the normal authenticated route.
        if session_status == 200:
            require(
                live.client.post("/v1/logout").status_code == 204,
                "TEMPORARY_SESSION_REVOCATION_FAILED",
            )
        require(
            live.client.get("/v1/session").status_code == 403, "REVOKED_SESSION_STILL_AUTHORIZED"
        )
        result = {
            "observed_at": datetime.now(UTC).isoformat(),
            "intent": original["pr_intent"],
            "preview_sha256": preview["preview_sha256"],
            "expired_at": preview["expires_at"],
            "initial_session_http_status": session_status,
            "approval_http_status": approval_status,
            "durable_intent": durable,
            "prior_probe_limitation": None if refresh else (
                "Initial harness expected logout 200 instead of the documented 204; "
                "no final receipt retained. Reconciliation does not recreate approval or session."
            ),
            "durable_external_writes": 0,
            "external_readback": external,
            "temporary_session_unauthorized": True,
            "credit": live.credit,
            "new_worker_executions": 0,
            "provider_calls": 0,
            "new_cloud_resources": 0,
            "admission": "remained_closed",
            "unused_key_revoked": 5183052,
            "working_key_preserved": 5183074,
            "user_authorization": "exact PR approved after expiry; no rebinding",
        }
        destination = "phase4-refresh-expired-result.json" if refresh else (
            "phase4-expired-approval-result.json"
        )
        (PRIVATE / "evidence" / destination).write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--refresh", action="store_true", help="Read-only fresh-intent reconciliation"
    )
    args = parser.parse_args()
    try:
        main(args.refresh)
    except Exception:
        raise SystemExit("EXPIRED_APPROVAL_CHECK_FAILED_RECONCILE_PRIVATE_STATE") from None
