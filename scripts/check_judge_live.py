"""One real public guest flow. Automated synthetic approvals are not human sign-off."""

import json
import time
from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx
from check_guest_demo_live import counts
from check_phase6_browser import version_rehearsal
from playwright.sync_api import expect, sync_playwright
from product_live_session import require
from vultr_phase1 import PRIVATE

ORIGIN = "https://158.247.227.66:8443"


def main():
    path = PRIVATE / "evidence/judge-live-2026-11-09-r3.json"
    require(not path.exists(), "RECONCILE_PREVIOUS_JUDGE_TEST")
    record = {
        "started_at": datetime.now(UTC).isoformat(),
        "completed": False,
        "checks": [],
        "synthetic_automated_approvals_not_human_signoff": True,
    }

    def save():
        path.write_text(json.dumps(record, indent=2), encoding="utf-8")

    save()
    before = counts()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1366, "height": 900})
        page = context.new_page()
        page.goto(ORIGIN, wait_until="networkidle")
        expect(page.locator("#judge-start")).to_be_disabled()
        page.locator("#judge-consent").check()
        page.locator("#judge-start").click()
        expect(page.locator("#workspace")).to_be_visible(timeout=20000)
        cookies = {c["name"]: c["value"] for c in context.cookies()}
        with httpx.Client(
            base_url=ORIGIN,
            verify=True,
            trust_env=False,
            follow_redirects=False,
            timeout=30,
            cookies=cookies,
            headers={"Origin": ORIGIN, "X-Proofflow-CSRF": cookies["__Host-proofflow-csrf"]},
        ) as client:
            identity = client.get("/v1/session").json()
            record["workspace"] = identity["workspace_id"]
            save()
            try:
                require(identity["kind"] == "guest", "GUEST_REQUIRED")
                page.locator("#judge-example").click()
                expect(page.locator("#notice")).to_contain_text("Synthetic example selected")
                require(
                    counts()["approvals"] == before["approvals"], "UNEXPECTED_AUTOMATIC_APPROVAL"
                )
                example = client.get("/static/judge-example.json").json()
                files = {
                    ("pipeline.py.txt" if k == "pipeline" else v["name"]): v["text"].encode()
                    for k, v in example.items()
                }
                page.locator("#files button").click()
                expect(page.locator("#confirm-contract")).to_be_enabled()
                expect(page.locator("#run")).to_be_disabled()
                page.locator("#confirm-contract").check()
                page.locator("#approve").click()
                expect(page.locator("#run")).to_be_enabled()
                page.locator("#run").click()
                page.wait_for_url("**/?job=*", timeout=20000)
                record["job"] = str(UUID(page.url.split("?job=", 1)[1]))
                save()
                expect(page.locator("#state")).to_have_text("Needs review", timeout=120000)
                original = client.get("/v1/jobs/" + record["job"] + "/summary").json()
                require(original["outcome"] == "mismatch", "EXPECTED_SOURCE_MISMATCH")
                record["original"] = original
                save()
                # A second unprivileged visitor cannot inspect this workspace.
                time.sleep(11)  # Respect the global 10-second guest admission throttle.
                with httpx.Client(
                    base_url=ORIGIN, verify=True, trust_env=False, timeout=20
                ) as other:
                    rejected = other.post(
                        "/v1/judge/start",
                        headers={"Origin": "https://evil.example"},
                        json={"synthetic_only": True},
                    )
                    require(rejected.status_code == 403, "CROSS_ORIGIN_ACCEPTED")
                    second = other.post(
                        "/v1/judge/start", headers={"Origin": ORIGIN}, json={"synthetic_only": True}
                    )
                    record["second_guest_status"] = second.status_code
                    record["second_guest_error"] = second.json().get("error", {}).get("code")
                    save()
                    require(second.status_code == 200, "SECOND_GUEST_UNAVAILABLE")
                    second_id = second.json()["workspace_id"]
                    require(second_id != identity["workspace_id"], "SHARED_WORKSPACE")
                    require(
                        other.get("/v1/jobs/" + record["job"]).status_code in (403, 404),
                        "CROSS_GUEST_READ",
                    )
                    other.post(
                        "/v1/workspace/delete",
                        headers={
                            "Origin": ORIGIN,
                            "X-Proofflow-CSRF": other.cookies["__Host-proofflow-csrf"],
                        },
                        json={"workspace_id": second_id, "confirm": True},
                    ).raise_for_status()
                record["checks"] += [
                    "fresh_browser_no_owner_tokens",
                    "no_automatic_contract_approval",
                    "same_origin_required",
                    "separate_guest_cannot_read_other_job",
                ]
                version_rehearsal(page, client, files, uuid4().hex, record, save, real_ai=True)
                page.screenshot(
                    path=str(PRIVATE / "evidence/judge-live-2026-11-09-r3.png"), full_page=True
                )
                after = counts()
                require(after["prs"] == before["prs"], "UNEXPECTED_EXTERNAL_INTENT")
                record["provider_calls"] = after["calls"] - before["calls"]
                record["completed"] = True
            finally:
                deleted = client.post(
                    "/v1/workspace/delete",
                    json={"workspace_id": identity["workspace_id"], "confirm": True},
                )
                record["test_workspace_revoked"] = deleted.status_code == 200
                record["finished_at"] = datetime.now(UTC).isoformat()
                save()
        context.close()
        browser.close()
    print(
        json.dumps(
            {
                "completed": record["completed"],
                "checks": record["checks"],
                "provider_calls": record["provider_calls"],
                "receipt": path.name,
            }
        )
    )


if __name__ == "__main__":
    main()
