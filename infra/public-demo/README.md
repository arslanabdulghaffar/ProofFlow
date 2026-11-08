# Prepared public-demo edge

These files are not installed or enabled. The repository stays private. The current
live application still uses pinned operator SSH and private TLS; that tunnel is not
a public demo URL. Public network acceptance has not passed.

The narrow deployment uses the existing control VM and systemd's TLS byte-forwarding
service. It adds no SaaS, VM, database, candidate network or provider. TCP 8443 is the
proposed demo port; 443 remains pinned operator SSH. The API stays networkless on its
existing Unix TLS socket. TLS terminates in the API with a publicly trusted certificate,
so no caller-controlled proxy scheme/host header is trusted. The relay is limited to
eight connections, 32 MiB, four tasks and 25% CPU, with secret directories inaccessible.
These are containment bounds, not distributed-denial-of-service protection.

Before activation, perform these steps in order:

1. Choose a controlled hostname or certificate-eligible IP and obtain a publicly
   trusted certificate matching it. The example `.example` address is deliberately
   unusable. No domain purchase, ACME account registration or certificate issuance is
   implied by the template. Verify the current certificate/renewal mechanism first.
2. Preserve admissions closed and idle; record existing TLS and configuration hashes
   privately. Install the certificate/key in the existing API TLS directory with the
   existing owner/modes. Install `origin.json` as a regular one-link file, owner
   root or10003, mode0400, containing exactly the final canonical HTTPS origin.
   The actual mount is read-only. Restart API and verify exact source/container policy.
3. Use separate individually provisioned guest workspaces and <=one-hour sessions.
   Never publish operator tokens, share a common judge credential or put credentials
   in URLs. Existing guest/session limits, cross-workspace checks, expiry/deletion,
   budgets and exact contract/version approvals still apply. Guests cannot create PRs.
   No anonymous signup or automatic business approval is introduced.
4. Check fresh credit/quotes, the dated funding guard and closed/idle state. Reserve
   judging uptime within $150 total/$25 inference eligible credits. Current dated
   guard expires Nov10 01:29 KST; a balance does not extend it automatically.
5. Install the reviewed socket/service units root-owned0644. Validate with the actual
   host's `systemd-analyze verify`. Only after TLS, guest setup, spending and publication
   conditions pass, create the root-owned enable marker and open TCP8443 in the host
   and Vultr firewalls. Do not modify operator SSH access. Stop/disable this socket and
   remove the enable marker to close public access; do not delete user data.
6. From a genuinely external clean browser, verify the trusted certificate, login,
   three fresh variants plus ambiguity, refresh/cancel/download isolation, guest PR
   denial, expired/revoked sessions and network/cleanup failures. Run the read-only
   `scripts/probe_public_ingress_http.py --origin https://FINAL-HOST:8443` without
   `--ca`; system public trust must pass. A private-CA/tunnel test is not this gate.
7. Reconcile all jobs, retain evidence, close unused invitations and check retention.
   Only then record the actual demo URL in a NEW release package. Preserve the prior
   private package and its exact source/media hashes. Public Git visibility, licensing
   and submission remain separate from having an HTTPS demo endpoint.

No implementation assumes a stale deletion inventory is current. For recovery, the
existing encrypted restore strips all runtime authority and keeps data quarantined.
Lost trustworthy deletion authority prevents old data recovery. An incident requiring
fresh host trust/rotated credentials is not solved by restarting a container. The owner
explicitly deferred offline key custody; do not choose a password for them.

References checked November8: [systemd socket proxy](https://www.freedesktop.org/software/systemd/man/latest/systemd-socket-proxyd.html),
[socket activation](https://www.freedesktop.org/software/systemd/man/latest/systemd.socket.html),
[Uvicorn settings](https://uvicorn.dev/settings/). Runtime uses the installed host's
supported options, not newer optional PROXY-protocol features.

For the no-domain option, [Let’s Encrypt’s official Certbot guidance](https://letsencrypt.org/2026/03/11/shorter-certs-certbot)
confirms IP certificates with the short-lived six-day profile and Certbot5.4+ webroot
support. This avoids a domain purchase, but still needs ACME port80 reachability,
tested automatic renewal and a deploy hook for the API certificate. Test staging
before production; a staging certificate is not browser-trusted. No ACME account,
certificate request, port80 listener or certificate transparency publication occurred
in this preparation checkpoint. Evaluate this option during actual public deployment.
