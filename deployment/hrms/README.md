# HRMS production deployment

This deployment is separate from the workout and legacy HRMS Compose projects.
It packages unchanged native platform code, the HRMS application service, and
the HRMS frontend. No demo users or local development databases are copied.

## Target and isolation

- Server: `62.238.103.67`; initial URL: `http://62.238.103.67:8082`.
- Compose project: `newtuple-hrms-production`.
- Releases, private environment, backups: `/opt/newtuple-hrms/`.
- The new web container runs its own Nginx. Existing port 80/443 listeners and
  workout Nginx configuration are not modified or reloaded.
- PostgreSQL, Redis and application API ports are not exposed on the host.
- Volumes and network are scoped by the unique Compose project name.
- Builds and tests execute on GitHub runners, not on the shared 4 GB server.
- Containers have memory ceilings and bounded Docker logs. Monitor host memory
  and disk; the ceilings do not reserve resources or guarantee spare capacity.
- Initial HTTP is temporary. Do not use real employee data until HTTPS is set
  up. Later change HRMS_PUBLIC_URL and bind the web port to loopback behind a
  dedicated TLS virtual host, coordinated with the existing edge Nginx owner.

## GitHub configuration

Workflow: `.github/workflows/hrms-production.yml`, pushes to main only, plus
manual dispatch on main. Serial deployments; in-flight deployments are not
cancelled. The activation variable defaults to disabled until server setup is
verified. Deployment uses the `hrms-production` GitHub environment. Do not add
required reviewers if fully automatic deployment on every main push is desired.

Repository variables:

| Variable | Value |
|---|---|
| HRMS_PRODUCTION_ENABLED | false during setup; true after verification |
| HRMS_DEPLOY_HOST | 62.238.103.67 |
| HRMS_DEPLOY_PORT | 22 |
| HRMS_DEPLOY_USER | hrms-deploy |

Repository secrets:

| Secret | Purpose |
|---|---|
| HRMS_DEPLOY_SSH_KEY | Dedicated CI SSH private key; never the personal admin key |
| HRMS_DEPLOY_KNOWN_HOSTS | Previously trusted SSH host keys; strict verification |
| HRMS_PRODUCTION_ENV_BACKUP | Encrypted recovery copy of production.env; not used by routine builds |

The built-in GITHUB_TOKEN downloads the workflow artifact. No GHCR password,
Hetzner API key or personal GitHub token is required by the pipeline.

`hrms-deploy` requires Docker access, which is effectively host administrative
access. Protect main and repository Actions write access accordingly. The
runtime environment is mode 600 and never included in uploaded build artifacts.

## Runtime environment

Generate fresh secrets, never copy `.hrms.local.env`:

- HRMS_DB_PASSWORD, HRMS_APP_DB_PASSWORD: URL-safe database passwords.
- HRMS_JWT_SECRET: high-entropy signing secret.
- HRMS_ENCRYPTION_KEY: stable Fernet key; retain with database backups.
- HRMS_PLATFORM_ADMIN_PASSWORD: bootstrap tenant/platform-owner credentials.
- HRMS_SERVICE_PASSWORD: dedicated application-service credential.
- HRMS_ORGANIZATION_ID, HRMS_ORGANIZATION_NAME, HRMS_ORGANIZATION_SLUG.
- HRMS_ADMIN_EMAIL, HRMS_OWNER_EMAIL, HRMS_SERVICE_EMAIL, HRMS_WORK_EMAIL_DOMAIN.
- HRMS_PUBLIC_URL=http://62.238.103.67:8082
- HRMS_HTTP_PORT=8082 and HRMS_BIND_ADDRESS=0.0.0.0 for initial IP access.

IMAGE_TAG is supplied by the deployment as the full Git commit SHA. Provisioning
installs tenant configuration via public platform APIs. Runtime services never
receive the personal SSH key. OAuth/email credentials are optional follow-up
configuration, not copied from local development.

## Release and recovery

CI checks the platform boundary, runs HRMS tests, and builds three images (the
frontend image includes TypeScript validation). Images are transferred as a
checksummed artifact over SSH, loaded, and deployed under the unique project.
Both HRMS databases are dumped before API migration/startup. Application health
and login routes must pass before `current` points at the new release.

Only HRMS services are recreated. No global Docker cleanup, volume deletion,
Nginx restart, or changes to existing app configuration are performed. The new
app may have brief downtime while containers restart; this is not blue/green.

If migration or startup fails, inspect the failed GitHub job and this project's
container logs. The previous-release pointer is retained, but it is NOT an
automatic rollback: migrations may be incompatible with the earlier image.
Take a fresh backup and assess schema compatibility before deploying the prior
SHA or restoring both database dumps. Never automatically downgrade schemas.
Uploads are persistent in their own volume; include them in an off-server
backup plan. Local database dumps alone are not disaster recovery. Retain
releases/backups according to available disk; do not use global docker prune.

Before activation, verify port 8082 is unused, allow it in the applicable host
and Hetzner firewalls, record baseline responses for both existing apps, then
verify those responses again after deployment. Initial inspected baselines:
workout port 80 redirects (301), legacy loopback 8081 responds 200.

### Automatic organization setup

On a fresh self-hosted deployment, native platform bootstrap creates the active
organization from `HRMS_ORGANIZATION_ID`, `HRMS_ORGANIZATION_NAME` and
`HRMS_ORGANIZATION_SLUG`, and creates its active administrator membership.
Keep the organization ID stable across deployments. The HRMS install job then
verifies that membership and assigns the native tenant `superadmin` role using
public platform APIs before installing the HRMS definitions.

Sign into HRMS with `HRMS_ADMIN_EMAIL` and its configured
`HRMS_PLATFORM_ADMIN_PASSWORD`. `HRMS_OWNER_EMAIL` is the separate platform
administration account, not the HRMS login. Do not make these emails identical.
No employee record or demo data is required for tenant administration. Super
Admin can open Settings → Organization to inspect the tenant, and Settings →
Users/Roles to configure access for HR staff.

Rerunning installation reuses the tenant and existing native configuration. It
does not reset passwords or remove additional roles from an existing Super
Admin. A missing/inactive membership, wrong organization, or missing native
Super Admin role fails installation rather than bypassing tenant checks.


## Google Workspace sign-in

HRMS offers Google sign-in for `@newtuple.com` only. Password sign-in remains
available. Microsoft login and callback routes are not exposed by HRMS.
The unchanged platform validates the Google-returned email domain before linking
or creating a user (`GOOGLE_ALLOWED_DOMAIN` is fixed to `newtuple.com` in Compose).
The gateway binds OAuth state to a secure, HTTP-only browser cookie and validates
the redirect URI. Existing native invitation and approval rules still apply;
active sessions must also belong to the configured HRMS tenant.

Activation:

1. Set up an HTTPS hostname for HRMS and set `HRMS_PUBLIC_URL` in the private
   server `production.env` to that origin, with no trailing slash. The initial
   HTTP IP address cannot be used for production Google sign-in.
2. In the Newtuple Google Cloud organization, configure the OAuth consent
   audience as **Internal**. This restricts authentication to managed Workspace
   accounts; the email-domain check alone does not prove Workspace membership.
3. Create an OAuth client of type **Web application**. Register exactly
   `https://YOUR-HRMS-HOST/auth/google/callback` as its authorized redirect URI.
4. Add repository or `hrms-production` environment secrets `GOOGLE_CLIENT_ID`
   and `GOOGLE_CLIENT_SECRET`. These are separate from SMTP credentials.
5. Deploy main. CI sends both credentials over SSH stdin to a mode-600 server
   environment file before restarting the platform. Neither credential goes
   into frontend bundles, build artifacts, command arguments or logs. Empty
   secrets preserve any existing server configuration; partial pairs fail.
6. Verify an approved Newtuple employee can sign in, a pending employee follows
   the native approval flow, and a personal Google account is rejected.

Google callback credentials cannot be tested end-to-end until the OAuth client
and HTTPS hostname are configured. Reference:
https://developers.google.com/identity/openid-connect/openid-connect


## Temporary MyHub HTTPS hostname (2026-10-09)

Live origin: `https://myhub.62-238-103-67.sslip.io`.
The existing `https://62-238-103-67.sslip.io` belongs to the legacy HRMS and
`https://repsolute.com` belongs to the workout app. Do not replace either route.

The shared `workout-app-frontend-1` Nginx owns ports 80/443. MyHub has its own
`/etc/nginx/conf.d/myhub.conf`, proxying through the Docker host gateway to port
8082. The source template and maintainer are stored in
`/opt/newtuple-hrms/proxy/`. `myhub-proxy-maintain.timer` restores only this route
after shared-edge container recreation (within approximately 35 seconds), tests
Nginx configuration, and reloads only when the route changes. It does not restart
or modify the other applications. This temporary integration depends on the
existing edge container name, workout-app_default network, and port 8082 binding.

Certificate: `myhub.62-238-103-67.sslip.io`, in the shared
`workout-app_letsencrypt` volume. Issued with the shared
`workout-app_certbot_webroot` HTTP challenge webroot. The existing
`repsolute-certbot` cron and HRMS renewal maintainer renew certificates from that
volume and reload the proxy. The new route serves HTTP challenges and redirects
other HTTP requests to HTTPS.

The private `production.env` now sets HRMS_PUBLIC_URL to the new HTTPS origin.
A mode-600 backup was saved on the server before editing. The active release's
Compose file was also corrected to pass GOOGLE_REDIRECT_URI to **hrms-app**,
not hrms-app-db; the same correction is in this repository. Both platform-api
and hrms-app use the new callback origin. OAuth client secrets are still required.

Google client configuration:
- JavaScript origin: `https://myhub.62-238-103-67.sslip.io`
- Redirect URI: `https://myhub.62-238-103-67.sslip.io/auth/google/callback`

To bootstrap again, install myhub-http.conf as the shared edge's myhub.conf,
validate/reload Nginx, obtain the certificate via the existing ACME volumes,
then install the template, maintainer and systemd units in their paths above.
Do not replace shared-edge configuration or stop its existing apps.
