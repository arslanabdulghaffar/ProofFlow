"""Owner-operated bounded guest launcher. No credential output or automatic approvals."""

import argparse
import base64
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
from guest_demo_access import load, save
from product_live_session import LiveSession, require
from vultr_credit_guard import run as credit_guard
from vultr_phase1 import PLANS, PRICES, PRIVATE, ROOT, Admin

from api.app.auth import SessionSecrets, csrf_digest, session_digest
from worker.protocol import authority_id

ORIGIN = "https://158.247.227.66:8443"
LATEST = PRIVATE / "guest-demo-latest.json"


def guard_command():
    digest = hashlib.sha256((ROOT / 'scripts/guest_demo_guard.py').read_bytes()).hexdigest()
    return '/usr/bin/python3 -I -B /opt/proofflow-guest-demo/' + digest + '/guest_demo_guard.py'


def host(admin, command, raw=None, timeout=60):
    r = admin.host("control", command, stdin=raw, timeout=timeout)
    if r.returncode:
        (PRIVATE / "evidence/guest-demo-host-failure.txt").write_bytes(r.stdout + r.stderr)
        raise RuntimeError("GUEST_ADMIN_FAILED_RECONCILE_SAVED_EVIDENCE")
    return r.stdout.strip()


def setup_guard(admin):
    names = ("guest_demo_guard.py", "install_guest_demo_guard.py", "install_product_services.py")
    files = {n: (ROOT / "scripts" / n).read_bytes() for n in names}
    digest = hashlib.sha256(b"".join(files.values())).hexdigest()
    target = "/opt/proofflow-public-setup/" + digest
    program = """import base64,json,os,sys
from pathlib import Path
v=json.loads(sys.stdin.buffer.read());p=Path(v['target']);p.mkdir(mode=0o700,exist_ok=True)
for n,raw in v['files'].items():
 assert n in ('guest_demo_guard.py','install_guest_demo_guard.py','install_product_services.py')
 q=p/n;b=base64.b64decode(raw)
 if q.exists():assert q.read_bytes()==b
 else:
  with q.open('xb') as f:f.write(b)
 q.chmod(0o400)
"""
    host(
        admin,
        "/usr/bin/python3 -I -c " + shlex.quote(program),
        json.dumps(
            {"target": target, "files": {n: base64.b64encode(b).decode() for n, b in files.items()}}
        ).encode(),
    )
    launch = (
        "import sys,runpy;sys.path.insert(0,"
        + repr(target)
        + ");runpy.run_path("
        + repr(target + "/install_guest_demo_guard.py")
        + ',run_name="__main__")'
    )
    return json.loads(host(admin, "/usr/bin/python3 -I -c " + shlex.quote(launch)))


def run_local(script):
    require(
        script in ("refresh_product_quote.py", "deploy_product_services.py"),
        "DEMO_SCRIPT_NOT_ALLOWED",
    )
    r = subprocess.run(  # noqa: S603 - fixed reviewed local administrator scripts
        [sys.executable, "-X", "utf8", str(ROOT / "scripts" / script)],
        cwd=ROOT,
        capture_output=True,
        timeout=240,
    )  # noqa: S603
    (PRIVATE / "evidence" / ("guest-demo-" + script + ".log")).write_bytes(r.stdout + r.stderr)
    require(r.returncode == 0, "DEMO_PREPARATION_FAILED_RECONCILE_NO_BLIND_RETRY")


def start(seconds=1800):
    require(type(seconds) is int and 20 <= seconds <= 1800, "DEMO_DURATION_INVALID")
    print('Checking credits, current prices and the server safety guard. No model call is made.',
          flush=True)
    admin = Admin()
    try:
        credit = credit_guard(admin, datetime.now(UTC))
        require(credit["credit_guard"] == "within_early_cutoff", "DEMO_CREDIT_CLOSED")
        require(
            "https://" + admin.state["hosts"]["control"]["address"] + ":8443" == ORIGIN,
            "PUBLIC_ORIGIN_CHANGED",
        )
        plans = {p["id"]: p for p in admin.request("GET", "/plans?per_page=500")["plans"]}
        require(
            {role: plans[plan]["monthly_cost"] for role, plan in PLANS.items()} == PRICES,
            "VM_QUOTE_CHANGED",
        )
        guard = setup_guard(admin)
        command = guard_command()
        status = json.loads(host(admin, command + " check"))
        require(status["state"] in ("CLOSED", "UNCONFIGURED"), "DEMO_ALREADY_ACTIVE_USE_OPEN")
        host(admin, "systemctl start proofflow-product-retention.service")
    finally:
        admin.close()
    # Fresh official catalogue, fixed existing prices, immutable config replacement.
    run_local("refresh_product_quote.py")
    run_local("deploy_product_services.py")
    print('Preparing your expiring guest session; credentials stay on this computer.', flush=True)
    with LiveSession() as live:
        require(
            live.sql("SELECT count(*) FROM pf_product.workspaces;") == b"0",
            "DEMO_REQUIRES_NO_EXISTING_WORKSPACES",
        )
        quote = json.loads(live.host("cat /etc/proofflow-repair/config.json"))["quote"]
        now = datetime.now(UTC)
        deadline = now + timedelta(seconds=seconds)
        require(
            deadline + timedelta(minutes=2) < datetime.fromisoformat(quote["valid_until"]),
            "DEMO_QUOTE_TOO_SHORT",
        )
        require(
            deadline < datetime.fromisoformat(live.credit["review_due_at"]),
            "DEMO_FUNDING_TOO_SHORT",
        )
        workspace, window, secret = str(authority_id()), str(uuid4()), SessionSecrets.create()
        value = {
            "window_id": window,
            "workspace_id": workspace,
            "started_at": now.isoformat(),
            "expires_at": deadline.isoformat(),
            "funded_until": live.credit["review_due_at"],
            "quote_until": quote["valid_until"],
            "boot_id": live.host("cat /proc/sys/kernel/random/boot_id").decode(),
            "state": "ACTIVE",
        }
        receipt = PRIVATE / "evidence" / ("guest-demo-" + window + ".json")
        record = {
            "window": value,
            "state": "PREPARING",
            "credit": live.credit,
            "guard": guard,
            "model_calls_by_launcher": 0,
            "new_resources": 0,
        }
        receipt.write_text(json.dumps(record, indent=2), encoding="utf-8")
        try:
            live.sql(
                "SET ROLE pf_product_provisioner; SELECT pf_product.create_workspace('"
                + workspace
                + "','guest','"
                + deadline.isoformat()
                + "');"
                "SELECT pf_product.create_session('"
                + workspace
                + "','"
                + session_digest(secret.token)
                + "','"
                + csrf_digest(secret.csrf)
                + "','"
                + deadline.isoformat()
                + "');"
            )
            access = {
                "window_id": window,
                "workspace_id": workspace,
                "expires_at": deadline.isoformat(),
                "origin": ORIGIN,
                "token": secret.token,
                "csrf": secret.csrf,
            }
            filename = save(access)
            record["access_file"] = filename
            receipt.write_text(json.dumps(record, indent=2), encoding="utf-8")
            status = json.loads(live.host(command + " arm", json.dumps(value).encode()))
            require(status["state"] == "ACTIVE", "DEMO_NOT_ARMED")
            with client_for(access) as client:
                response = client.get("/v1/session")
                require(
                    response.status_code == 200 and response.json()["kind"] == "guest",
                    "LIVE_GUEST_READBACK_FAILED",
                )
            record.update(state="ACTIVE", quote=quote, monthly_vm_quotes=PRICES)
            receipt.write_text(json.dumps(record, indent=2), encoding="utf-8")
            pointer = {"access_file": filename, "receipt": receipt.name,
                       "expires_at": value["expires_at"]}
            pending = LATEST.with_suffix(".pending")
            with pending.open("x", encoding="utf-8") as output:
                output.write(json.dumps(pointer))
                output.flush()
                os.fsync(output.fileno())
            os.replace(pending, LATEST)
        except Exception:
            live.host(command + " close")
            record["state"] = "FAILED_ADMISSION_CLOSED"
            receipt.write_text(json.dumps(record, indent=2), encoding="utf-8")
            raise
    return record


def client_for(access):
    return httpx.Client(
        base_url=access["origin"],
        trust_env=False,
        timeout=20,
        limits=httpx.Limits(max_keepalive_connections=0),
        headers={
            "Cookie": "__Host-proofflow=" + access["token"],
            "Origin": access["origin"],
            "X-ProofFlow-CSRF": access["csrf"],
        },
    )


def current():
    value = json.loads(LATEST.read_bytes())
    require(set(value) == {'access_file', 'receipt', 'expires_at'}
            and re.fullmatch(r'guest-demo-[a-f0-9-]{36}\.json', value['receipt']) is not None,
            'GUEST_POINTER_INVALID')
    return value


def stop():
    latest = current()
    record = json.loads((PRIVATE / "evidence" / latest["receipt"]).read_bytes())
    admin = Admin()
    try:
        status = json.loads(host(admin, guard_command() + " close"))
        try:
            access = load(latest["access_file"])
        except RuntimeError:
            access = None  # Expired sessions cannot authorize deletion; retention owns it.
        if access is not None:
            with client_for(access) as client:
                response = client.post(
                    "/v1/workspace/delete",
                    json={"workspace_id": access["workspace_id"], "confirm": True},
                )
                require(response.status_code in (200, 403), "DEMO_DELETE_RECONCILE")
        host(admin, "systemctl start proofflow-product-retention.service")
        record.update(state="CLOSED", closed_at=datetime.now(UTC).isoformat())
        (PRIVATE / "evidence" / latest["receipt"]).write_text(
            json.dumps(record, indent=2), encoding="utf-8"
        )
        return status
    finally:
        admin.close()


def sign_in_and_stage(page, access):
    """Stage disclosed synthetic files only; the guest must choose every approval."""
    from check_phase6_browser import variants
    from playwright.sync_api import expect

    page.goto(access['origin'], wait_until='networkidle')
    page.locator('#session-token').fill(access['token'])
    page.locator('#csrf-token').fill(access['csrf'])
    page.locator('#login button').click()
    expect(page.locator('#workspace')).to_be_visible()
    require(not page.locator('#session-token').input_value()
            and not page.locator('#csrf-token').input_value(), 'LOGIN_FIELDS_NOT_CLEARED')
    _, _, _, files = next(variants(access['window_id']))
    for kind, name in (('pipeline', 'pipeline.py.txt'), ('transactions', 'transactions.csv'),
                       ('customers', 'customers.csv'), ('contract', 'contract.json')):
        page.locator('#' + kind).set_input_files({'name': name.removesuffix('.txt'),
                                                'mimeType': 'text/plain', 'buffer': files[name]})
    page.locator('#notice').evaluate('(node, text) => node.textContent = text',
        'Synthetic demo files selected locally. Click Upload and review, then approve only '
        'after reading the contract. Guest window ends ' + access['expires_at'] + '.')
    expect(page.locator('#run')).to_be_disabled()
    expect(page.locator('#confirm-contract')).not_to_be_checked()
    return files


def require_active_window(access):
    admin = Admin()
    try:
        credit = credit_guard(admin, datetime.now(UTC))
        require(credit['credit_guard'] == 'within_early_cutoff', 'DEMO_CREDIT_CLOSED')
        status = json.loads(host(admin, guard_command() + ' check'))
        value = json.loads(host(admin, 'cat /etc/proofflow-guest-demo/window.json'))
        require(status['state'] == 'ACTIVE' and value['window_id'] == access['window_id']
                and value['expires_at'] == access['expires_at'], 'DEMO_WINDOW_CLOSED')
    finally:
        admin.close()


def open_browser():
    from playwright.sync_api import sync_playwright

    try:
        latest = current()
        access = load(latest["access_file"])
        with client_for(access) as client:
            require(client.get("/v1/session").status_code == 200, "GUEST_ACCESS_REVOKED")
        record = json.loads((PRIVATE / "evidence" / latest["receipt"]).read_bytes())
        require(record["state"] == "ACTIVE", "DEMO_WINDOW_CLOSED")
        require_active_window(access)
    except (FileNotFoundError, RuntimeError):
        start()
        access = load(current()["access_file"])
    print(
        "Opening your guest browser. This demo window closes in at most 30 minutes."
    )
    print("Use synthetic data only. Review and approve the contract and exact version yourself.")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(viewport={"width": 1366, "height": 900})
        page = context.new_page()
        sign_in_and_stage(page, access)
        # Memory-only browser cookies: no persistent profile or storage_state file.
        while browser.is_connected() and datetime.now(UTC) < datetime.fromisoformat(
            access["expires_at"]
        ):
            try:
                page.wait_for_timeout(1000)
            except Exception:
                break
        browser.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("start", "open", "stop"))
    parser.add_argument("--seconds", type=int, default=1800)
    args = parser.parse_args()
    if args.operation == "open":
        open_browser()
    elif args.operation == "stop":
        print(json.dumps(stop()))
    else:
        record = start(args.seconds)
        print(
            json.dumps(
                {
                    "state": record["state"],
                    "expires_at": record["window"]["expires_at"],
                    "credential_output": False,
                    "provider_calls": 0,
                }
            )
        )


if __name__ == "__main__":
    main()
