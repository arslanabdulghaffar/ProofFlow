# Private product GitHub integration setup

This is the product's dedicated integration, separate from development commits to ProofFlow. Setup does not approve a PR. No candidate is executed in GitHub or CI.

Current setup assistance: the in-app GitHub tab is at sign-in. Sign in yourself; never paste login codes or keys into chat. After that, the fields below can be filled together. No App credential is installed yet and no actual product PR has been created.

After the encrypted key is saved, the trusted administrator runs `scripts/prepare_github_app.py`. It checks local file ACLs, dedicated App permissions, selected installation, private repository identity, disabled Actions, absent hooks and the bounded base tree before passing the key over pinned SSH standard input to the fixed installer. Development Git authentication is used only for administrator read-only checks; it is never installed in the product. The installer requires closed admission and idle queues, preserves existing secret/config mismatches, and restarts the dispatcher with its dedicated private mount. These helpers have local/mock and Linux filesystem tests; actual account installation is still NOT RUN.

1. Create private **arslanabdulghaffar/ProofFlow-Demo** with a README and default branch main. No other files, workflows, webhooks, deployment or CI integrations. In Settings → Actions → General, disable Actions. Keep ProofFlow itself private.
2. Under your GitHub account Settings → Developer settings → GitHub Apps, create a private App for your account only. Use a descriptive name such as ProofFlow Demo. Homepage may be https://github.com/arslanabdulghaffar/ProofFlow. Disable the App webhook; no callback/user authorization URL is needed for this server integration.
3. Repository permissions: **Contents: read/write**, **Pull requests: read/write**, automatically required **Metadata: read**. No organization/account permissions and no event subscriptions.
4. Install the App on **only ProofFlow-Demo**, not all repositories or the ProofFlow source repository.
5. Generate/download its RSA private key. Run the following in PowerShell:

    powershell -NoProfile -File "A:\hackathon\ProofFlow\scripts\Save-GitHubAppCredential.ps1"

The helper asks for the non-secret App Client ID, installation ID, and local path to the downloaded PEM file. It encrypts the key with Windows user-bound DPAPI outside Git. Do not paste the key into chat, source, command arguments or environment files. Reply only that setup is saved, or name the non-secret screen where you are stuck.

Codex will verify the exact private repository, selected installation, minimal permissions, fixed base/path and absence of workflow files. The trusted product dispatcher will mint installation tokens restricted to that one repository. The API, candidate worker and verifier will receive no GitHub key. Draft PR dispatch still requires a concrete preview containing repository ID, base SHA, candidate/diff hash, path, draft body and exact operator approval. No merge/default-branch write or public release is authorized.

Sources checked Nov4: [App JWT authentication](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-json-web-token-jwt-for-a-github-app), [installation tokens and permissions](https://docs.github.com/en/rest/apps/apps), [draft pull requests](https://docs.github.com/en/rest/pulls/pulls), [Git references](https://docs.github.com/en/rest/git/refs).
