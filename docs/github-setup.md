# Private product GitHub integration setup

## Immediate local approval — avoids the chat round trip

Account/App setup is complete. The latest chat approval was processed at Nov5 08:41 KST, after its07:50 expiry; actual reconciliation confirms no PR/branch/write. Do not generate another short-lived chat request automatically. The owner can review and approve directly in one local terminal while the same preview remains valid:

```powershell
powershell -NoProfile -File "A:\hackathon\ProofFlow\scripts\Approve-Phase4PR.ps1"
```

The command creates one fresh read-only preview of the existing eligible version and opens its full destination/base/branch/title/body/diff in Notepad. Read it, then enter the exact `APPROVE <full digest>` text shown by the terminal. Enter alone cancels. The ten-minute expiry and all server-side authority checks remain unchanged. No credentials need to be copied. Do not pipe input or have Codex synthesize the confirmation: it is a direct human product action, not another standing development permission.

After confirmation, allow about four minutes. The helper uses normal API approval and the existing pinned dispatcher/SQL/App components; it discards the final real PR response once and lets the normal dispatcher recover after the natural lease expires. Then it checks exact GitHub commit/tree/source/PR readback, no duplicate writes, restart persistence and replay. No merge, CI execution, publication or new cloud service. A failure retains private evidence; do not retry blindly. The interactive path and live response-loss test are NOT RUN until the owner actually operates it. Local tests and PowerShell syntax checks passed.

Generated records are outside Git under deployment/evidence/phase4-pr-interactive-<id>.json, with a unique encrypted actor file. Final result is phase4-pr-result-<intent>.json; the prior chat records remain untouched. Codex should reconcile that receipt, update the Phase4 handoff and verify the private Git checkpoint after actual acceptance. It must not mark Phase4 complete from a preview or local test result.

This is the product's dedicated integration, separate from development commits to ProofFlow. Setup does not approve a PR. No candidate is executed in GitHub or CI.

Current setup, November5 KST: owner explicitly approved dedicated App creation/installation/key storage. ProofFlow Demo Arslan is registered and installed only on private ProofFlow-Demo, with Contents/Pull requests read-write and Metadata read-only, webhook off. Key encrypted outside Git and installed only in the deployed dispatcher. Actual restricted token/repository/tree preflight and deployed read-only PR preview passed. Actions remain disabled; both repositories private. [App receipt](evidence/phase4-app-installed-2026-11-05.json). Owner then approved removal of unused first key5183052; it is revoked, and working key5183074 authentication passed again. Never remove the working key. The exact PR answer was processed after preview expiry: no PR/branch/write exists. Fresh exact preview/approval must wait for the owner's availability; no setup repetition is needed. [Reconciliation](evidence/phase4-expired-approval-2026-11-05.json).

Windows helper correction: Set-Acl requested unavailable SeSecurityPrivilege. Preserve existing security descriptors and persist only modified owner/DACL through native FileSystemInfo.SetAccessControl. Actual encrypted save and owner/SYSTEM-only ACL readback passed. Administrator ACL validation now uses System.IO.File.GetAccessControl, avoiding inherited PowerShell module-path incompatibility. No permission relaxation, elevation, secret logging or Git credential reuse in product.

The trusted administrator completed `scripts/prepare_github_app.py`. It checks local file ACLs, dedicated App permissions, selected installation, private repository identity, disabled Actions, absent hooks and the bounded base tree before passing the key over pinned SSH standard input to the fixed installer. Development Git authentication is used only for administrator read-only checks; it is never installed in the product. The installer requires closed admission and idle queues, preserves existing secret/config mismatches, and restarts the dispatcher with its dedicated private mount. Actual account installation passed. The steps below are retained setup instructions, not remaining owner tasks.

1. Create private **arslanabdulghaffar/ProofFlow-Demo** with a README and default branch main. No other files, workflows, webhooks, deployment or CI integrations. In Settings → Actions → General, disable Actions. Keep ProofFlow itself private.
2. Under your GitHub account Settings → Developer settings → GitHub Apps, create a private App for your account only. Use a descriptive name such as ProofFlow Demo. Homepage may be https://github.com/arslanabdulghaffar/ProofFlow. Disable the App webhook; no callback/user authorization URL is needed for this server integration.
3. Repository permissions: **Contents: read/write**, **Pull requests: read/write**, automatically required **Metadata: read**. No organization/account permissions and no event subscriptions.
4. Install the App on **only ProofFlow-Demo**, not all repositories or the ProofFlow source repository.
5. Generate/download its RSA private key. Run the following in PowerShell:

    powershell -NoProfile -File "A:\hackathon\ProofFlow\scripts\Save-GitHubAppCredential.ps1"

The helper asks for the non-secret App Client ID, installation ID, and local path to the downloaded PEM file. It encrypts the key with Windows user-bound DPAPI outside Git. Do not paste the key into chat, source, command arguments or environment files. Reply only that setup is saved, or name the non-secret screen where you are stuck.

Codex will verify the exact private repository, selected installation, minimal permissions, fixed base/path and absence of workflow files. The trusted product dispatcher will mint installation tokens restricted to that one repository. The API, candidate worker and verifier will receive no GitHub key. Draft PR dispatch still requires a concrete preview containing repository ID, base SHA, candidate/diff hash, path, draft body and exact operator approval. No merge/default-branch write or public release is authorized.

Sources checked Nov4: [App JWT authentication](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-json-web-token-jwt-for-a-github-app), [installation tokens and permissions](https://docs.github.com/en/rest/apps/apps), [draft pull requests](https://docs.github.com/en/rest/pulls/pulls), [Git references](https://docs.github.com/en/rest/git/refs).
