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
