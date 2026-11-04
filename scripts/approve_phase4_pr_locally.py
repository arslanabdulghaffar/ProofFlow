"""Human-operated exact preview/approval in one local terminal, with normal expiry enforced."""

import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from complete_phase4_pr_approval import main as complete
from product_live_session import PRIVATE, require
from refresh_phase4_pr_preview import main as prepare


def confirm_exact(record, read_answer, clock):
    preview = record["pr"]
    digest = preview["preview_sha256"]
    require(type(digest) is str and re.fullmatch(r"[a-f0-9]{64}", digest), "PREVIEW_DIGEST_INVALID")
    expires = datetime.fromisoformat(preview["expires_at"])
    require(clock() < expires, "PREVIEW_EXPIRED_NO_WRITE")
    answer = read_answer("Type APPROVE " + digest + " to submit, or press Enter to cancel: ")
    require(answer == "APPROVE " + digest, "APPROVAL_CANCELLED_NO_WRITE")
    require(clock() < expires, "PREVIEW_EXPIRED_NO_WRITE")
    return digest


def main():
    # Refuse pipes/automation before creating a session or preparing a new intent.
    require(sys.stdin.isatty(), "INTERACTIVE_TERMINAL_REQUIRED_NO_ACTION")
    notepad = Path("C:/Windows/System32/notepad.exe")
    require(notepad.is_file(), "PREVIEW_VIEWER_UNAVAILABLE_NO_ACTION")
    destination = PRIVATE / "evidence" / ("phase4-pr-interactive-" + uuid4().hex + ".json")
    print("Preparing an exact private PR preview. No write is approved yet.", flush=True)
    record = prepare(destination, emit=False)
    artifact = Path(record["review_artifact"])
    require(
        artifact.parent == PRIVATE / "evidence" and artifact.is_file(), "PREVIEW_FILE_UNAVAILABLE"
    )
    # Notepad displays text only; no uploaded/generated source is imported or executed.
    subprocess.Popen([str(notepad), str(artifact)])  # noqa: S603 - fixed text viewer/owned artifact
    expiry = datetime.fromisoformat(record["pr"]["expires_at"]).astimezone(
        timezone(timedelta(hours=9))
    )
    print("Read the exact destination, branch, base, title, body and full diff in Notepad.")
    print("Preview file: " + str(artifact))
    print("Expires at " + expiry.strftime("%Y-%m-%d %H:%M:%S KST"))
    print("This creates one private draft PR only. No merge, CI execution or publication.")
    digest = confirm_exact(record, input, lambda: datetime.now(UTC))
    print("Submitting exact approval and checking recovery. Allow about 4 minutes.", flush=True)
    result = complete(digest, inject_reply_loss=True, record_path=destination)
    print("Verified private draft PR: " + result["external_readback"]["url"], flush=True)
    print("Evidence saved outside Git. Return to Codex to finish the verified phase checkpoint.")


if __name__ == "__main__":
    try:
        main()
    except (Exception, KeyboardInterrupt) as error:
        safe = {"INTERACTIVE_TERMINAL_REQUIRED_NO_ACTION", "APPROVAL_CANCELLED_NO_WRITE",
                "PREVIEW_EXPIRED_NO_WRITE", "PREVIEW_VIEWER_UNAVAILABLE_NO_ACTION"}
        code = (str(error) if str(error) in safe
                else "LOCAL_APPROVAL_STOPPED_RECONCILE_SAVED_EVIDENCE")
        raise SystemExit(code) from None
