# Decision log

## D104: verify actual scheduled operation and preserve release provenance

Observe the existing scheduler's natural twelve-hour-due capture rather than forcing
another capture to refresh a date. Rehearse the newly authenticated snapshot off-VM;
a zero-workspace snapshot after retention is valid but not a fresh nonempty-data claim.
Exercise the normal renewal service under the exact reviewed unit/closed admission,
without force-renewal. Actual ExecStartPost success supplements the prior direct hook
check; future CA issuance and post-event hosting remain unverified.

Read only the existing support ticket through documented GET endpoints. Retain raw
messages privately; commit only routing status/date, content digest and decision gap.
Do not send, rate, close, or attach anything. A forwarding response is not clearance.

Package v5 uses verified source65b6b8e, unchanged media and original recording provenance.
Compare SOURCE.zip byte-for-byte to Git archive and the bundled hook to deployed hash;
verify outer ZIP against its separately recorded digest. Preserve all previous bundles.
This is private review material, not publication or proof of all Phase6 gates. Scoped
checks/Codex review are not independent human approval; offline custody remains deferred.

## D103: recover interrupted TLS deployment without guessing or forcing issuance

Keep the existing exact IP, chain, validity and key validation. Before service changes,
validate both existing files and all staged files without short-circuiting. Serialize
with a root-owned no-follow lock. A fsynced root-owned marker binds the intended pair
by hash; exact private staged bytes roll forward only to that same target. Stop the
guest API before replacement; verify both bytes, start and verify active, then clear
the marker. Retain it on uncertainty. Unknown partial or conflicting files stop rather
than being deleted or interpreted as an old certificate to roll back automatically.
Normal same-certificate/no-marker operation remains a no-op.

Certbot deploy hooks only follow actual renewals and hook errors are not sufficient to
establish its exit status ([official guide](https://eff-certbot.readthedocs.io/en/stable/using.html#renewing-certificates)).
Add the fixed hook as ExecStartPost under the existing service resource/deadline bounds.
This provides a same-lineage check and retry on subsequent scheduled no-renewal runs.
It does not force renewal, bypass CA validation or promise future successful issuance.

The targeted installer requires exact old unit digest, pinned host, valid credit window
and closed/idle product before changing only the reviewed hook/unit. Preserve prior
revision/unit and exercise actual same-certificate no-op and external health readback.
New source is hash-named, no new privilege/dependency or provider key. Operations flags
renewal failure and leftover rotation state even if an old public certificate still
works. Separate review includes real local process death, file safety/lock conflicts,
start failures, no-op behavior and scope-denial tests; no independent human sign-off.

## D102: reconcile backup/funding uncertainty without replaying authority

Use the same bounded latest-receipt reader for export, saved SQL recovery and operations.
An interrupted replacement is a stop, never permission to erase the pending file or
fall back silently. Re-read the pointer after slow work and re-read the vault after SQL
rehearsal. Scheduler timestamp claims must bind to authenticated contents even when no
new capture is due. These are checkpoint checks, not a claim of atomic custody across
all concurrent operations. Key expiry and current deletion-authority checks remain.

Funding inspection is separate from apply and does not instantiate LiveSession or run
the destructive credit guard. Use a pinned machine and repeatable-read read-only SQL
snapshot. Preserve PostgreSQL ledger bytes for unresolved-intent binding. Distinguish
not-applied, remote-applied/local-pending, local-applied/receipt-pending and exact completed
state. Any partial result is nonzero and never edits state or retries the original
update. Completed inspection permits later legitimate ledger usage after the review,
while checking current reservation caps; unresolved inspection demands the original
ledger hash and closed inference. A latched/expired stop stays closed.

Separate critical pass reviewed pre-access pending denial, receipt/key swaps during
waits, unchanged caps, incomplete/completed record mismatch, readonly SQL, secret error
redaction and preservation of the stricter deadline. Actual receipt/state readback and
isolated saved-database replay pass. Crash-stage cases are labeled automated doubles,
not induced production faults or independent human approval. No dependency, privilege,
product approval/verifier change, cloud provisioning or offline password setup.

## D101: observe live operations without granting release or spending authority

Provide a one-shot owner command using existing credentials and pinned SSH hosts.
Only fixed HTTPS GET, account GET, budget SELECT, systemctl and statvfs observations;
never call the destructive credit guard, create work, extend funding or export keys.
Authenticate the saved backup through the existing profile vault (its local freshness
floor may advance). Bound and redact public response/error text. Check actual Docker
and worker storage paths, exact budget caps and deadline, task freshness and certificate
expiry. Nonzero means a fixed actionable failure code, not permission to repair blindly.
Conservative credit floor $150 is a review threshold, not an invoice or provider stop.

SCOPED_OK always retains phase6_complete=false. Public liveness and the deliberately
unready product endpoint have separate meanings; test unexpected200 and wrong-app
responses. This is not a background monitor, end-to-end workflow or RPO/RTO promise.
Separate critical pass reviewed side effects, secret output, deadline/cap binding,
false readiness and failed-probe continuation. Twenty regression cases and actual
readback pass; no new dependency/privilege/security policy, independent human sign-off
or publication. Preserve existing private release artifacts as dated evidence.

## D100: actual scheduled SQL quarantine with an independently tested process deadline

Authenticate the existing scheduled backup and receipt under CurrentUser DPAPI; send
only trusted SQL/snapshot/current-authority bytes over stdin to a local pinned PostgreSQL
rehearsal. Never put a key, password or SQL in argv, logs or a persistent data volume.
No cloud mutation or production SQL import. Use no network/ports, UID70, dropped caps,
read-only root,512MiB no-swap memory,1CPU,128PIDs and bounded tmpfs. Clone connection
limit0 denies normal login before stripping all24 authority tables. Recheck live deletion
authority after local cleanup; a stale or lost authority cannot be reconstructed from backup.

Actual failure showed BusyBox timeout as PID1 was insufficient. Use the existing Docker
init (Tini0.19.0, hash in receipt) to separate namespace init from the timed PostgreSQL
process. No new package/privilege/network installation. [Official Docker documentation](https://docs.docker.com/reference/cli/docker/container/run)
describes init/signal behavior; actual90s kill/AutoRemove is separately measured. Observer
must see exit137 and disappearance without cleanup, not any nonzero exit or a forced
cleanup. Fresh trusted container reconstruction is not compromised-host recovery. Failed
readbacks and the first watchdog failure remain disclosed. Separate critical review is
not independent human sign-off; no contract/verifier/product approval policy changed.

## D99: prepare judging hosting without changing operational authority

Use a fixed read-only account/instance/inference/ledger preview. Check exact project and
instance identities, no backup/DDoS add-ons, approved plan prices, unchanged caps and
conservative reservation totals; do not refund reservations using an hourly estimate.
Vultr's672-hour billing basis gives approximate7/14-day compute costs. Preserve current
48-hour funded-review discipline and final teardown; account credit does not settle
post-event access terms. A powered-off VM still bills; do not confuse shutdown with
teardown. No new services, personal payment, invitation or admission change.

Recovery denial drill uses inert synthetic data and the existing pinned networkless,
nonroot, read-only container with512MiB memory and64MiB tmpfs. Require exact failure codes and no returned data,
with successful controls and cleanup; arbitrary infrastructure errors cannot count as
security denials. Same-source local recovery does not establish a reimaged trusted host
or replace lost current deletion authority. Separate critical review and automated checks
are not independent human sign-off. No runtime, verifier, contract or privilege change.

## D98: bind offline export and release receipts to their authenticated content

Owner export must match scheduled digest/capture/expiry to the authenticated backup,
re-read the vault after interactive password entry, and recheck expiry after encryption.
Receipt substitution cannot mislabel custody, and a key retired during the prompt cannot
be exported from a cached key. Current-profile authentication is not lost-profile recovery.
Package v2 uses exact Git document bytes, checks documents and media against bundled
source/pins and permits a separately trusted ZIP hash. Internal manifest consistency alone
is not authenticity; the external checkpoint hash remains the trust anchor. Historical v1
archives remain verifiable, including their Windows newline convention. No archive code
executes; no new dependency, runtime privilege, restore promotion or public release.
Separate Codex critical review and scoped tests do not supply independent human sign-off.

## D97: prove visible browser startup before opening guest authority

Use the installed Microsoft Edge Playwright channel on Windows, in a fresh ephemeral
profile. Actual visible launch and guest intake were tested after the bundled Chromium
executable was missing and its downloaded replacement failed native assembly activation.
Do not treat headless-shell acceptance as visible-browser installation proof. Launch the
visible browser before reading access credentials or invoking remote guest preparation;
close it if setup fails. Preserve public system TLS trust and exact approvals. No app
runtime dependency, browser profile reuse or OS security relaxation. Non-Windows retains
the explicit bundled-Chromium existence check. No independent human review claimed.

## D96: individual expiring guest windows and desktop-independent closure

The owner explicitly authorized guest access and bounded live demo operation on Nov8.
Use one individually provisioned guest workspace/session per30-minute window. No public
signup, shared judge credential, URL token, operator session or automatic contract/version
approval. The owner launcher uses existing CurrentUser DPAPI and owner/SYSTEM-only ACL
helpers; a dedicated ephemeral Chromium context signs in and stages labeled synthetic
files locally. Actual submission/contract/version decisions remain in the product UI.

No schema/runtime/limits/provider changes. Fresh official catalogue and VM charges plus
credit cutoff must pass before opening. Existing$150/$25 account reservations, cumulative
repair allocation, three-call/$0.50 repair bounds and isolated-worker policy stay intact.
A root-owned systemd guard on control checks every10s, independently of the desktop.
Persist intent before admissions; expire on deadline, boot change, backwards clock or
invalid state. Block inference then close execution through configure_execution; never
edit job outcomes. If DB closure fails, stop dispatcher. Guest workspace/session expiry
and fixed quote expiry provide additional request/dispatch enforcement; no automatic
window extension. Admin commands and Docker access are fixed trusted operations with
no guest-selected paths, SQL, credentials or cloud-management keys on the host.

Review: this adds a root administrative guard, not public privilege. Use single host lock,
protected files, fixed arguments, source-hashed installation and live expiry readback.
Initial credential validation mistakenly assumed URL-safe tokens; use existing prefixed
session/CSRF validators rather than duplicating their format. Failed setup kept admissions
closed and its expired workspace goes through normal retention; no paid call was made.
Final review added dispatcher Requires+After dependency on the one-shot guard so boot
identity is checked before dispatch can resume. Actual idle dispatcher restart and host
unit verification passed; guard completion timestamp preceded dispatcher start. Full
host reboot not repeated. [Official dependency semantics](https://www.freedesktop.org/software/systemd/man/latest/systemd.unit.html)
support the ordering/requirement combination. The periodic guard remains separate from
the desktop and preserves the current valid window on an ordinary dispatcher restart.

Independent human review is still unavailable; automated/Codex review is not human approval.

## D95: preserve bounded public admission and separate renewal scheduling

Actual staging and public firewall probes initially timed out, then passed after
external connectivity was established. Preserve failed receipts; no blind replay.
The first browser revocation test encountered the connection cap; close old pooled
test transports before independent readback, never increase admission limits to pass.
Four fresh contexts and a separate real restart/revocation test then passed. Use
normal time-bound authority IDs in test provisioning; UUID4 is rejected by current SQL.

Certbot renewal adds its own random sleep. Use systemd's existing300s jitter and
`--no-random-sleep-on-renew`, preserving240s service bounds. Actual staging renewal,
production hook trust/no-op and scheduled service passed; future production rotation
is not yet observed. Keep existing private transport and keys isolated from public TLS.

## D94: explicit public TLS activation with a separate guest-only API

The November8 owner request explicitly authorizes public TLS activation and external
guest testing, while retaining private Git and promotional-credit caps. Use the existing
control IPv4 and free short-lived IP certificates; no domain purchase or new VM. Keep
operator SSH443/private API intact. A separate networkless API container has the same
limited database/assets policy, a separate Unix socket/TLS mount, and guest-only session
admission. Operator tokens must fail on this surface. Public relay binds only the VM's
public IP:8443 because an existing loopback health service occupies127.0.0.1:8443.

Certificate infrastructure uses a separate root-only Certbot5.9.0 environment, hash-
locked18-package dependency set; the initial audit reports no known Python advisories.
It is not added to application/worker images. ACME standalone challenge exposes port80
only while the client runs; that port does not serve project files. Test staging first,
then validate production chain/IP/key/expiry before activation. ACME account keys stay root-only; the TLS key is readable only by the isolated API UID
on its protected read-only mount. Keys never enter Git, prompts or browser profiles. Scheduled renewal must copy verified certificate pairs
and restart only the public API. No certificate validation bypass in external tests.

Preserve firewall SSH rules, worker isolation, exact approvals, session expiry, quotas
and budget gates. Public access is invited guests, not anonymous signup or a shared
judge credential. Tests use separate bounded synthetic guests and clean browsers with
system trust. No new product PR, repository publication, license or event submission is
authorized by this TLS work. Separate Codex critical review is not human sign-off.

## D93: prepare one HTTPS origin and recheck recovery expiry at completion

The owner requests remaining public-demo preparation/recovery work while retaining
private Git and credit-only limits. Add one canonical configured HTTPS authority,
checked before routing, body parsing or database access. Reject duplicate/wrong Host,
plaintext transport and caller Forwarded/X-Forwarded headers. Preserve strict Origin,
CSRF, session, workspace and exact approval checks. This is not anonymous signup.
An optional bounded owner-only file in the existing read-only TLS mount may configure
the future public origin; absence preserves the private tunnel. No new mount, package,
network namespace, credential privilege or default public listener is introduced.

Separate Codex critical pass reviewed startup failure, symlink/hardlink/mode/size,
canonical IPv4/IPv6/DNS/port, proxy spoofing before routing and denial headers. Linux
and ASGI adversarial tests pass. One old event fixture lacked Host; add the valid
header rather than weakening the new policy. References checked Nov8: official
[Uvicorn settings](https://uvicorn.dev/settings/) and
[Starlette middleware](https://starlette.dev/middleware/). Unlike a terminating proxy
that supplies scheme headers, the proposed edge transports TLS to the existing API;
proxy-header trust remains disabled.

Recovery previously checked expiry using only the start timestamp. Materialization
now charges monotonic elapsed time and rechecks backup, workspace and authority
expiry before success. Failure still requires isolated caller cleanup; fresh live
deletion-authority readback remains mandatory. No stale authority or lost-host restore
exception is added. Four Linux expiry/clock faults and a real separate-instance
encrypted restore pass. This does not establish compromised-host recovery or owner
offline custody. Codex/automated review is not independent human sign-off.

Rebuild uses unchanged locked base/dependencies. The first network-disabled build
could not use the network-mode-specific apt cache; normal trusted build reused all
dependency layers successfully. New image passes exact 73-file/source/mode inventory.
Private deployment must retain closed/idle admissions, preserve the predecessor,
pass container policy/readback and update evidence before claiming deployed behavior.

## D92: private release assets with verifiable source and truthful gate status

Use local editable PPTX and a standalone cover for the repository's private release
package. Bundled Artifact Tool renders/exports the deck; no presentation SaaS publication
or new application dependency. Text uses the actual product palette; the one screenshot
is hash-checked against its synthetic run. Source notes and native tables preserve
evidence/limitations. The finalizer checks structure,fonts,geometry and re-import; visual
review covers every slide. These checks are not native PowerPoint or public-form tests.

Pin reviewed media before assembling an explicit allowlist of package files. Archive
only clean committed tracked source with Git; do not sweep the workspace/private
deployment directory. Bound ZIP/XML parsing,deny unsafe/duplicate names,secret filenames,
symlinks,external PPTX relationships/macros and DTD/entities. SHA-256 proves consistency,
not independent live-provider authenticity. An outer ZIP manifest binds file lengths,
hashes and source commit; the later checkpoint records that ZIP hash without pretending
the archive can contain its own future receipt commit.

The public form is not verified,so draft fields retain null public URLs and false release/
license flags. Offline key custody is OWNER_DEFERRED. Current public/private scope and
full disaster gaps stay visible; ordinary preparation continues. No new runtime privilege,
model campaign,external write or spending. Separate Codex claim/privacy review is not
independent human sign-off. Eight negative gate probes supplement actual export and
offline benchmark accounting; application tests need no repeat for document-only work.

The offline packager has 13 durable guard tests. Windows ZipInfo normalizes separators
on read; require the original name to equal the parsed name before validating paths.
The raw archive mutation test verifies that boundary. Runtime security policy is unchanged.

## D91: scheduled local custody, portable synthetic transport and honest recorded evidence

Use the existing private desktop as the off-VM backup destination without another paid
service. A limited interactive-user Windows task checks hourly, captures every12h or2h
before expiry and preserves closed/idle gates. It retries busy/failing runs and fails
on pending uncertain receipts. Capture uses the D90 exported MVCC snapshot and fixed
nonroot network-denied API asset reader; reads are inert, bounded and hash checked.
Repeated blob registrations use the earliest creation time so deduplication cannot
extend raw-data lifetime. Even a not-due result authenticates the vault key/envelope;
a timestamp is not proof of a recoverable backup. Desktop sleep/logout remains a gap.

Add offline password transport using existing cryptography50.0.2: scrypt n=2^17,r=8,p=1,
random16-byte salt and AES-256-GCM key wrapping bound to the envelope hash. Fixed parser
bounds; no key/password persistence, argv or chat. A24–256-byte UTF-8 password is entered
twice only in a local interactive terminal. Existing snapshot/raw expiry is preserved.
Current authenticated deletion authority is still required and must be <=60s old.
The transport is not a backup-derived proof of non-deletion. Exported copies cannot
be remotely crypto-erased; keep this synthetic owner-custody feature out of claims
about enforced guest-data retention. Actual Windows-to-Linux drill passed with an
ephemeral test password, not owner custody. No product endpoint/image/schema change.

The real AI demo uses the official fresh provider quote and existing budget admission
caps. No fixture patch substitutes for the model. Preserve the failed recording harness
receipts and reconcile read-only worker records rather than spending again to obtain
cleaner evidence. Missing output after a killed loop is FAILED_INFRA/report=null; the
trusted worker_receipt proves cleanup, not a fabricated public verification report.
Close browser contexts before browser shutdown on exceptions. Media may add labeled
holds/cuts and actual receipt summaries, never false live states or human approval.

Local signed Ubuntu FFmpeg6.1.1-3ubuntu5 was installed only for trusted own-video editing;
not in the application,worker,verifier or cloud. No new Python/runtime dependency.
Separate Codex critical review covered salt/nonce/KDF bounds, stale authority, expiry,
secret-free capture, old-receipt replay, failed task reporting and funding pins. Fixed
findings and21 new unique fault/policy cases are not independent human sign-off.
Funding uses current accepted runtime pins independently of the frozen benchmark and
date-specific exclusive intents; no cap increase, reservation release or old renewal replay.

## D90: consistent capture and private rehearsal without overstating recovery

Use PostgreSQL exported read-only REPEATABLE READ snapshots for inventory,registry and
pg_dump instead of relying on a future scheduler to quiesce every writer. Freeze the
expiry observation inside the snapshot; keep the exporter alive until dump success.
Fixed trusted Docker targets,Unix sockets,no shell,read-time byte caps,shared50s
deadline,55s container-owned kill and server timeouts bound capture. Caller failure
rolls back; an ended snapshot cannot silently fall back to a new one. The new helper
adds no dependency,privilege,network endpoint or product policy. A separate critical
pass identified and fixed the missing independent process lifetime bound.12 new fault
tests and actual PostgreSQL integration support it; no independent human sign-off.

Do not call same-profile DPAPI a portable recovery key,or an old backup inventory fresh
deletion authority. Live empty-product capture proves actual vault transport; separate
nonempty concurrent-data recovery proves quarantine behavior on another DB instance.
Neither proves fresh-host compromise recovery,scheduling or public readiness. The live
capture preceded final55s hardening; preserve that revision distinction and do not replay
its completed receipt merely to replace the evidence.

Browser scenarios use fresh seeded synthetic variants and disclose their template
origin. One first-match faulty source was explicitly constructed for the visible owner
witness after an earlier sample correctly rejected duplicate matches instead. Preserve
that failed harness expectation. A separate pooled-connection failure after logout is
not an authorization verdict; a new transport using the revoked token passed403 in the
amended run. Full final comparison remains frozen. The correct-source version rehearsal
is not AI repair; exact approval is labeled automated synthetic testing,not human review.
No product GitHub action is needed for another recording. [Evidence](evidence/phase6-recovery-rehearsal-2026-11-07.json).

## D89: complete finite security acceptance without hiding coverage limits

Use static govulncheck binary analysis after the filesystem scanner recognized no Go
packages. Record source/tool hashes and actual build modules;retain warnings and all
finding levels. JSON exit0 is transport success,not safety. Three tiny helpers are
native ELF binaries,not scripts;review their parent FD/argument setup and disassembly
separately. Unknown main-module/platform/native coverage remains visible.

Patch the concrete Critical host TCP issue with exact signed noble-updates149 packages
on existing idle hosts. Require closed inference/product admission,empty jobs/workspaces,
no pending external write,exact package/origin plan,durable install/reboot intent and
new-kernel readback. Worker first;no removal,new service,proposed repository or automatic
vulnerable rollback. Retest all16 actual containment probes after reboot.

The existing Phase5 plan requires tested containment/auth/mutations,honest frozen
comparison/accounting and separate critical review. Those private technical gates now
pass;verified push completes the phase. Do not convert unresolved production/disaster/
license/public-release obligations into fake passes or endless unspecific Phase5 work.
Keep composite traceability partial and disclose the deterministic baseline advantage.
No independent human approval exists. [acceptance evidence](evidence/phase5-binary-acceptance-2026-11-07.json).

## D88: rebuild from exact policy, preserve durable authority

Existing container identity must include immutable image AND exact command/environment,
mount destinations/sources/RW/propagation,nonroot identity/groups,no privileges/added
caps,NNP,CPU/RAM/no-swap/PID/ulimit bounds and private namespaces. Do not accept a
matching image with changed host authority.28 concrete drift cases and real readback
support the expanded installer gate;no candidate/verifier/approval rule changes.

The incident drill reconstructs only the API container from an authenticated pinned
installer,after fresh credit/closed/idle checks. Flush and atomically publish stages;
stop/archive predecessor,never erase or silently roll back it. Compare durable
authority,source bytes and revoked-token denial before cleanup. Actual new container
and readback pass. This is not fresh-host recovery or secret rotation;those require
separate trustworthy credentials/deletion authority. No new resources or public action.
Source findings and zero detected binary packages are not binary security clearance.
Separate critical pass is Codex/automated,not human sign-off. [Evidence](evidence/phase5-runtime-incident-2026-11-07.json).

## D87: capacity belongs to real executor work, not its HTTP waiter

Background filesystem/ZIP work is not stopped by cancelling an asyncio waiter.
Shield the executor future and retain it until completion; release the process-local
4-slot asset IO /1-slot bundle budget only from its completion callback. Discard
orphan results/errors and preserve response deadlines,post-read authorization and
uncertain upload reservations. A blocked thread keeps its slot; supervised restart
is the recovery boundary, not an unsafe retry or forced thread termination.

Seven real-thread/local ASGI-double cases plus actual deployed auth/inert-byte smoke
support the change. The trusted smoke helper now permits explicitly shorter1–40min
sessions; actual workspace lifetime remains enforced by SQL. Its initial40min/20min
failure and incorrect202 cleanup assertion are preserved/reconciled, not relabeled
success. No permission,dependency,schema,verifier,contract,provider or budget expansion.
Separate critical review is Codex/automated evidence, not independent human approval.
[Receipt](evidence/phase5-http-cancellation-2026-11-07.json).

## D86: serialize backup authority and retain native findings honestly

Decrypted recovery assets now live only in private container tmpfs, not ordinary host
temporary directories. Use the existing pinned image with trusted source-only read-only
mount,closed network,nonroot/no capabilities,no cgroup swap,fixed memory/process limits
and an independent20-second container-owned timeout. Never import candidate data.
Actual forced termination after materialization proves cleanup without Python finally.
Completed live helpers use this runner on future authorized work but are not replayed.
No new dependency/cloud resource or deployment privilege; local Docker was already in
use for trusted tests. Host paging/snapshots are outside the erasure claim.

Every vault operation takes the same nonblocking Windows byte-range lock, released
by the OS after process death. Write new private ACL files with CreateNew/Flush(true),
then atomically rename; no key is recoverable from a partially written file. Under
that lock, remove interrupted unpublished files/orphan keys and ciphertext; never
guess a corrupt key's expiry. Continue other authenticated expiry and return a fixed
reconciliation failure. Keep a private atomic clock floor before authorization and
check expiry again after crypto/file IO. Missing/corrupt floor with backups fails
closed. This is not rollback-resistant against a trusted administrator restoring the
entire private directory; that operation remains unsupported.

The existing .proofflow ancestor is Administrators-owned. Allow current user/SYSTEM/
Administrators only at that ancestor, rejecting reparse points; retain stricter
current-user-owned/current-user+SYSTEM-only deployment and key files. No actual ACL
or ownership change. This matches the documented trusted administrator boundary.
Actual process-death testing collects stdout after termination on Windows; the initial
harness failure is preserved separately. No candidate/native exploit was executed.

The refreshed scanner rates the same186 package/advisory pairs differently;49 HIGH
does not mean three newly introduced packages. Preserve findings, actual library hashes
and official Trixie/Noble status; unavailable stable fixes are not permission to silently
mix unstable distribution packages. FTS/session support exists, but the inspected
journal has no virtual tables and application code accepts no SQL/database/changeset
input. Scoped evidence is not vulnerability clearance or independent human approval.
[Evidence](evidence/phase5-vault-native-review-2026-11-07.json).

## D85: expire authority only after identity becomes permanently inadmissible

Unknown worker IDs must carry a fresh RFC9562 timestamp; unknown legacy UUID4 IDs fail
closed. Keep known executions for exact reconciliation and unfinished/quarantined work
indefinitely; retire only cleaned records and unused fences after seven days. Persist
a clock floor before pruning, retain one nonrenewable legacy grace, checkpoint SQLite
WAL and reject capacity overflow instead of evicting authority. Workspace creation
similarly requires fresh UUIDv7; completed deletion records can expire without permitting
old IDs to reappear. Migration019 binds expiry to the reviewed runtime, and020 changes
only signed-batch job identity generation. No contract/verifier/approval relaxation.
Do not restore old journals/clock floors or raw roots as a way to resume a service.

Use the already pinned cryptography AES-256-GCM for bounded DB+asset envelopes, a new
key per snapshot, separate current-user DPAPI key storage and private ACLs. Snapshot
lifetime<=24h; raw exposure<=48h; keys expire before ciphertext is removed. Recovery
requires fresh authenticated current authority twice and an isolated clone stripped
of all runtime authority; assets remain inert0400 files. A missing current allowlist
means no restore, even when an old backup contains a workspace. This is not automatic
production promotion or portable key recovery. The Windows watcher runs local key
expiry even if billing lookup fails; outages can delay physical deletion.

Actual off-VM recovery and normal fixture retirement passed after two disclosed
harness failures: bounded wait for observed DB clock lead, then a narrowly scoped
generated-clone connection helper preserving the general SQL allowlist. Existing
backup/job bytes were reused, not rerun. Separate critical review is Codex review,
not independent human approval. No new dependency/service/permission or model call.
[Evidence](evidence/phase5-encrypted-recovery-2026-11-07.json).

## D84: expire receipt details; restore only into inert data quarantine

Seven-day worker receipt expiry does not delete execution IDs, manifests or fences:
removing those would permit replay under the present UUID protocol. One legacy grace
period is persisted; recovery cannot renew it. Uncertain cleanup remains quarantined.
Physical SQLite/WAL cleanup failure closes admission. This narrows retained details
but does not complete minimal negative-authority metadata retention.

Deletion-safe recovery first has a deliberately limited, tested data-only lane.
Fresh current authority overrides a <=24-hour snapshot; missing/revoked/deleted or
changed-lifetime workspaces are excluded, and authority is read again after restore.
An isolated connection-limit-zero clone loses every session, approval, queued job,
PR intent and allocation; even retained workspaces are revoked. No automatic
promotion, credentials, lease resurrection, rollback of spend or external write.
This does not authorize pruning tombstones. Full encrypted DB+asset recovery and
disaster-available current deletion authority remain Phase5/6 gates. The existing
legacy backup helper keeps its guest/deletion rejection. No dependency or cloud
service added. Review is a separate Codex critical pass, not independent human approval.

## D83: renew only the funded existing-resource window

Standing credit-use/development authorization covers a fresh review of existing resources. Actual $192.92 credit, exact $24/$48 plans/owned resources, closed/idle services, unchanged $120 non-inference ledger reservations and $150/$25/$2 caps passed. The full $145 project allocation remains reserved; expiry alone advanced to November 8 23:27 KST after durable intent and conditional SQL/readback, then local guard readback. No new resource, payment method, cap increase, refund, status edit or reopened stop. The fixed November 23 final cutoff remains. Provider hard-stop/tax unknowns and conflicting post-event hosting guidance remain explicit. [Evidence](evidence/phase5-final-comparison-2026-11-06.json).

## D82: report actual finite outcomes, including the strongest deterministic baseline

The 96-job/79-response audit is complete. A/C both repaired 15/18; B accepted nine incorrect outcomes; D's fixed contract rebuild repaired 18/18. This supports measured acceptance-control behavior, not AI or witness superiority. Retain every failed run and disclosed polling amendment. Shared template/fault families, one repeat, absent human oracle review and unequal A/C orchestration prevent broader claims. Export allowlisted synthetic cases/records/metrics only; raw provider/protected evidence remains private. Future tuning is post-evaluation development and cannot overwrite this report. [Final report](../eval/final-comparison-2026-11-06.md).

## D81: preserve interrupted final run and disclose a transport-only amendment

The first A comparison poll returned BASELINE_RUNNING; the harness incorrectly treated any state outside QUEUED/RUNNING/RECONCILING as terminal. Its safety closure cancelled the original before repair. Actual readback confirms cleanup and no model call. Preserve that interrupted result in the denominator; do not rerun completed B/D/C or replace A's record. Correct only state polling, then prospectively bind a source amendment and continue the92 undispatched jobs with unchanged cases/order/model/prompts/runtime/grader/limits. This is disclosed transport maintenance after three observations, not unchanged-source or independently held-out evidence. Source/candidate tuning or outcome edits remain forbidden. Scoped continuation verifies exact prefix, closure and actual cancelled-workspace identity before normal retirement. No activation/PR/spend-cap change.


## D80: evaluate actual API workflow and preserve baseline decisions before grading

Use actual product intake/contract/original/repair/export for arm A, without exact-version activation or external actions. Capture raw private API/provider/execution evidence before ordinary synthetic workspace retirement. For B, authenticate/bind collected worker bytes and persist zero-exit acceptance in the existing after_capture hook before deterministic grading; failed/late grading remains unknown rather than retroactively removing an unsafe acceptance. C uses verdict-only feedback and fresh protected checks; D uses the fixed rebuild only on the worker. All arms preserve failed/missing/unknown observations. The A administrative/API overhead differs from C repair-core orchestration and must be disclosed in latency comparisons; this is not a pure end-to-end witness ablation. No final campaign/freeze yet and no human oracle/security review claim.


## D79: separate final B/C receipts from infrastructure probes

Use a finite private filesystem journal bound to the frozen manifest:48 B/C jobs,3 calls/$0.10 each,144 calls/$4.80 maximum, exact immutable payload/quote/response records, fsynced exclusive creation and descriptor-pinned locking. Global reserve/claim remains mandatory. Existing/unknown requests cannot send again. Do not increase or evict infrastructure probe receipts. A retains actual product API/queue storage; final combined72 model-job forecast remains$7.20. Final controllers/freeze/dispatch are not yet implemented; no paid result is implied. Fourteen local Linux tests and a separate Codex critical pass are not independent human approval.


## D78: distinguish code failure from infrastructure failure without inventing verification

A full-product evaluation must test the actual intake/queue path. A confirmed original code failure may request bounded repair only after independent source diagnosis finds zero blocking occurrences. Add a separate source operation and execution_failed outcome; semantic remains null until outputs actually exist and pass comparison. New017 migration preserves all previously applied bytes and admission/lease/revocation/idempotency/cap checks. Successful candidate plus fresh protected checks still precedes exact activation; no batch completion or PR authorization follows from a crash. Source ambiguity remains held. Retire raw failure previews before new controller history/reconciliation copies, keeping digest and authority evidence.

Draft24-case comparison generator is separate from canary generation but reuses disclosed fault families and positive template: prospective synthetic evidence, not independently authored held-out data. Do not freeze/run it until this product gap passes deployed acceptance. No final evaluation result exists. Development pilot remains labeled repair-core-only. Separate critical review is recorded in phase5-security-review.md; no human reviewer is confirmed.


## D77: retire raw worker previews without forgetting execution authority

Store an indexed nullable preview deadline in the durable worker journal. Existing rows lack a finish time, so grant a single300-second migration grace; future failure previews get the same TTL from finish. Replace only raw preview bytes with digest/retired marker. Keep IDs, job generations, manifests, fences, states, cancellation, cleanup and quarantine. Enable SQLite secure_delete and require WAL truncation; a busy checkpoint pauses admission, and recovery always retries truncation even if redaction already committed. Process at most32 expired rows per pass. Do not claim forensic snapshot/SSD erasure or a strict expiry SLA under outages/backlog.

Deploy only reviewed journal/supervisor changes after source/host/idle checks. Preserve old code/manifests without creating a raw DB backup. Verify new authenticated identity and update both exact controller config shapes. Invoke configure_execution with false admission so semantic-epoch invalidation clears old active versions; do not reuse approvals for changed runtime. Rebuild matching product image using unchanged cached dependencies, retain the installed expired provider settings with paid dispatch closed. Initial probe-config equality refusal was corrected only after verifying dispatcher's extra verifier field. First post-restart RPC delivery-unknown is preserved; bounded authenticated readiness precedes future checks. No independent human approval, new provider call/service or external PR write. [Evidence](evidence/phase5-worker-retention-2026-11-06.json).

## D76: bounded real pilot and safe retention correction

Run the declared4-case A/B/C development pilot through fixed Vultr provider and real worker/verifier components. A evaluates repair-core, B fixes exit-zero acceptance before final grading, C removes witness rows; same contracts/model/budgets/canaries, no end-to-end or held-out claims. Preserve all15 request/response receipts and failures; never rerun existing IDs. A private fsynced locked journal reserves before global claim/HTTP; unknown costs stay held. New016 adds a privileged exact-id/manifest allocation into unchanged$5 development cap using the same advisory lock as prepare_repair_call. It denies API/dispatcher access and never releases funds. The completed pilot's full$1.20 allowance was recorded afterward: original launch checked available allocation and closed product admission while local/global caps protected calls. Future driver records allowance before launch. Accounting estimates are not billing settlement.

New015 requests deletion for expired operators through the full existing revocation/worker-cleanup/uncertain-PR gate chain. The retirement union accepts at most32 IDs because unchanged limits allow16 originals plus16 repairs. Immutable unit upgrade only changes the hashed source path, preserves predecessor and refuses other policy changes. Retain completed deletion markers/metadata and worker execution/fence records until a coordinated lifecycle design prevents stale restore/re-execution. No manual expiry/status changes in production. No dependency, runtime/verifier/candidate policy, public exposure, external PR or human sign-off change. [Review](phase5-security-review.md), [Evidence](evidence/phase5-model-pilot-retention-2026-11-06.json).

## D68: bounded response completion and disclosed development evaluation (Phase5)

Apply an outer30s ordinary/65s event HTTP deadline across response transmission and overload replies. Cancellation releases request capacity without sending a second response or implying database rollback; scoped idempotency/status reconciliation remains authoritative. Regression uses blocked ASGI sends and actual deployed source/policy readback. Patch only inherited apt/libapt-pkg7.0 to Debian3.0.4 via signed HTTPS repositories with zero download retries; pin/review the resulting image. Other native findings remain risks; no runtime/worker/verifier/SQL/contract/approval changes. A stale exact predecessor pin initially refused deployment safely; reconcile live state before correcting it, preserve prior containers.

Evaluation accounting predeclares balanced cases/arms/artifact identities/forecasts, rejects duplicate or unbound records and preserves failures/missing/unknown grades/costs. It cannot authorize spending or prove receipt authenticity. Twelve disclosed canary-derived development cases and positive controls are validated on the designated worker, never locally executed. The failed JPY unit fixture remains evidence; fractional-USD revision was a development data correction before any model/final run, not a verifier change. Pilot adapters/durable caps/receipt reconciliation and independent final cases are still required. Source ambiguity holds are not a substitute for missing-business-policy clarification coverage. No independent human review exists. [Review](phase5-security-review.md), [actual evidence](evidence/phase5-security-development-2026-11-05.json).

## D74: existing-PR recovery-only acceptance under the owner's no-new-PR constraint

Do not reset a completed production intent, replay a GitHub create, extend an expired approval or request a duplicate PR merely to exercise a fault. The owner explicitly requests recovery without another PR. Use a separate no-network disposable PostgreSQL fixture with all unchanged product migrations. Initialize missing PR acknowledgement from retained confirmed action data, retaining synthetic fixture workspace/proof/actor and disabled GitHub dispatch authority. This initialization is a declared recovery scenario, never a production state edit or claimed original timeout.

Use the exact production controller/adapter source (hash compared with installed image) on the administrator computer, with a fixed functions-only psql bridge into the fixture. Candidate source is data only. Mint a repository-restricted read-only token; pre-network reject every mutation except exactly scoped read-only token issuance. Store adapter allows only claim/readback/defer. Lose one real PR-list GET reply before verification/DB acknowledgment. Restart the fixture database; require pending persistence and initial takeover denial, then wait for unchanged180-second lease naturally. Require higher generation, stale-controller/new-write rejection, exact existing PR readback, unchanged3 write-intent hashes, completed restart/no-op redelivery, cleanup and identical production snapshot before/after.

This changes the test method to respect the owner's constraint, not approval, isolation, verification, idempotency or fencing requirements. Original POST-create response loss is NOT_REPRODUCED and must never be claimed. Real initial PR creation is separately evidenced; this drill proves recovery of a missing-ack state against the existing real PR. No new dependencies/services, production credentials in fixture, candidate execution, SQL changes or independent human review. [Phase4 acceptance](evidence/phase4-acceptance-2026-11-05.json).

## D73: reconcile accepted approval before any retry; wrap immutable fault dependencies

A local harness failure is not proof that the external action failed. Inspect the exact durable intent and dedicated App readback before creating any replacement. This attempt already completed its3 authorized writes after production restart; preserve that PR and never reuse its approval for another intent. Complete exact readback/restart/idempotent replay using the original still-valid actor, then logout.

Fault injection must wrap the ProductStore/App interfaces rather than assigning methods on a frozen production object. Regression must use that real immutable type with explicitly fake I/O; a mutable mock is insufficient. Preserve returncode and diagnostic digests on future driver failures; never log native stderr or secret objects. No direct status/lease edits, production policy/dependency changes or human-signoff claims. Actual failed-injection gap remains explicit; ordinary completed PR readback does not prove lost-response recovery. [Evidence](evidence/phase4-real-pr-reconciled-2026-11-05.json).

## D72: explicit Windows session ownership and fresh expired-workspace replacement

Encrypted session creation must set current-user ownership and protected user/SYSTEM DACL at CreateNew, including elevated terminals. Do not accept Administrators ownership in the secret reader or overwrite existing sessions. Retain fixed stdin-only DPAPI, no plaintext argv/logs, fixed name validation and independent decrypt/ACL readback. Preparation checks at least41 minutes of valid operator workspace life before a40-minute session; fixed stage/error allowlists report failure without native exception text. Expired workspaces/approvals remain unchanged.

A new synthetic workspace may repeat normal API intake, exact synthetic contract/version activation and fresh isolated proof using retained identical source bytes, with inference blocked. This is automated fixture activation, never the human PR approval. Original queue waiting recognizes terminal states explicitly; unknown/running states cannot trigger false success. A cancelled attempt requires durable confirmed cleanup before a separately initiated new job; no status edits. Actual preview check logs out its actor and never submits approval. No deployed dependency/policy/SQL change or independent human review. [Evidence](evidence/phase4-local-approval-fix-2026-11-05.json).

## D71: human approval in one local session, with unchanged product rules

Repeated chat round trips exceeded the existing ten-minute preview lifetime. Do not weaken that policy or silently carry the answer onto another intent. Provide Approve-Phase4PR.ps1/approve_phase4_pr_locally.py: require interactive stdin before any preparation, generate a unique retained record/session, display exact inert preview text in fixed Notepad, require the full displayed digest and check expiry again after input. Blank/broad confirmation is not approval. Codex must not automate that human confirmation. No credentials in chat/argv or new account setup. Optional helper record paths stay in the private evidence directory; prior artifacts remain preserved.

Completion now validates the current preview before stopping any service, skips fault reinjection for already-approved state, bounds the trusted fault process to80 seconds inside/90 seconds outside and cleans only its labeled container before restarting production in finally. It never changes leases/status/expiry.617 local tests pass; actual interactive approval and real response-loss acceptance remain NOT RUN. This is an operator utility, not a product policy change or independent human review.

## D70: one approved real PR with deliberately lost final response

Complete the Phase4 response-loss gate using a trusted one-shot driver on the existing control VM. Stop the normal dispatcher only with admission closed and repairs idle; approve the exact unexpired preview through the API; run the unchanged deployed GitHubDispatcher against the real functions-only store and dedicated App. Scope every claim to the exact intent/digest. Use the pinned product image, UID10003, read-only root/mounts, no capabilities, resource limits and only the DB socket/dispatcher password/App key. No worker, provider or candidate execution mounts; no new cloud resource or permission. Always restart the ordinary dispatcher in finally.

Branch and commit use ordinary durable dispatch/readback. After the final actual GitHub PR response, discard that response before readback/confirmation by ending this controller turn with the existing uncertain-operation exception. Require durable PR_PENDING and exactly three write records, one unconfirmed. Let the original180-second lease expire naturally; do not edit status, lease, expiry or approval. The restarted production dispatcher must confirm via read-only reconciliation with no repeated write. Independent App commit/tree/source/PR readback, completed-state restart and exact approval replay follow. This is controlled application response loss after real HTTP, not a fabricated network outage. Three controller-double tests check exact scoping and final-response-only loss; the real gate is not claimed until observed. No independent human sign-off.

## D69: complete GitHub tree readback and all-stage recovery checks

Phase4 review found that candidate bytes/diff/parent checks did not inspect the resulting commit's tree mode, and a non-object PR result could escape fixed GitHub diagnostics. Require the returned commit/tree identity, complete nontruncated tree, unique allowlisted regular files (100644), and exact candidate blob before compare/content readback. Reject executable/symlink/submodule/extra-path trees even when candidate bytes match. Reject malformed PR list elements and top-level objects with a fixed diagnostic. No candidate, verifier, approval expiry, SQL or permission changes. The existing Git trees read endpoint needs no extra permission. GitHub's official [tree documentation](https://docs.github.com/en/rest/git/trees?apiVersion=2026-03-10) distinguishes regular, executable, symlink and submodule modes; [commit documentation](https://docs.github.com/en/rest/git/commits?apiVersion=2026-03-10) binds the commit to its tree (checked Nov5 KST).

Separate critical pass covers complete-tree identity, fixed GET destinations, no automatic write retry, unchanged source/parent/diff checks and malformed-shape diagnostics. Twelve dispatcher fault cases now cover lost reply, lost prepare acknowledgement and lost readback acknowledgement for branch/commit/PR stages. Disposable real SQL additionally covers commit/PR lease takeover, stale-controller rejection and no second dispatch; these use synthetic receipts, not actual GitHub writes.607 Windows tests pass/86 Linux skips; seven real SQL groups pass. New pinned product image886e5044e05ce84b78c2fc10ae19019d577338b66e7808475d0020a4fb452bab contains72 exact allowlisted files at UID10003. Software-only replacement on the existing VM preserves old containers and requires closed/idle execution plus blocked inference. No new dependency, cloud service or inference request; existing $150/$25 credit-only limits apply. This review is not independent human sign-off. Actual PR acceptance remains a separate unfinished gate.

## D68: single-use external writes and signed fresh batches

Phase4 uses migrations013/014, now applied and immutable. GitHub preview binds exact actor/version/semantic epoch/configuration/base/diff/path/draft text and expires after ten minutes. Every branch/commit/PR stage durably records its exact request before HTTP; a lost database acknowledgement sends no request. Pending stages reconcile through read-only exact repository/branch/commit bytes/PR checks, even after local revocation, and never resend unknown writes. Bounded retry exhaustion stays UNCERTAIN with a retention hold. Provisioner resume_pr_readback can only restore readback of the last existing stage and expires write authority. It cannot approve or retry a new external mutation. Revocation after committed dispatch cannot recall an already authorized HTTP call; preserve actual external history and block later stages.

Signed ingress authenticates exact bounded bytes before parsing, uses a per-connection derived key, five-minute skew and durable scoped event identity. First acceptance freezes the current exact version; replay cannot rebind it. Connection authority is owner/session-bound and expiry-bounded, with explicit revocation cancelling unfinished jobs. Keep GitHub and batch master secrets in distinct least-privilege service mounts. New optional cryptography dependency is now in the pinned product image only; candidate/verifier dependencies unchanged.

Separate critical review covered fixed API origin/no redirects/proxies, malformed upstream shapes, streamed errors/response bounds, private descriptor reads, permission/repository/tree scope, locking/fencing/commit acknowledgement, concurrent approval CAS, retention holds, pending readback after revocation, replay binding and browser stale/double-submit behavior. Added tests and stable sanitized errors address the findings. This is Codex review plus automated verification, not independent human sign-off.

## D69: deployed acceptance and honest harness recovery

Browser and signed-event acceptance used existing paid infrastructure with zero new inference calls/resources. Two fresh isolated executions matched; dispatcher restart, same-event/lost-reply recovery and revocation preserved exact identities. Final version and connection are revoked; any later PR demonstration needs a new legitimate proof/version. Never modify revoked history. Source-bound receipts preserve failed harness runs and resumed readback, rather than claiming one uninterrupted pass.

Initial Playwright route.fetch used a client without the project CA; its native error exposed temporary synthetic session/CSRF in tool output. Immediately revoked that exact session, retained the already-completed batch, changed only the trusted harness transport/diagnostics, and reconciled without duplicate execution. No provider/App/cloud key was involved. Later harness-only corrections opened a collapsed revoke control and used the actual proofflow-product-retention.timer unit. Final browser revocation/mobile/logout and both receipts passed. Private raw evidence stays outside Git; no independent human approval or universal security claim follows.

Dedicated App setup helpers validate encrypted local key ACLs and account scope before fixed pinned-SSH installation. Existing development authentication is used only for read-only administrator repo/Actions/hooks preflight, never mounted or forwarded to product. Actual installation and product GitHub writes remain NOT RUN pending owner sign-in/setup and concrete exact PR approval. The current owner request for setup help does not grant the product a broad write bypass.

D52 — Deployed probes drive exact-mode input writes, bounded failure diagnostics, dotted cgroup counters, real /tmp plus shared bounded binds and a two-second kernel-termination observation grace. Execution limits are unchanged; collection still requires zero writers. D53 — Preserve default fork capacity failure; voluntary32-task fixture proves guest fork accounting, not default63-child capacity.

## Latest owner and deployment decisions — Nov 4

- D48 supersedes D23/D27/D30's indefinite paid-action block: owner explicitly authorizes credit use for the project while they await support. Verify actual credit, expiry and charges; retain $150 total/$25 inference, no personal payment. Unknown tax/non-overage terms remain unknown rather than promised guarantees.
- D49 supersedes D19 and older stop-before-Phase-2 language: complete Phase 1 acceptance, update docs, commit/push/verify and report, then continue Phase 2 while the owner is away under their explicit instruction. Silence is not additional authorization for publication, business policies or spending changes.
- D50: administrator API key stays encrypted under Windows DPAPI outside Git; pre-pinned SSH host identities avoid trusting a first network connection. Exactly two quoted VMs created, with private VPC and administrator-only SSH firewalls. Empty-machine rebuilds are setup recovery, never application-data migration.
- D51: operational guard cuts off early at $120 observed project/account spend and a funded review deadline, with a fixed November 23 maximum. Preserve $30 headroom; no automatic creation on recovery. This is a best-effort task on the administrator computer, not provider-enforced billing. Inference requires the separate database admission cap.

All decisions below dated 2026-10-24; implementation evidence remains NOT RUN. Ordinary design defaults may be refined before schema freeze with traceability and tests. Business meaning outside synthetic demo approval needs the owner.

| ID | Decision and reason | State / authority |
| --- | --- | --- |
| D01 | Phase 0 documentation/tool readiness only; retain event timing gate | Owner instruction + current rules; accepted |
| D02 | Reuse supplied empty folder, clone exact private repository, start its default main; preserve history | Authenticated identity/read evidence; accepted; push separately verified |
| D03 | One confirmed human owner + Codex; no assumed hours or independent reviewer | Owner clarification; accepted |
| D04 | Synthetic exact raw-field duplicate equality, earliest ordinal representative, hold all conflicting identities; strict precedence | Broad semantics owner-approved; exact examples/default representation in contract.md |
| D05 | v1.1 finite downstream filters, exact customer attributes, optional merchant/currency rollups with schemas and V10 | Synthetic scope approved; coordinated schema extension pending Phase 2 |
| D06 | Contract/verifier/runtime changes invalidate eligibility via policy epoch; immutable batch binding survives as history; explicit revoke stops publication | Conservative engineering choice; race tests required |
| D07 | Durable execution UUID + manifest + journal; generation-fenced transitions; reconcile before retry; no exactly-once claim | Engineering choice; Phase 2/4 tests |
| D08 | Dedicated Linux runsc/systrap worker, independent guest process/resource probes, supervisor-owned bounded storage survives stop | Primary docs support direction; compatibility unproven |
| D09 | Two-model small authenticated Vultr probe before selection; strict local JSON schema regardless of provider mode | Catalogue-only now; account/model/billing pending |
| D10 | Equal-budget development pilot, 72-run minimum comparison; 216 runs conditional on measured cost/upper bound | Replaces unfunded p43 assumption; eval/plan.md |
| D11 | $150 project/$25 inference ceilings, eligible credits only; ask before potential out-of-pocket exposure | Owner standing authorization; account charges unverified |
| D12 | Revise $10 storage allowance to $18 reserved minimum; total target $140.20, not quote | Official billing observation; account-specific charges pending |
| D13 | MIT proposed for owned code; no LICENSE issued until ownership clearance; source PDF excluded | Owner says clearance unestablished |
| D14 | Local Node 24 LTS/uv tooling isolated; application dependencies/images pinned at kickoff | No global tool replacement; verified local commands |
| D15 | Required human review gap stays explicit; automated checks + separate critical review continue development | Latest owner instruction supersedes treating missing teammate as development stop |
| D16 | Product App/repo/action approval separate from development Git authentication and checkpoint authorization | Preserves product external-action boundary |
| D17 | P1 minimizer, fancy analytics/motion, multi-model routing/extra profiles deferred; single complete deployed path first | Solo-first plan; no safety/approval cuts |
| D18 | Page 11 live foundation gate moved to Phase 1; Phase 0 cannot claim health/sandbox success | Resolves PDF sequencing vs user pre-event boundary |
| D19 | Stop after successful Phase 1 checkpoint for owner review, before Phase 2 | Latest user task supersedes automatic phase continuation for this task |
| D20 | Owner confirmed the window-open assertion was premature and no early permission exists; wait for Nov 4 00:00 KST/current official opening | Resolved owner clarification; do not ask again; finish preparation only |
| D21 | Propose Seoul AMD High Performance control 2c/4GiB and worker 4c/8GiB; preserve isolation/headroom | Public API plus authenticated unsubmitted $24/$48 monthly previews; final networking/fees/coverage and deployment entitlement pending; no provisioning |
| D22 | Reserve $72 compute until account billing is settled; revised provisional total $145 within $150 | Replaces D12's $67.20 compute/$140.20 total; API hourly/monthly fields and billing article require reconciliation; not an enforced cap |
| D23 | Account/quote inspection only; no resource, inference subscription, payment verification or billable activation now | Latest owner instruction; login succeeded but credit terms remain unverified |

## Kickoff decisions — 2026-11-04 KST

- D24 supersedes D01/D20's waiting state: the official dashboard explicitly shows Live / Submissions open. Core Phase 1 work can begin. Stop before Phase 2 still applies.
- D25 refines D11/D23: $150 total/$25 inference are promotional-credit ceilings, not personal spending authority. No deposit, card charge or uncovered liability is authorized. Credit application does not itself prove available balance, coverage, expiry or bounded charges.
- D26: minimal trusted FastAPI/Pydantic health surface, exact PyPI dependency pins and uv lock. No arbitrary provider or candidate dispatcher. Liveness is separate from readiness, which remains closed until real infrastructure verification exists. Dependency review and separate critical review are recorded in phase1-readiness.md; no independent human sign-off.

- D27: owner completed the event Gift Code flow; authenticated $200 credit/December 4 expiry resolved activation. Current $24/$48 compute previews and usage-only inference quote were read without purchase. No hard non-overage/expiry protection or precise inference/tax coverage found; maintain credit-only gate under standing owner limits. Owner asks autonomous decisions, not repeated questions or personal spending.
- D28: Trivy image scan added to foundation review. Fixed outdated runtime pip by using hashed pip 26.3 during build then removing pip. Remaining Debian findings are retained, not suppressed; local health testing is not deployment/release security acceptance.

No installed model/provider, product permission, cloud rate or test result is inferred from these planning decisions. Changes must record the old claim that is no longer valid and the acceptance evidence required.

- D29 (Nov 4 follow-up): strip unnecessary setid permissions while retaining packages/notices; inspect running service privileges and keep all CVEs visible. Nine HIGH findings have health-only triage, not a deployed waiver. No unstable-library substitution or weakened gate.
- D30 (Nov 4 follow-up): official tax/allocation/stopped-VM guidance does not resolve the credit-only billing gate. Keep paid actions blocked, no repeated owner question; new authoritative account/event evidence is required.

- D31 (Nov 4 local follow-up): implement only trusted collector/log components while cloud spending is blocked. Fixed retained-directory descriptor and O_PATH inode pinning precede regular-file I/O; no arbitrary path or stopped-writer flag. Supervisor must independently prove quiescence and exact execution ownership; metadata race tests do not substitute for it. No new dependency/privilege or changed contract cap.
- D32: preserve unparsed exact output bytes/hash and bounded raw log prefixes; parsing, verification, immutable transport, escaping at display and runtime cleanup remain separate unimplemented stages. Local component tests never count as candidate execution or deployed acceptance.

- D33 (Nov 4 owner guidance): accept owner-relayed organizer service coverage and 1–2 week judging uptime for planning, with clear provenance. Challenge 1 still uses Vultr; runsc remains our stronger project choice. Broad authorization means continue WIP without repeated permission, while credit-only/private/Phase 2 boundaries persist. Tax/non-overage terms are still unknown; one precise support-message permission request is pending, no message sent.
- D34: implement a single-project, integer micro-USD PostgreSQL admission ledger, nonlogin owner and separated dispatcher/reconciler privileges. Require fresh READ COMMITTED snapshots and durable successful commit before external I/O; uncertain outcomes retain funds. Local concurrency/crash checks are real, not deployment acceptance or a cloud billing cap.
- D35: offline JSON probe planning binds payload and conservative integer reserve to reviewed rate evidence/expiry; no HTTP/secret/provider fallback. Synthetic tests never count as real inference. Pinned PostgreSQL is local test-only with retained critical scan findings; it is not selected as the deployment image.

- D36: owner reiterates continuous development and no repeated credit-sufficiency questions. Do not hold ordinary development for an answer to the support-message request; no explicit support-send authorization was received, so no message sent. Credit-only/private/Phase 2 constraints remain.
- D37: optional pinned Psycopg/HTTPX client integrates real local committed ledger operations with one fixed HTTPS request. Failures never automatically retry or release funds; reported usage never settles billing. Default health image excludes the client. Separate real DB and mock transport tests preserve honest evidence; no live-provider claim. Protected/client/dependency review is recorded in readiness.

- D38: separate worker dependency lock pins pandas 3.1.0/NumPy 2.5.4; controller has neither. Build/scan locally without running worker image. Fixed nonroot bootstrap applies reviewed rlimits, allowlisted environment and exact CLI; it is not a supervisor or evidence of gVisor resource enforcement. Candidate execution remains designated-worker-only. Readback/thread settings never replace the deployed hostile probes.

- D39 (Nov 4 supervisor): Docker remains image-build tooling; execute pinned runsc directly within a per-execution systemd cgroup, with runsc cgroup management disabled and no delegation. This keeps runtime/gofer descendants under the independent 20s watchdog after supervisor death. A pre-start gate requires observed unit policy and denies delayed launches after staging removal. Real local systemd fixtures support the host lifecycle only; runsc/pandas/deployed enforcement remain unproven. No plain-Docker fallback.
- D40: worker-private SQLite WAL/FULL journal commits identity/fence/admission before staging; exact replay never executes again. Persist bounded output copies before normal unmount, then record cleanup separately. Reserve at most 20 capture slots including unfinished jobs; exact acknowledgement or five-minute maintenance sweep releases copies. Cleanup uncertainty quarantines admission. A resident one-second maintenance loop starts after recovery and fails admission closed on errors. Deployed service restart wiring, immutable image import and mTLS transfer remain Phase 1 composition gates. Separate critical review recorded in sandbox.md; no independent human approval.

- D41 (Nov 4 service): use a small one-request private TLS 1.3 framed RPC, dedicated CA plus exact peer leaf pins, fixed operations/limits and no proxy/HTTP/tool dispatcher. Bind creates to the controller's expected runtime digest; immutable execution IDs reconcile disconnections. Transfer independently checked bytes to durable controller storage before exact acknowledgement. Lost ACK never causes execution retry. Local TLS/host fixture evidence is distinct from deployed acceptance.
- D42: derive a read-only SquashFS blob from an approved local Docker create/export with no start or pull; do not extract archive paths onto the host. Pin the blob independently in deployment configuration and verify read-only loop backing identity. Record builder/export/image hashes; a receipt alone is not trust. New host tool usage/privileges and separate review are documented; no Python dependency change, cloud action or candidate execution.

- D43 (Nov 4 database/provider): same-control-host Unix socket plus client-required SCRAM replaces arbitrary libpq DSNs; fixed database/login, no PG environment/password-file fallback. Separate peer admin and disabled settlement identity. Host-only bounded credential files do not authorize activation. No TCP database support is implied.
- D44: replace the active vulnerable PostgreSQL fixture with the pinned, patched nonroot Alpine build after real migration/auth/crash tests and a zero-finding scan. Preserve old receipts; do not transfer this result to the helper/control/worker images or claim deployed clearance. Protected configuration review and remaining gates are recorded in readiness; independent human sign-off remains unavailable.

- D45: bounded immutable probe intents/results preserve exact bytes; read-only recovery cannot resend or settle. Unfinished intents consume the 100/account cap. Synthetic restore never authorizes a restored spend ledger to dispatch.
- D46: pin the complete gVisor release-20261102.0 bundle and fixed companion directory. No runtime auto-download or local guest execution. Unavailable package inventory is a review gap, not a clean scan.
- D47: require actual kernel cgroup limit readback before launch; retain sampled host counters with missing-final-sample state. Host counts do not prove guest fork/thread enforcement.


## D54: distinguish host containment from guest fork capacity (Nov 4)

Separate critical review of the deployed fork flood: the unchanged default fixture's expectation of 63 simultaneous children remains FAILED (45 observed before runtime exit2). A read-only host observer captured pids.max=128, sampled_peak=128 and pids.events max=1 on that exact execution. The kernel denied further tasks; runtime descendants terminated and cleanup confirmed. The independently lowered32 guest fixture proves31 children/EAGAIN/no hard-limit raise; the64-thread fixture proves63 threads plus main. These are upper resource bounds, not a promise that gVisor can support every combination up to both ceilings simultaneously.

Disposition: process containment passes; default fork capacity is an explicit compatibility limitation. No deployment limit, fixed fixture expectation, collected output or candidate result was changed to pass. The failed fixture remains in evidence and its runner still fails. Simple pandas workloads are eligible for the next isolated probe; any runtime nonzero, partial output, timeout or uncertain cleanup is ineligible for verification success. Model-generated code remains untrusted and runs only on the designated worker. This is Codex's separate critical review, not independent human approval.


## D55: persistent SSH recovery and real reboot gate

The control reboot failed its180s administrative recovery bound because ssh.socket's443 setting did not govern the enabled ssh.service startup. Recovered via worker private forwarding with the original control host-key pin; no agent/key forwarded, no data rebuilt or host check bypassed. Explicit key-only sshd ports22/443 plus enabled regular service now survive both real VM reboots. The bootstrap template includes the same persistent behavior. Retain the initial failure and successful follow-up evidence.

## D56: provider probes, reservations and bounded development backup

Both2048-token coding responses exhausted reasoning allowance and were rejected unchanged. New IDs with8192 maximum completion tokens (already the adapter ceiling) passed for both models; all eight requests retain their reservations. Authenticated provider usage reconciles token counts, not a final invoice. No security/output/business limit changed. Flash Next is a reasonable first Phase3 candidate based on lower catalogue cost and this single faster coding probe; it is not a benchmark or quality superiority claim.

Phase1 private state now has a Windows-user-bound DPAPI off-VM backup and actual disposable restore. This proves encrypted local recovery for this operator profile; it does not satisfy the later portable restic/object-storage requirement. Empty HTTPS health is operator-only; public application admission remains503. No public release or human security approval is inferred.

## D57: bounded Phase2 representations and partial evidence components

Use explicit proofflow-json-v1 ASCII canonical bytes, Unicode scalar key ordering and lossless signed64 JSON integers with golden vectors; server hashes are authoritative. Preserve raw CSV strings and every occurrence. Exact source amount/time parsers use a finite documented grammar and never infer/round. Normalized input expansion must fit the existing10MiB worker cap. No arbitrary policy extension or Q08 choice is introduced.

Output structural decoding and V02–V04 lineage checks are internal partial components, never a verdict. Tests expose their deliberately incomplete coverage so no caller can mistake them for the full verifier. Remaining money/reasons/filter/duplicate/rollup/canary/runtime/approval gates still apply.

Linux assets use a private administrator-opened directory, flock serialization, temp/fsync/rename/directory-fsync, readonly single-link object checks and exact rehash. Same-UID administrator compromise is outside this control; no public hash-only authorization, retention, quota or registry exists yet. Critical pass reviewed hostile names, Unicode errors, byte expansion, ownership swaps, concurrent publication and fsync faults; fixed malformed-name Unicode error leakage. No dependency/privilege addition, human approval or Phase2 completion is claimed.

## D58: private product identity and immutable registry before HTTP intake

Use a separate product database and nonlogin owner/API/provisioner roles. Runtime API cannot create privileged sessions or read/update tables directly; the provisioner is an administrator-only identity. Credentials use256-bit random tokens, separate CSRF, domain-separated hashes, strict duplicate/header/origin handling and secure host-only cookies. PostgreSQL checks current workspace/session authorization on every function call. Fixed lock order serializes quota and revocation races; compare exact asset identity on retry. No application state/verdict/policy/approval fields are introduced.

Conservative private-development bounds:8 workspaces,32 sessions/workspace,64 assets and128MiB per workspace; expired/revoked records still count. These do not alter source/execution limits or grant public guest signup. SQL migration now owns database PUBLIC CONNECT/TEMP and schema CREATE revocation: the separate critical pass caught that these protections initially existed only in fixture setup. Moved them into the migration and reran real privilege/race/restore tests. No independent human sign-off. Product SCRAM deployment, adapter/HTTP integration, retention, queue and full verifier remain open; Q08 is unchanged.

## D59: owner resolves Q08 and freezes synthetic v1.1 policy

On2026-11-04 KST the owner selected “Hold the batch for the missing required field (recommended).” Missing required customer attributes therefore block all relevant source occurrences before date/currency exclusion; invalid exact duplicates do not become harmless DUPLICATE_EXACT records. Keep all applicable filter/source diagnostics and every occurrence. This resolves the schema-freeze gate without granting real-customer policy, public release or exact-version approval. Freeze the finite JSON representation/example before implementing the independent reference and output comparison. Routine wire defaults and supplementary runtime constraints are documented in contract.md/schema; no model/candidate may change them.

## D60: bounded verifier and protected fresh canaries

Deploy a separate immutable Python-only verifier image under systemd RootImage: UID/GID10002 distinct from provider10001, empty capabilities, no-new-privileges, denied socket syscalls, read-only root/no host binds/credentials,512MiB/no swap,1CPU/32 tasks,10s wall and15MiB output. Fixed bounded-data operations accept no pipeline/code/runtime/path. One locked slot is recovered before reuse; systemd owns the watchdog independently. Root launcher privilege is confined to the fixed plan; administrator/control compromise remains trusted. Request/source/output/image-bound reports are evidence, never approval.

Fresh controller-generated256-bit seeds vary IDs/order, composite ownership, refunds/zero/duplicates, conflicts/ambiguity, declared attributes/filter boundaries and rollups. Candidate gets ordinary normalized inputs/contract, never seed/oracle. Correct quarantine behavior may match while source occurrences still block. Four real worker executions with deployed comparison prove this primitive; they are fixtures, not AI repairs or product API completion.

Critical review found directory allowlist exceptions re-included host/cache modules. Explicit descendant exclusions and image COPY sources/modes, final inventory inspection and rerun probes corrected it. Identity provisioning rejects UID/group collisions; diagnostic faults are outside the image. Journal capacity64 includes uncertain failures; no automatic retry/eviction. Aliases that make required headers unrepresentable are rejected earlier (all CSVs already failed them); complete swaps remain supported. No new dependency/service purchase. No independent human sign-off; prior native/runtime advisory limitations remain.

## D61: private product API, reservations and original-run queue

Reserve asset bytes/objects before publication; retain uncertain reservations. Stable per-content staging paths recover only matching prefixes and bound crash leftovers. API inputs carry IDs/data only; no runtime/tool/status selector. Four full ASGI requests, bounded streaming bodies and fresh DB authorization before/after downloads limit memory and disclosure. Exact contract bytes require explicit confirmation; matches and held source data remain distinct. The original failure page escapes source-derived ownership witnesses, reads committed records and cannot activate versions.

Separate functions-only API/dispatcher logins use SCRAM and short committed transactions in proofflow_product. Immutable migration receipts are committed with SQL; existing budget rows stay untouched. Sixteen global retained jobs and one worker lease bound private development.45s lease/10s heartbeat, generation fencing, exact execution intent, source/output/report hashes and cleanup-bound failures prevent stale completion. Lost execution enters reconciliation; no replacement is dispatched. Five failed lease generations preserve a held capacity for operator investigation. Policy epochs retain old execution identities; revocation prevents publication. No VERIFIED/COMPLETED or external action function exists in this Phase2 queue.

New privileged surface is a fixed Unix-socket verifier helper: kernel peer UID10003, root-peer check, bounded frames, fixed immutable image/command, and independent systemd watchdog. It accepts no executable payload field. API/dispatcher run as10003 in separate restricted containers with separate credential mounts; API has no worker/provider/verifier socket mount and is planned networkless. Shared UID permits read-only shared asset bytes, not shared credential mounts or PID namespaces. Candidate execution stays on the separate worker. The root helper has no DB/provider key. No new dependency version, VM, subscription or inference request.

Separate critical pass fixed temporary-file quota amplification, capacity release before response completion, absent output/report binding, ambiguous cleanup booleans, old-runtime identity replacement during recovery and source rejection being mistaken for execution success. Local checks:478 Windows tests/55 Linux skips,10 real PostgreSQL groups,10 Linux byte-store groups,6 verifier boundary groups and4 Unix peer/frame groups. Product image53 modules match source hashes with no unexpected files. Actual deployed product SCRAM/HTTP/queue/failure UI remain NOT RUN until deployment checks; these local fixtures are not live integration evidence. Human review remains unavailable.

D61 deployment follow-up: actual HTTP/queue original runs and separate cancellation/dispatcher-loss checks now pass. The root socket directory was created0700 because umask077 removed group traversal from requested0750; explicit chmod after owned directory creation fixed it, without widening the socket0600 or UID allowlist. Initial jobs stayed unfinished before worker dispatch; the first later reconciled to a real mismatch. A probe with a missing interval endpoint was correctly rejected; only fixture data changed. Applied migration003 is preserved; additive004 persists exact cleanup evidence with failure/cancellation. No table status edits or historical migration rewrite. Current API is private TLS over Unix socket, not a public guest service. Synthetic probe sessions are administrator-provisioned test identities, not human approval.

## D62: authorized bounded event replay and private service replacement

Migration005 grants API-only reads of at most64 committed job events after a current-authority/cursor check. SSE binds resume IDs to exact job UUID and decimal sequence, rejects duplicate/foreign/noncanonical/oversize/future cursors, uses string sequence in data and returns204 when terminal replay is exhausted. Reauthorize before each frame after potentially slow sends; no promise to recall already-delivered bytes. Heartbeats are comments, not events. Two event connections within four API slots,60s loop/65s outer bound and fixed failures limit resource use. Browser EventSource integration is later work. Unit revocation-between-frames and actual logout-stream checks passed; no independent human reviewer.

Replace only the exact prior trusted product image while admission is closed and all jobs terminal. Stop/check/rename the previous container for preservation, then create the new pinned container with the same reviewed mounts/limits. No deletion, secret rotation, new cloud service or automatic rollback. Partial failure leaves affected intake stopped for reconciliation. Old applied migrations stay immutable. Current verifier and worker image identities are unchanged.

## D63: private browser wire and revocation-first raw retirement

Use vanilla same-origin HTML/CSS/JS served from the existing private API, with no new runtime dependency/CDN. Import only an exact administrator-provisioned session/CSRF pair; mint no authority. Browser summaries validate a separate versioned wire contract and generate JSON Schema plus TypeScript deterministically. Preserve sequences as decimal strings. Only textContent renders source-derived values. Same-page job/upload retries preserve IDs; unknown submission across reload remains an explicit limitation. Exact contract and deletion confirmations remain server-authorized.

Retirement needs a committed revoked workspace and a terminal, confirmed worker-cleanup manifest before touching bytes. Shared directory leases serialize writers/runners against an exclusive nonroot byte worker; permanent markers block restored reads/execution. Rename execution directories to workspace-bound retiring names before removing content so a crash cannot orphan ownership attribution. Do not follow links, change roots, kill active workers or invent cleanup. Root coordinator remains a trusted administrator and uses fixed commands; byte process has no network/caps/secrets,128MiB/1CPU/16tasks/20s. Retain existing operator synthetic evidence unless explicitly deleted. The older backup helper now rejects guest/deletion state; seven-day tombstone and worker metadata lifecycle plus backup expiry/restore still need implementation and acceptance. Public intake stays closed.

Separate critical pass reviewed schema grants/lock order, token/Origin/cookie boundaries, file-selection/approval race, state clearing, native error redaction, deletion/write/restore races, crash recovery and backup resurrection. Tests are documented in the browser-retention receipt; no independent human approval. Development-only Playwright1.64.1/pyee14.0.0/greenlet3.5.6/typing_extensions4.16.0 were installed for actual Chromium tests, excluded from all product images. Chromium156 headless shell uses the verified exact leaf SPKI after Python CA verification; no global certificate bypass or trust-store modification. References: [Playwright installation](https://playwright.dev/python/docs/browsers), [Chromium SPKI flag](https://chromium.googlesource.com/chromium/src/+/8402d3c5bc13e018fa75eba650ed881755e0223b). Root-only local WSL test venv and python3.12-venv support trusted tests; no candidate program executes there.

## D64: finish the original Phase2 gate and recover uncertain browser replies

Phase2 acceptance follows the original schemas/backend/verifier row in phase-plan.md, not an ever-expanding release backlog. Its v1.1/hash, SQL/auth/assets/queue, real original execution, V01–V10 and deployed failure-view obligations now have evidence. Earlier next-session text mixed Phase2 tasks with R37/Phase5 retention hardening and T22/Phase6 portable backups. Preserve those later obligations and deny public release until their actual gates pass; do not label them implemented or ask the owner to approve routine phase continuation. Composite trace rows remain partial until their later workflow exists.

Persist only bounded request IDs, workspace and session expiry in same-tab sessionStorage before enqueue. No tokens/source bytes; malformed/expired/foreign/extra fields fail closed. Reload does not submit; user retries the identical body/key explicitly, with fresh DB authorization. Storage failure prevents POST. Actual browser fault injection lost an acknowledged response and recovered the identical already-committed worker job after reload, with no extra execution.

The final retention probe creates exactly one disposable synthetic guest/job. After real worker/verifier completion, revocation precedes fault injection in the bounded nonroot byte worker. Remove the intent only after the production workspace-bound directory rename, then fail deliberately; never fake completed status. Normal production retention must resume without needing that deleted intent, erase assets/journal/registry and preserve other workspace evidence. The deployed probe passed. Its retained intent prevents blind reruns. No new cloud service/provider call, independent human approval or public release. Full retention and backups stay explicit later release gates.


## D65: bounded private repair and separate critical review (Phase3)

Continue under the owner's Phase3 authorization; the older Phase0 timing/Phase1 stop notes are superseded. Keep private and credit-only $150/$25 limits. No new service or subscription. A separate repair queue references a real mismatch with zero blocking occurrences and the currently approved exact contract. It shares the original worker admission lock. Three proposals maximum, 300-second admission deadline, 120,000 input/32,000 output token envelopes and $0.50 reserved per job; a durable $5 development envelope survives workspace deletion. The implementation is stricter: three calls, 20,480 input-token allowance per call and 8,192 output tokens, no uncertain transport retries. Existing project budget reservations remain held; no estimated usage is treated as invoice settlement.

Text context is at most16KiB plus the fixed system message. Qwen documents byte-level BPE and ChatML; a4,096-token allowance covers fixed framing. Reported prompt usage above20,480 or missing usage stops the job. This is a conservative text-only admission bound, not a locally measured provider tokenizer count. Full262,144-token input pricing still funds each monetary reservation. Sources: https://qwen.readthedocs.io/en/latest/getting_started/concepts.html and https://api.vultrinference.com/docs/reference/create-chat-completion (checked Nov4). Fixed Flash Next selected for the development workflow from Phase1 latency/cost evidence; no claim of a quality benchmark. Recheck authenticated catalogue/rates and credits, expire the quote after one hour, never activate another subscription.

Reuse the fixed Vultr transport and durable budget claim, with product-scoped erasable provider request/response evidence instead of placing user source in the historical Phase1 probe table. Only the trusted dispatcher mounts copies of the existing inference and budget credentials. API, worker and verifier do not receive them; no management key is installed on the hosts. This is an explicit reviewed extension of dispatcher privilege, not an unchanged-secret-boundary claim. No new runtime dependency. All generated source remains bytes; only the designated worker executes it.

Every candidate and both fresh protected cases receive distinct execution IDs and increasing worker generations under a repair ID. Persist each intent before dispatch and compare independently captured output hashes/source/runtime/verifier bindings. Canary seeds, rows, expected owners and full reports stay out of prompts and browser summaries. Retry feedback for protected checks is a fixed failure code. Correct quarantine remains held; it only satisfies its protected comparison, never the original-input approval gate. A passing candidate becomes AWAITING_APPROVAL with an owned export/diff, never activation or batch completion. Revocation is checked again before export and completion.

Lease loss enters cleanup-only reconciliation; no provider resend or candidate continuation. Fence above all productive generations, reconcile exact executions, retain unknown funds. Unknown worker delivery continues blocking capacity if cleanup cannot be established. Deletion revokes first, waits for repairs, includes repair journal IDs, erases provider contents/proposals and preserves the spending counter. Historical worker metadata lifecycle remains a later release gate.

Separate critical pass: reviewed SQL privilege/lock order, original-versus-repair admission, immutable call/response records, output/source binding, deadline headroom, token/money reservations, protected-feedback leakage, cleanup-only recovery, retention and secret mounts. Added regression cases for these boundaries. Automated/controller doubles are explicitly labeled and never execute candidate code. Live acceptance still must pass before Phase3 is marked DONE. No independent human reviewer or human sign-off exists.


Phase3 deployed probe finding: the first real repair returned HTTP200/finish_reason=length with all8,192 completion tokens reported as reasoning and no usable patch. Correctly stopped as provider_unavailable; no candidate dispatch, no replay, no reservation release. Authenticated Flash Next catalogue advertises reasoning.supports_max_tokens=true. Add a fixed1,024 reasoning-token cap inside the existing8,192 total, bind the changed payload into a new request hash, preserve the old failed job, and run a new logical repair over the same real original evidence. This changes provider generation settings, not the business contract, verifier, expected output or security/spending limits. Source: https://api.vultrinference.com/docs/reference/create-chat-completion. Updated planner has explicit request-identity/cost regression coverage.


Second actual development run: enforced1,024 reasoning cap was observed (1,023 reported). Attempt1 returned a malformed proposal and was rejected without execution; attempt2 returned source which executed cleanly but failedV07/V08/V09. Retry composition then hit the16KiB prompt bound when embedding the12,614-byte candidate. Preserve that terminal context_limit job and all bytes; do not enlarge prompt/source limits. Use the immutable original plus short hash-bound prior failure summaries for every retry, clarify the public requirements-file shape, and request concise standard-library code. Disable optional reasoning with the documented reasoning.enabled=false; catalogue mandatory=false was verified. This is another explicitly recorded development prompt/planner revision, not final evaluation, a silent per-job retry, an accepted bad patch or a verifier change. Both earlier jobs and reservations remain counted.


Phase3 scope completion adds an unchanged-original path with zero provider calls and three fresh isolated checks, a separate candidate registry (ordinal0 is original,1–3 are model proposals), committed monotonic repair events, and owned bounded ZIP evidence with exact file hashes. The API gains read-only access to controller execution captures, never the worker or provider credentials. Reads use descriptor walks, regular/single-link/private-file checks, fixed names and the retention lease; fresh workspace authorization is repeated before response. One concurrent bundle build,40MiB cap, no executable archive permissions, no extraction/execution. Include original and candidate bytes, authorized inputs/contract, original and last candidate outputs labeled by attempt/verdict, receipts/events/usage, manifest and isolated replay instructions. Protected canary rows/expected owners and provider reasoning are excluded; a redacted receipt is not a replay of hidden tests. Existing pre-event-migration repair history is not backfilled with invented event timestamps. Later exact activation remains Phase4.


Final Phase3 critical review found line-ending reproducibility drift. Normalize application sources to LF and rebuild the image, but preserve already-applied008–010 migration bytes exactly with narrow -text Git attributes. Do not alter migration receipts or applied SQL. Actual final image inventory matches source; its only UI change explicitly labels the model diagnosis an unverified explanation. Acceptance evidence distinguishes the previous tested image from this nonsemantic source-normalization update. All runtime/verifier/contract/candidate hashes remain unchanged.

The Phase0 documentation-hygiene checker still rejected the already-used Phase2 and new Phase3 trace labels. Extend its explicit status vocabulary to IMPLEMENTED/PARTIAL_PHASE2/3; this only validates document syntax, never grants product verification or phase acceptance. All276 requirement rows/59 pages and source/link/ignore checks remain enforced.


## D66: exact-version activation and immutable fresh batches (Phase4 in progress)

The owner's Phase4 instruction authorizes development and private checkpoints, not bypassing the product's exact external-action approvals. Reuse the proven original worker queue for fresh batches; a separate mapping freezes pipeline/version at acceptance. Preserve original receipt verification and add a version-authority guard at dispatch/heartbeat/capture/completion. Ordinary activation does not rebind older batches; explicit revocation cancels affected unfinished work, blocks publication and retains completed history as affected evidence.

Prepare versions only from immutable AWAITING_APPROVAL repair proofs and durably materialized exact source bytes. Actor-bound ten-minute previews bind action UUID, all code/contract/runtime/verifier/evidence hashes, expected active version, pipeline revision and revocation/verification epochs. Recompute before atomic activation; idempotent approved intents return history without reactivation. No Boolean coercion: HTTP must explicitly receive true, not numeric1. Final response reads current version separately. A global semantic epoch increments on runtime/verifier change, including a change away and back; admission generations continue changing as before. Contract revocation deactivates affected versions. No model or candidate chooses an active version or policy.

Separate critical pass includes authorization, lock order, stale preview CAS, same-key changed body, ordinary activation versus explicit revocation, restore/rollback invalidation, candidate hash materialization and retention dependencies. SQL/HTTP fixtures are labeled metadata/doubles and never execution or human approval. No independent human reviewer exists. Dedicated product GitHub App setup and concrete PR approval remain required for the live external-write gate; development credentials must never be installed in the product.


D66 deployed follow-up: migrations011/012 are applied with LF bytes; do not rewrite. Real disposable synthetic workspace passed exact activation/digest rejection/idempotent approval/stale preview, clean fresh batch, invalid extra-column rejection, actual missing-customer held execution, queued revocation and full version/batch/approval/journal deletion. The first held probe incorrectly added an undeclared segment column to a contract with no attributes; parser correctly held it before execution. Preserve that finding and resume the same workspace with a missing-customer fixture, without changing the contract/verifier or replaying completed work. The resumed checks passed. Independent API/SQL tests are labeled; the live synthetic session is not human approval. Application software upgrades may retain an expired inference quote only when the durable budget account is blocked; provider stale-quote rejection remains unchanged.

## D67: dedicated GitHub App boundary and reviewed dependency

Use a private dedicated ProofFlow-Demo repository with only README.md and pipeline.py and no Actions/CI/webhooks. Product App permissions are contents/write, pull_requests/write and metadata/read, installed only on this repository. Validate installation, exact numeric repository ID/private identity and tree; mint repository-restricted installation tokens. Never mount development Git credentials or management keys. API/worker/verifier receive no App key. Requests use the fixed api.github.com origin, TLS verification, no redirects/environment proxy, bounded JSON and fixed operations/path. Unknown writes require readback reconciliation, never blind retry. The concrete draft preview and exact operator approval remain separate from development authorization; no default-branch write, merge or visibility change.

Add optional cryptography50.0.2 only to support maintained RS256 signing for App JWTs; no new JWT library or homemade RSA. Locked transitive packages are cffi2.1.1 and pycparser3.12. New package installation is development-only until a reviewed product image includes it. GitHub documents RS256, iat clock allowance and ten-minute maximum JWT validity; use a shorter lifetime and one-repository installation tokens. Sources checked Nov4: https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-json-web-token-jwt-for-a-github-app and https://pypi.org/project/cryptography/ . This review does not claim an independent human security sign-off or an actual successful PR.

D67 November5 follow-up: actual setup/preflight/preview passed. The owner explicitly approved unused key5183052 revocation, completed with working key5183074 authentication preserved. Exact PR approval was processed after its existing expiry; owner unavailability and broad development permission do not extend or rebind that approval. Preserve the expired intent and use a new exact preview only when the owner can review it. The trusted reconciliation helper never creates an intent, worker job or replacement session; if its actor is already unauthorized, it performs read-only external reconciliation. Fixed the helper's logout expectation from200 to the actual API204. Initial attempt did not retain a final receipt, so its expiry HTTP result is not claimed as captured acceptance. No security policy, applied migration or product runtime changed. Separate critical review covered fixed credential paths/ACLs, no native exception disclosure, read-only GitHub operations, zero durable writes and closed admission; it is not independent human approval.

D67 fresh-preview follow-up: owner explicitly requested a new exact preview before later saying unavailable. That request authorizes preparation, not automatic submission of the unseen new digest. Create a separate named encrypted actor/intent, preserve prior artifacts and reuse the eligible verified version without replaying candidate work. Administrator session filenames accept only the legacy fixed name or a UUID-derived fixed pattern; reject paths before accessing secrets. Completion helper requires the exact supplied digest, compares the current immutable preview, checks authority/expiry before POST and performs read-only reconciliation if already approved. It cannot extend approval, choose another repository/path or replace credentials. Review separates completed-state restart from an unperformed external-response-loss injection. No new dependency, migration, deployed service change, privilege or human sign-off.

D67 second late-answer reconciliation: the owner supplied exact approval after the existing preview and actor expired, then requested no repeated questions while unavailable. No automatic replacement preview or reapproval prompt. Add an explicit read-only reconciliation mode for this retained intent; inspect durable approval/authority using a canonical parsed UUID and compare actual App branch/PR absence. It never posts approval, including when its actor remains valid. Preserve closed admissions and expired intent; no product policy, database migration or deployed image change. Separate critical review and thirteen scoped tests are not independent human approval.
