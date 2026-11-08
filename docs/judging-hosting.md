# Judging hosting operations

Owner authorized self-service judge access and credit-only judging hosting on November9.
The public URL is https://158.247.227.66:8443. Start demo creates a new guest identity;
it does not approve contracts, versions or external actions. The main repository is
public/MIT; ProofFlow-Demo stays private. [Acceptance](evidence/phase6-judge-access-2026-11-09.json).

## Current controls

- Existing two VMs only: $24+$48/month; approximately $36 for14 further days.
  Observed credit $187.35; $145 reservations; $150 project/$25 inference caps unchanged.
- Current funded review ends **November11 03:13:23 KST**. Final resource teardown remains
  **November23 09:00 KST**. Credit expiry is December4. No personal payment is authorized.
- Guest access lasts30 minutes; normal retention begins five minutes early. At most8
  retained workspaces,128 lifetime claims, and one claim per10 seconds. Do not reset
  counters to hide abuse or exceed the original funding envelope.
- A source-pinned root timer renews a three-minute new-guest lease every minute. It
  reads the fixed provider catalogue before the one-hour quote has40 minutes left.
  Only the reviewed model and unchanged rates are accepted. No catalogue read is an
  inference call. The dispatcher reloads validated quotes between work steps.
- Expiry, reboot, invalid configuration, blocked budget or failed checks close access.
  Guard failures latch closed; they are not automatically rearmed. Guest code gets no
  network, secrets, SQL, cloud management or GitHub authority.
- Scheduled backup can read an open but idle application without changing admission.
  Active jobs/repairs still cause a retry. Restores clear all25 authority tables,
  including judge admission. A restored clone cannot authorize live execution.

## Recurring maintenance

The desktop heartbeat `maintain-proofflow-judging-access` runs every four hours.
Keep the computer on, online, and the desktop app running for these local checks.
The Windows credit guard and backup tasks remain installed. The server admission
guard operates independently, but it cannot destroy billable VMs without the local
management credential. Provider hard-stop/tax and future account access are unknown;
application caps are not a provider billing guarantee.

From the project root, use the existing virtual environment:

```powershell
.venv\Scripts\python.exe -X utf8 scripts\judge_hosting.py status
.venv\Scripts\python.exe -X utf8 scripts\check_operations.py
```

Status must show the timer active, service success, enabled admission and a current
claim lease (unless intentionally draining). Read the deployed source hashes through
the helper. Do not rerun model acceptance merely to refresh a timestamp.

When less than24 hours remain in the funded window:

1. Run `scripts/judge_hosting.py drain` with the same Python. This closes new claims,
   while existing sessions and work continue. Wait until active guests are zero and
   jobs/repairs/PR leases are terminal. Do not cancel a judge's work for convenience.
2. Run `scripts/judge_hosting.py close`, then the existing
   `scripts/review_credit_window.py --apply --review-date YYYY-MM-DD` using the actual
   KST date. It verifies account/quotes, exact resources, caps and unchanged reservations
   before extending by at most48 hours. For an existing intent use `--inspect` first;
   never retry an uncertain review blindly or clear a credit stop latch.
3. After successful exact readback, run `scripts/judge_hosting.py arm`. It rechecks
   credit, the pinned guard and closed/idle policy, updates the current funded window,
   and enables the timer. Then verify status and public HTTPS without a model call.
4. Record meaningful changes and checkpoint them; verify the remote SHA. If the provider
   demands personal payment or any cap/identity/rate fails, preserve the specific blocker
   and leave admission closed. No repeated owner question is needed for ordinary work.

At the final deadline, the existing credit guard deletes only exact owned resources.
Verify removal and preserve the receipt; stopping a VM alone does not end Vultr billing.
Keep the submitted recording and repository available afterward.

## Review and limitations

Separate critical review covered public bootstrap grants, origin/CSRF, rate/cap
serialization, quote publication, failure latching, backup concurrency and restoration
authority. Actual browser testing caught a0400 quote-file permission defect under root's
077 umask; fchmod0444 and atomic publication fixed it. Real Linux and host probes passed.
The failed test receipts are preserved; no status or expected output was edited.

The public route verifies synthetic-only consent and guest isolation, not judge identity.
Abuse can consume limited capacity or the shared inference budget. Availability can
therefore close safely. Offline key custody remains owner-deferred; full compromised-host
reconstruction and independent human security approval are not claimed. General readiness
continues to report503 for these broader incomplete acceptance conditions, while liveness
and the specifically tested judge workflow pass.
