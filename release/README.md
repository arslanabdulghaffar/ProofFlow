# Private release review package

This package is ready for private review. It is not a submission or public release.
Keep the repository and package private. Offline key custody was deferred by the owner;
it is not silently completed or a prerequisite for unrelated package preparation.

The November8 guest TLS and live AI follow-ups are newer than the recorded demonstration. Public
login: https://158.247.227.66:8443. Four fresh guest browser cases and security/restart
checks passed without certificate bypass. A later bounded guest run demonstrated two
real Vultr calls, rejection then verified repair, and a completed fresh batch. Test
sessions were revoked; owner demo windows are separately limited to30 minutes. This is
invited access, not anonymous AI. The existing video retains its original runtime/date;
it does not depict the later guest run. New packages include both acceptance receipts.

## Contents

| File | Purpose |
| --- | --- |
| `ProofFlow-deck.pptx` | Eight editable slides; actual screenshot, native evidence tables and source notes |
| `ProofFlow-cover.png` | Standalone1920×1080 cover matching the product palette |
| `ProofFlow-demo.mp4` |139.04s captioned private real-AI recording; edits and separate containment disclosed |
| `submission.json` / `submission-copy.md` | Draft event fields, descriptions, tags and explicit missing public URLs |
| `SOURCE.zip` | Exact committed tracked project snapshot; no Git history or machine-local secrets |
| `setup.md` | Safe offline review and actual infrastructure boundaries |
| `demo-edit-manifest.json` | Original recording hashes and edit/hold/card provenance |
| `evidence/` | Selected sanitized acceptance records and measured comparison report |
| `MANIFEST.json` | SHA-256 and byte length of each bundled file; source commit and gate status |

The ZIP intentionally excludes credentials, DPAPI files, backups, plaintext database
dumps, raw provider responses, protected canary rows, source handoff PDF, environments,
tool caches and browser profiles. The deck's screenshot contains synthetic identifiers.
Candidate programs in source/evaluation files remain inert text: never run them on the
development computer, control host or verifier.

## Release gates still open

| Gate | Current status |
| --- | --- |
| Ownership and permissive license | Owner clearance pending; no license issued |
| Public repository / media | Remain private; no publication or submission |
| Authenticated submission form / enrollment / absolute deadline | Not verified; public countdown text is zero |
| Guest/public TLS smoke | Passed four external contexts and scoped security/restart checks; invited access |
| Offline password and recovery kit | Owner deferred |
| Lost deletion authority / compromised-host restore | Still blocked by design / not tested |
| Independent human security review | No reviewer confirmed; automated/Codex review is not sign-off |
| Judging-period hosting | Existing cutoff Nov10 01:29 KST; later funding needs fresh review within caps |

No new paid service or inference request is needed to inspect this package. The most
recent documented credit observation was$189.06 on Nov8 KST, not a fresh balance promise. Limits
remain$150 total/$25 inference in eligible credits, with no personal payment authorized.

## Building and checking the package

Document authoring uses the configured bundled `@oai/artifact-tool` runtime, not an
application dependency. Read `release/build-deck.mjs` for required runtime environment
paths. Its three arguments are repository root, private build workspace and existing
private demo evidence directory. Use a new workspace for each revision; the finalizer
does not overwrite existing final files. The private screenshot is hash-checked against
its original receipt. The source does not call cloud APIs or execute candidate code.

`build-cover.mjs` writes the standalone cover; `render-deck.mjs` renders a final PPTX for
visual review. All eight final slides were inspected; the deck has three native tables.
Native PowerPoint playback itself was not tested. No PDF or public-hosted version is
claimed. If the final event form requires another format, adapt it after inspecting
the form rather than claiming that a guessed limit is authoritative.

`scripts/build_release_package.py` accepts only a clean committed project and explicit
reviewed artifact paths. It uses `git archive` for the exact commit, fixed manifest
entries and SHA-256 readback; no upload/submission action exists. Its `--verify` mode
checks the finished ZIP without extracting or executing its contents. It also compares
documents and media with their committed source/pins. Supply `--expected-sha256` from
the separately trusted private checkpoint receipt to verify archive identity. A package
manifest alone proves internal consistency, not the identity of its publisher. New v2
manifests require the complete document/media set; older v1 packages remain checkable.
