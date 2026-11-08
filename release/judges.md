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
The application currently uses individual invited guest sessions, lasting at most
30 minutes. This URL alone does not grant execution. No shared judge password,
Vultr account access or GitHub App credentials are distributed in the public release.
Live judge-session delivery is still pending; the recorded workflow and source are
available without login. This limitation must be included in the submission.

When an individual session is issued, enter its session and CSRF values only into
that HTTPS application. Use synthetic data only. Review each contract and exact code
version yourself. The flow is Upload and review → Approve contract → Run original →
Request repair → Inspect evidence → Prepare/review/approve exact version → Run fresh
batch. A guest cannot authorize an external GitHub action.

The owner can issue a fresh window using the existing configured launcher described
in [setup](setup.md). That administrative launcher and its local credentials must not
be shared with judges. Opening a window rechecks credit and prices; expiry closes
admission even if the owner's computer disconnects.

## Scope and limits

This is a synthetic-data hackathon prototype, not a production finance service.
ProofFlow repaired 15/18 repairable cases in the frozen comparison; the deterministic
rebuild repaired 18/18. No AI-superiority or customer-ROI claim is made. Full
compromised-host reconstruction and independent human security review are unproven.
Offline recovery-key custody is owner-deferred. Post-event hosting depends on provider
account access and renewed funded reviews within the credit-only limits.
