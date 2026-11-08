# Judge review guide

ProofFlow repairs small merchant revenue-import programs with Vultr inference,
executes every candidate on a separate isolated worker, and checks actual output
against source-derived expectations before an exact version can process a new batch.

## Start with the recorded workflow

1. [Watch or download the narrated 3m03s demonstration](https://github.com/arslanabdulghaffar/ProofFlow/releases/download/v0.1.0-hackathon/ProofFlow-demo-narrated.mp4).
   It shows an original ownership error, a real Vultr repair, three fresh matching
   checks, exact automated test approval and a completed fresh batch. A separately
   labeled infinite-loop execution is terminated with cleanup confirmed.
2. [Read the eight-slide PDF](https://github.com/arslanabdulghaffar/ProofFlow/releases/download/v0.1.0-hackathon/ProofFlow-deck-submission.pdf)
   or [download the editable deck](https://github.com/arslanabdulghaffar/ProofFlow/releases/download/v0.1.0-hackathon/ProofFlow-deck-submission.pptx).
3. Inspect the [comparison and all denominators](../eval/final-comparison-2026-11-06.md),
   [actual public guest acceptance](../docs/evidence/phase6-guest-operation-2026-11-08.json),
   [architecture](../docs/architecture.md) and [contract](../docs/contract.md).

The video retains original recorded results with synthetic narration, a guide-cursor
overlay, slower playback and pauses. Dated private/review labels describe its preparation
stage; the owner approved publication on November9. This is not a livestream. The
[edit manifest](https://github.com/arslanabdulghaffar/ProofFlow/releases/download/v0.1.0-hackathon/narrated-demo-edit-manifest.json)
identifies edits, pauses and receipt summaries. Automated approvals are test actions,
not independent human sign-off. The downloadable source is MIT licensed.

## Live execution

[Open the Vultr-hosted application](https://158.247.227.66:8443/).
Select synthetic-only consent and **Start demo**, then **Load synthetic example**.
No account, invitation, owner launcher or cloud credential is needed. Each visitor gets
a separate workspace, lasting at most30 minutes; cleanup begins five minutes early.
Capacity and the shared demo budget can temporarily close access.

1. Click **Upload and review** and read the contract before approving it.
2. Run the original. The example deliberately joins customers without their merchant;
   inspect the wrong-owner evidence even though totals match.
3. Request repair and refresh its recorded status. Vultr proposes real code; fresh
   isolated runs and protected checks determine whether it passes.
4. Inspect the diff/evidence, then prepare and review the exact version preview.
   Approve only if you agree with that version.
5. Upload a fresh compatible synthetic CSV pair, run a fresh batch and download evidence.

The [November9 acceptance](../docs/evidence/phase6-judge-access-2026-11-09.json) passed
this path with two actual model calls and a completed fresh batch. Automated test
approvals are not independent human sign-off. A guest cannot authorize GitHub writes.
Public visitors are not verified as judges. If capacity is full, use the recording and retry later.

## Scope and limits

This is a synthetic-data hackathon prototype, not a production finance service.
ProofFlow repaired 15/18 repairable cases in the frozen comparison; the deterministic
rebuild repaired 18/18. No AI-superiority or customer-ROI claim is made. Full
compromised-host reconstruction and independent human security review are unproven.
Offline recovery-key custody is owner-deferred. Post-event hosting depends on provider
account access and renewed funded reviews within the credit-only limits.
