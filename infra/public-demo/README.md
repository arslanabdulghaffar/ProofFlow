# Public guest TLS operations

The owner explicitly authorized activation on November8. The guest-only endpoint is
https://158.247.227.66:8443. Repository, release package and media remain private.
Public HTTPS does not authorize a source release, license, event submission or product PR.

The existing control VM runs a separate networkless guest API. Its host socket is
`/run/proofflow-public-api/api.sock`; TLS is mounted read-only from
`/etc/proofflow-public-api/tls`. The private operator API and pinned SSH443 are unchanged.
Operator tokens are rejected at both public session import and request authorization.
The relay binds the public IPv4 only: loopback8443 remains the existing health service.
It permits eight connections,32MiB,four tasks and25% CPU. These limits are not DDoS protection.

Public trust is Let’s Encrypt short-lived IP TLS. Certbot5.9.0 and its18 dependencies
are separately pinned/hash-locked under `/opt/proofflow-acme`; no application/worker
runtime dependency was added. Port80 is open for the standalone ACME challenge only;
no persistent HTTP server or directory listing is installed. Staging and production
issuance passed. The first staging request timed out while firewall propagation was
pending; a bounded external fixed-response probe then passed before retry.

## Issuance, deployment and renewal

Use fresh credit checks before changes. No new VM, domain, subscription or payment is
needed for this setup. The current funded cutoff is Nov10 01:29 KST; a certificate's
expiry or an account balance does not extend this cutoff.

1. Install `scripts/install_public_tls_client.py` with the reviewed hash lockfile in
   a root-only revision directory. Use Certbot standalone HTTP01, exact control IPv4,
   `--preferred-profile shortlived`, separate staging/production config/work/log paths
   under `/etc`, `/var/lib` and `/var/log/proofflow-acme`. Validate staging first.
2. Deploy the exact product image using the existing closed/idle upgrade path. Install
   `install_public_api.py`, `install_public_certificate.py`, `public_api_policy.py`,
   `install_product_services.py`, the two units and `public.json` with the current IPv4
   in a protected revision directory. The public installer does not enable its listener.
3. The root-only certificate hook verifies the system trust chain, exact IP SAN,
   matching key, current validity and at least24h remaining. Only the fixed production
   lineage is accepted. On renewal, validate before stopping the public API, replace
   its cert/key, fsync and restart it. A partial installation stays stopped for manual
   reconciliation; preserve pending files and the ACME archive, never bypass validation.
4. Verify TLS over the Unix socket and actual host systemd units. Open only80/8443 in
   the control firewall; preserve restricted SSH and worker rules. Create the reviewed
   root-only enable marker, then enable `proofflow-public.socket`. The installer substitutes
   `@PUBLIC_IPV4@`; never bind0.0.0.0 because loopback8443 is occupied.
5. `proofflow-public-renew.timer` runs twice daily with up to300s randomized delay.
   Certbot's additional random sleep is disabled so it cannot consume the240s service
   deadline. The actual staging renewal dry-run and production no-op/deploy-hook readback
   passed. A dry-run did not replace the production certificate. Inspect the service's
   Result/ExecMainStatus and certificate expiry; timer activation alone is not renewal proof.
6. Run `scripts/probe_public_ingress_http.py --origin https://158.247.227.66:8443` without
   `--ca`. `check_phase6_browser.py --public-guest` uses fresh guest contexts and real
   worker execution; `check_public_security_live.py` tests isolated inert assets,
   operator rejection, guest PR denial, expiry, logout and public-service restart.
   These tests require closed/idle admission initially and delete their own fixtures.

## Access, rollback and recovery

There is no anonymous signup, shared judge password or token in a URL. Provision each
invited guest through the existing scoped workspace/session administration, with a
<=one-hour session. No test credentials survive the acceptance run. Execution and
inference admissions remain CLOSED after testing; invite issuance must include a fresh
bounded operating review before a guest can run jobs. The public login page is live;
this is not an unattended anonymous AI service. Existing exact approvals remain required.

To close the edge, stop/disable `proofflow-public.socket` and `proofflow-public.service`;
remove only the reviewed enable marker after checking its exact path. This preserves
private access and all data. A failed critical guest/auth check requires closing the
edge while reconciling. The initial browser logout probe hit connection overload;
closing old test transports before revocation readback fixed the harness without
changing limits. Four fresh contexts subsequently passed. A separate restart test
confirmed valid access survives restart and revoked sessions never return.

Fresh-host compromise recovery still requires new host trust and rotated credentials;
restarting this container does not prove it. Reissue TLS for the verified replacement
IP instead of copying compromised private keys. Restore data only with trustworthy
current deletion authority; missing authority keeps recovery quarantined. Offline
owner password/key custody is deferred. Existing scheduled backups depend on the
Windows desktop being awake/logged in. Full host-loss RTO/RPO is not claimed.

References: [official IP certificate guidance](https://letsencrypt.org/2026/03/11/shorter-certs-certbot),
[Certbot renewal](https://eff-certbot.readthedocs.io/en/stable/using.html),
[Certbot timer jitter discussion](https://github.com/certbot/certbot/issues/9997),
[systemd socket proxy](https://www.freedesktop.org/software/systemd/man/latest/systemd-socket-proxyd.html).
