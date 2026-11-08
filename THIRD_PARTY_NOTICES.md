# Ownership and attribution inventory

Local review tooling added November7: Go1.27.3 and golang.org/x/vuln/cmd/govulncheck1.9.0
(BSD-3-Clause), with official archive SHA/module checksum/tool hash in the
[Phase5 audit](docs/evidence/phase5-binary-acceptance-2026-11-07.json). These tools and
the pinned upstream gVisor C/source excerpts stay in ignored local storage;no runtime
application dependency or redistributed third-party source was added. Existing VM
Ubuntu kernel packages upgraded to signed noble-updates6.8.0-149.149;distribution
copyright/license files remain installed. This inventory is not MIT ownership clearance.

On November8,2026 the owner Arslan Abdul Ghaffar confirmed ownership and authorized
public release under MIT. The root LICENSE covers original ProofFlow code and
documentation. Third-party dependencies retain their own licenses and notices below;
this release does not redistribute their installed packages, images or model weights.
Earlier review notes about pending ownership describe the historical preparation state.

The engineering handoff is attributed in docs/source-review.md. Its PDF, extracted text and page images remain outside Git; redistribution rights have not been established. Repository documentation paraphrases the specification and records decisions rather than republishing the source.

Python foundation dependencies are now locked and installed; see inventory below. Continue an inventory of name, exact version/revision, source URL, license, notices, use and reviewer for Next.js, React, Python, FastAPI, Pydantic, pandas, SQLAlchemy, Alembic, PostgreSQL, Docker, gVisor, Caddy, restic, scanners and any evaluation baseline. Review transitive dependencies and base images too. Include model/provider terms separately; an API model listing is not a license conclusion.

All demo/evaluation data must be labeled synthetic or have recorded permission/license. Track seed/provenance and generator author. Keep held-out oracles private until evaluation is finished. Third-party prior-art citations do not imply reproduced results, endorsement, or permission to reuse their assets.

## Python foundation inventory — 2026-11-04

Source: installed wheel metadata, reviewed by Codex; no independent human review. Versions and wheel hashes are fixed in uv.lock. Metadata license labels are recorded as supplied; they are not a legal clearance or a license grant for ProofFlow. Retain upstream license files. Development-only audit dependencies (including certifi/MPL) are not in the runtime export. No third-party dataset is added.

| Distribution | Version | Metadata license | Use |
| --- | --- | --- | --- |
| [annotated-doc](https://pypi.org/project/annotated-doc/0.0.5/) | 0.0.5 | MIT | Runtime |
| [annotated-types](https://pypi.org/project/annotated-types/0.8.0/) | 0.8.0 | MIT | Runtime |
| [anyio](https://pypi.org/project/anyio/4.16.0/) | 4.16.0 | MIT | Runtime |
| [boolean.py](https://pypi.org/project/boolean.py/5.0/) | 5.0 | BSD-2-Clause | Development check |
| [CacheControl](https://pypi.org/project/CacheControl/0.14.4/) | 0.14.4 | Apache-2.0 | Development check |
| [certifi](https://pypi.org/project/certifi/2026.10.23/) | 2026.10.23 | Mozilla Public License 2.0 (MPL 2.0) | Development check |
| [charset-normalizer](https://pypi.org/project/charset-normalizer/3.5.2/) | 3.5.2 | MIT | Development check |
| [click](https://pypi.org/project/click/8.5.0/) | 8.5.0 | BSD-3-Clause | Runtime |
| [colorama](https://pypi.org/project/colorama/0.4.6/) | 0.4.6 | BSD License | Development check |
| [cyclonedx-python-lib](https://pypi.org/project/cyclonedx-python-lib/11.12.0/) | 11.12.0 | Apache Software License | Development check |
| [defusedxml](https://pypi.org/project/defusedxml/0.7.1/) | 0.7.1 | Python Software Foundation License | Development check |
| [fastapi](https://pypi.org/project/fastapi/0.162.0/) | 0.162.0 | MIT | Runtime |
| [filelock](https://pypi.org/project/filelock/4.2.7/) | 4.2.7 | MIT | Development check |
| [h11](https://pypi.org/project/h11/0.16.0/) | 0.16.0 | MIT License | Runtime |
| [httpcore](https://pypi.org/project/httpcore/1.0.9/) | 1.0.9 | BSD-3-Clause | Development check |
| [httpx](https://pypi.org/project/httpx/0.28.1/) | 0.28.1 | BSD License | Development check |
| [idna](https://pypi.org/project/idna/3.20/) | 3.20 | BSD-3-Clause | Runtime |
| [iniconfig](https://pypi.org/project/iniconfig/2.3.1/) | 2.3.1 | MIT | Development check |
| [license-expression](https://pypi.org/project/license-expression/30.4.4/) | 30.4.4 | Apache-2.0 | Development check |
| [markdown-it-py](https://pypi.org/project/markdown-it-py/4.2.0/) | 4.2.0 | MIT License | Development check |
| [mdurl](https://pypi.org/project/mdurl/0.1.2/) | 0.1.2 | MIT License | Development check |
| [msgpack](https://pypi.org/project/msgpack/1.2.4/) | 1.2.4 | Apache-2.0 | Development check |
| [opentelemetry-api](https://pypi.org/project/opentelemetry-api/1.45.2/) | 1.45.2 | Apache-2.0 | Runtime |
| [packageurl-python](https://pypi.org/project/packageurl-python/0.17.6/) | 0.17.6 | MIT License | Development check |
| [packaging](https://pypi.org/project/packaging/26.3/) | 26.3 | Apache-2.0 OR BSD-2-Clause | Development check |
| [pip](https://pypi.org/project/pip/26.3/) | 26.3 | MIT | Development check |
| [pip-requirements-parser](https://pypi.org/project/pip-requirements-parser/32.0.1/) | 32.0.1 | MIT | Development check |
| [pip_api](https://pypi.org/project/pip_api/0.0.35/) | 0.0.35 | Apache Software License | Development check |
| [pip_audit](https://pypi.org/project/pip_audit/2.10.1/) | 2.10.1 | Apache Software License | Development check |
| [platformdirs](https://pypi.org/project/platformdirs/4.14.3/) | 4.14.3 | MIT | Development check |
| [pluggy](https://pypi.org/project/pluggy/1.7.0/) | 1.7.0 | MIT License | Development check |
| [py-serializable](https://pypi.org/project/py-serializable/2.1.0/) | 2.1.0 | Apache Software License | Development check |
| [pydantic](https://pypi.org/project/pydantic/2.14.2/) | 2.14.2 | MIT | Runtime |
| [pydantic_core](https://pypi.org/project/pydantic_core/2.50.2/) | 2.50.2 | MIT | Runtime |
| [Pygments](https://pypi.org/project/Pygments/2.21.0/) | 2.21.0 | BSD-2-Clause | Development check |
| [pyparsing](https://pypi.org/project/pyparsing/3.3.3/) | 3.3.3 | MIT | Development check |
| [pytest](https://pypi.org/project/pytest/9.2.0/) | 9.2.0 | MIT | Development check |
| [requests](https://pypi.org/project/requests/2.34.2/) | 2.34.2 | Apache Software License | Development check |
| [rich](https://pypi.org/project/rich/15.0.0/) | 15.0.0 | MIT License | Development check |
| [ruff](https://pypi.org/project/ruff/0.17.3/) | 0.17.3 | MIT | Development check |
| [sortedcontainers](https://pypi.org/project/sortedcontainers/2.4.0/) | 2.4.0 | Apache Software License | Development check |
| [starlette](https://pypi.org/project/starlette/1.10.0/) | 1.10.0 | BSD-3-Clause | Runtime |
| [tomli](https://pypi.org/project/tomli/2.5.0/) | 2.5.0 | MIT | Development check |
| [tomli_w](https://pypi.org/project/tomli_w/1.2.0/) | 1.2.0 | MIT License | Development check |
| [typing-inspection](https://pypi.org/project/typing-inspection/0.4.4/) | 0.4.4 | MIT | Runtime |
| [typing_extensions](https://pypi.org/project/typing_extensions/4.16.0/) | 4.16.0 | PSF-2.0 | Runtime |
| [urllib3](https://pypi.org/project/urllib3/2.8.0/) | 2.8.0 | MIT | Development check |
| [uvicorn](https://pypi.org/project/uvicorn/0.54.0/) | 0.54.0 | BSD-3-Clause | Runtime |

Control base: Docker Official Python 3.12.16 slim trixie, Linux amd64, manifest SHA-256 `1148dbb014615300fa7e713b2f94f550c0d1c69780c0805f84f093ceee34dd0b`. Source Dockerfile revision `3d7e95597e56a415d9e4abc0f15877e005d2cb2e` from the official image manifest. Python is PSF-licensed; Debian contains multiple separately licensed components whose packaged notices must be retained. Trivy 0.76.1 (Apache-2.0, official aquasecurity/trivy release, verified SHA-256) scanned OS and Python packages locally. [Image/package receipt](docs/evidence/control-image-scan-2026-11-04.json) preserves remaining findings and metadata licenses; full release attribution and reachability review remain open. Build uses hashed pip 26.3 then removes pip from runtime. The Python audit alone does not cover OS advisories. No model license/terms or runtime eligibility is inferred.

Local budget fixture: Docker Official PostgreSQL 18.6 trixie linux/amd64 manifest `sha256:f4b419e350fd98d4a8429603295208976dea4c8fb8326d818d346d3e29f1db6f`, official source revision `e00e1bd34ec5c8a8e7ad89b273b3d42efaf6d5bc`. PostgreSQL uses the [PostgreSQL License](https://www.postgresql.org/about/licence/); retain its upstream copyright and license text. Image includes separately licensed Debian and gosu components whose notices remain in the upstream image; complete release attribution remains open. This is a trusted local disposable test fixture, not a released image or approved deployment base. [Budget scan receipt](docs/evidence/phase1-budget-postgres-2026-11-04.json) retains critical and other advisories. No Python database driver or additional Python dependency was added. Reviewer: Codex, no independent human sign-off.

Optional inference client / development integration additions (Nov 4): Psycopg and psycopg-binary 3.3.7 metadata LGPL-3.0-only; Windows tzdata 2026.6 Apache-2.0. HTTPX 0.28.1 BSD-3-Clause and its certifi 2026.10.23 MPL-2.0 now also belong to the optional inference runtime; the base health export still excludes them. Exact wheels/hashes in uv.lock and inference-check-requirements.txt. Retain upstream notices and assess LGPL relinking/source and MPL source obligations before redistributing a public deployment image. The binary driver bundles native libraries requiring separate inventory/release review; Python audit zero is not native-library clearance. Trusted local test image only, not publicly distributed. Reviewed by Codex, no independent human sign-off.

Worker-only pinned inventory (Nov 4): pandas 3.1.0 BSD-3-Clause; NumPy 2.5.4 metadata BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; python-dateutil 2.9.0.post0 BSD-3-Clause/Apache-2.0; six 1.17.0 MIT. The separate worker lock also resolves Windows/emscripten tzdata 2026.6, not installed in the Linux image. Preserve packaged notices including numerical-library/native wheel components; complete bundled-native attribution and security review remains open. Exact hashes are in worker/environment/uv.lock and worker-requirements.txt. No third-party application source copied or candidate data included. Reviewer Codex; no independent human approval.

Worker import/TLS local tooling (Nov 4): existing Ubuntu squashfs-tools `1:4.6.1-1build1` (mksquashfs, GPL-2.0-or-later) and OpenSSL `3.0.13-0ubuntu3.15` (Apache-2.0) used for trusted image conversion and ephemeral test certificates. Python's ssl/socket/tarfile modules are standard library, not new PyPI dependencies. Tools are not copied into source or the candidate image; retain packaged notices if later redistributed. The generated filesystem retains the upstream image's package notices. Builder binary hash is recorded in the import receipt. Host/native security review remains required before deployment; package version recording is not vulnerability clearance. No project license/ownership clearance is inferred.

Database hardening (Nov 4): active trusted fixture now derives from Docker Official PostgreSQL 18.6 Alpine 3.24, upstream revision `e00e1bd34ec5c8a8e7ad89b273b3d42efaf6d5bc`, base digest `10a5c69a83035ab5239f5620d708520e8b28f5aa1f2b20143e6024532edadfb5`. Stable Alpine signed packages pin brotli-libs 1.2.1-r0 (MIT) and libcurl 8.23.0-r0 (curl license); other Alpine packages retain separate obligations and upstream notices. gosu is removed from the final filesystem. Retain PostgreSQL/upstream licenses and complete image redistribution attribution before release; removing a binary is not a waiver for distributing underlying layers. No Python dependency change. Exact build/scan identities in the database/provider receipt. Codex review is not independent human sign-off.

gVisor preflight (Nov 4): official release-20261102.0 x86_64 archive and eight member pins in infra/gvisor/runsc-release.json. Binaries remain ignored local artifacts. Upstream [selected-release license](https://raw.githubusercontent.com/google/gvisor/release-20261102.0/LICENSE) is Apache-2.0; retain upstream notices and bundled-component obligations on installation/redistribution. Only trusted version/flag inspection; no install or guest execution. Trivy package inventory unavailable. Project MIT ownership clearance remains open.
