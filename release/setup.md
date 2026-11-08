# Review and setup

## Inspect without credentials

Open the deck and cover locally, play the MP4, then read the measured comparison and
manifest. The packet is private. Do not upload it to a hosting site or change repository
visibility from these instructions.

For source review, extract `SOURCE.zip` into a new empty project folder and inspect the
root README, `AGENTS.md`, `docs/contract.md`, `docs/architecture.md`, `docs/threat-model.md`
and `docs/release.md`. The source includes inert synthetic/model-generated program text.
Do not import or run those programs outside the designated isolated worker.

With a trusted Python3.12 environment and the project's locked dependencies, the frozen
comparison can be checked offline:

```powershell
python -c "import json; from pathlib import Path; from eval.comparison_artifact import check; check(json.loads(Path('eval/final-comparison-2026-11-06.json').read_bytes())); print('Accounting verified; no live calls or candidate execution')"
```

This verifies stored accounting and hashes; it is not another live evaluation or proof
that a third party independently witnessed the provider requests. Do not rerun the
one-shot campaign, renewal, kernel maintenance or PR scripts to reproduce a table.

## Actual Vultr deployment

Two Vultr Compute VMs host the private product: control/API/dispatcher/PostgreSQL and a
separate gVisor execution worker. The restricted verifier lives on control and does not
execute source. Application-agent calls use the fixed Vultr Serverless Inference adapter.
Secrets are scoped to the trusted dispatcher/admin services and are never copied into
candidate sandboxes, this source archive or the package.

The public guest login is https://158.247.227.66:8443 with trusted IP TLS; four fresh
external guest contexts and security/restart checks passed. The separate operator path
remains pinned HTTPS/SSH. Test sessions were revoked and execution/inference admission
is closed after testing; an invited demo needs scoped access and a fresh operating review.
Normal authenticated operator flows require private account setup outside this package;
there is no shared judge password or key embedded here.

For a future authorized deployment, follow the checked-in provisioning/installation
runbooks with current account quotes, eligible credits, admission controls and exact
runtime pins. Do not copy another machine's credentials or automatically provision on
install. Existing$150 total/$25 inference caps and provider expiry restrictions apply.
No card, deposit or personal billing is authorized.

## Recovery and known limits

The Windows backup task is current-user and depends on the desktop being awake/logged
in. Actual nonempty encrypted capture and Windows-to-Linux inert recovery have passed.
Current trustworthy deletion authority remains mandatory; old snapshots cannot revive
deleted workspaces. The owner will handle offline password/kit custody later. A fully
reimaged compromised-host recovery and public-service RTO/RPO are not established.

## Owner’s individual guest launcher

Run `powershell -NoProfile -File "A:\hackathon\ProofFlow\scripts\Open-PublicDemo.ps1"` on
the already configured owner computer. It rechecks credits/prices and opens an individual
30-minute guest session in a dedicated browser, with synthetic inputs selected locally.
No upload, contract/version approval, inference request or PR happens automatically.
The server closes admission after the window even if the desktop goes offline. This
administrator helper requires existing private local setup; it is not a public signup
mechanism and should not be given to judges with account credentials.
