# Environment readiness — 2026-10-24 KST

## Kickoff update — 2026-11-04 KST

Historical observations below describe Oct 24 only. Current branch main is an established private repository. Python app dependencies are now installed in ignored `.venv`; a fresh runtime-only `.venv-runtime-check` succeeded. Local Windows Python 3.12.10, uv 0.13.5. Trusted image uses Python 3.12.16 / Debian trixie linux/amd64; build and non-root/read-only health smoke succeeded with Docker 29.9.1 in WSL. Its temporary test container was removed. No candidate code or candidate sandbox ran locally. No Vultr resources, inference or deployed acceptance. See [readiness evidence](phase1-readiness.md) for versions, limits and exact remaining gates.

Observed on this computer, not a deployment test. Workspace `A:\hackathon\ProofFlow` was empty and not a Git repository. No AGENTS.md existed at workspace or applicable drive/parent paths before changes. Cloned the user's exact repository into the empty folder; nothing was overwritten.

| Area | Actual observation | Readiness |
| --- | --- | --- |
| OS/shell | Windows NT 10.0.26300.0, PowerShell | Ready for trusted local preparation |
| Git | 2.49.0.windows.1; Git Credential Manager configured; existing user identity configured | Authenticated local HTTPS read works |
| Repository | REST API full_name arslanabdulghaffar/ProofFlow, private=true, visibility=private, default_branch=main, size=0; branches=[] | Empty repository is valid; no existing history or user changes |
| Advertised permission | Authenticated local credential queried GitHub API: pull/push/maintain/admin true | Advertised permission only; actual push recorded in progress |
| Protection visibility | Repository rulesets API returned HTTP 403; no existing branch to inspect | Protection state not proven absent; normal push must obey server enforcement; no bypass attempted |
| Connector vs Git | No connected GitHub app used; Git/GCM credential was tested directly | Connector permission not inferred; no credentials printed/stored in project |
| GitHub CLI | gh unavailable | Not blocking; Git plus authenticated API checks suffice |
| Python | System 3.12.10; isolated `.venv-tools` created and version checked | Trusted preparation checker ready; application dependencies not installed |
| uv | 0.13.5 installed from verified PyPI wheel in `.venv-tools`; --version passed | Local dependency manager ready |
| Secret scanner | Gitleaks 8.30.1 downloaded from its official release, SHA-256 verified | Local scanner available; staged scan result recorded in progress |
| Node/npm | System Node 26.3.1/npm 11.16.0 observed; side-by-side `.tools/node-v24.22.1-win-x64` Node 24.22.1/npm 11.19.1 checked | LTS preparation tool available without modifying global install/PATH |
| WSL | Ubuntu-24.04, WSL2 kernel 6.18.54.1; Python 3.12.3 | Linux tooling exists; not designated candidate worker |
| Docker | WSL Docker client/server 29.9.1; cgroup v2; daemon responds | Read-only daemon inspection only; no candidate or probe container run |
| runsc | No runsc executable or registered runtime found; only runc variants | NOT READY for sandbox; Phase 1 dedicated worker required |
| Other Linux tooling | psql/make/uv/node not found by command lookup in WSL | Install needed tools in chosen trusted environment at kickoff; no app install claim |
| PDF | Poppler pdfinfo/pdftoppm and bundled pypdf used | All 59 pages extracted/read; selected diagram/tables rendered |
| Vultr/account/domain/App | No authenticated account/runtime/inference/product-App checks | NOT RUN; timing/access/charges gates apply |

Installed files are ignored local tools; no global dependency replacement or cloud resource creation. Downloads verified against official distribution SHA-256 before install/extraction:

- Node `https://nodejs.org/dist/v24.22.1/node-v24.22.1-win-x64.zip`; SHA-256 `d2046d28c2c3dcd211ac5145c0bf30e2047ef9dfb306693c8c6e2eccd8b95fa5`, matched SHASUMS256.txt from that distribution directory.
- uv `uv-0.13.5-py3-none-win_amd64.whl`; SHA-256 `1fb29fc46ba12033e2ef95a95ac79d649e71bbb1358419bbbcbd19d86026ef2f`, matched PyPI metadata; installed `--no-index --no-deps` from the downloaded wheel.
- Gitleaks `https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/gitleaks_8.30.1_windows_x64.zip`; SHA-256 `d29144deff3a68aa93ced33dddf84b7fdc26070add4aa0f4513094c8332afc4e`, matched the release checksums file; extracted under `.tools/gitleaks`.

Reproduce preparation tooling with Python 3.12 venv + that pinned uv wheel and the Node archive/checksum. This hash check confirms distribution byte integrity, not a full supply-chain audit. Pin exact application Python/Node/pandas/Next/FastAPI dependencies, lockfiles and Linux image digests in Phase 1 after compatibility/security review; the local versions are not a release manifest.

Available commands now (PowerShell from repository):

```powershell
python scripts/check_preparation.py
& .\.venv-tools\Scripts\uv.exe --version
& .\.tools\node-v24.22.1-win-x64\node.exe --version
& .\.tools\node-v24.22.1-win-x64\npm.cmd --version
git status --short --branch
```

If Git authentication later expires: install/use GitHub CLI and run `gh auth login --hostname github.com --git-protocol https --web`, then `gh auth setup-git`, or complete Git Credential Manager's browser sign-in. Ensure the signed-in account has access to the exact private repository. Never paste tokens/passwords/private keys into chat. Current session did not need a login.
