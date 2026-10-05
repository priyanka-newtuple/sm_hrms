# Newtuple HRMS — developer handover

Prepared 2026-10-05. Code inspected at `419374a88077f5f475ca7bc1bd584d0824a2957c`.
This document summarizes the work delivered in this development session and the
decisions a successor must preserve. Production statements below are the last
verified deployment results from 2026-09-30, not a fresh server inspection today.
No passwords, tokens, private keys or environment-file contents belong here.

## 1. Start here

- Repository: <https://github.com/priyanka-newtuple/sm_hrms>.
- Production: <http://62.238.103.67:8082/login>.
- Current HRMS local runtime: <http://localhost:5182/login>.
- Production/default branch: `main`; pushes trigger deployment automatically.
- Work on a feature/fix branch. Follow [AGENTS.md](AGENTS.md); merge through a PR
  or explicit user authorization. Do not stage unrelated files or push casually.
- The current architecture is the API-based HRMS application layer. Older design
  documents may describe superseded in-core implementations or future scope.
- First read [application boundary](design_docs/hrms_application_layer.md),
  [production runbook](deployment/hrms/README.md), and
  [branding contract](frontend/src/skins/hrms_native/components/BRANDING.md).

## 2. Architecture and non-negotiable boundaries

```text
Browser -> HRMS web/Nginx -> HRMS application API -> native platform public APIs
                                 |                          |
                       HRMS journal database       platform database

Separate installer -> native platform public configuration APIs
```

The core platform is generic and multi-tenant. An organization is a tenant;
native entities, forms, workflow definitions, enrollments, states, transitions,
roles and permissions belong to that organization. HRMS installs product packs
as tenant configuration, rather than changing the core engine.

| Responsibility | Source of truth / implementation |
| --- | --- |
| Entity records, native forms/workflows, native permissions and execution | Unmodified platform under `backend/` |
| HRMS orchestration, relationship checks, confidentiality, aggregation | `applications/hrms_api/hrms_app/` |
| Product UI and branding | `frontend/src/skins/hrms_native/` |
| Operation recovery, human audit, product permission overrides | Separate HRMS application database, managed by `journal.py` |
| Domain installation | `install.py`, `provisioning.py`, and the catalog modules |

Rules:

1. Do not modify native state-machine core code or native frontend components.
   Reuse native components from the HRMS skin. Validate with
   `python scripts/verify-platform-boundary.py`.
2. The runtime HRMS layer must not import core managers/models or query platform
   database tables. Use `platform.py` and public HTTP APIs.
3. Each HRMS deployment is bound to one configured organization. Human requests
   require an active user, matching organization, active membership and native
   roles. Never solve access errors by bypassing membership checks.
4. Runtime orchestration uses a dedicated restricted service identity. It is
   privileged, internal, and never sent to the browser or assigned to humans.
5. Tenant Settings uses the real human token through `settings_gateway.py`.
   Do not substitute the service token or expose unrestricted native mutation
   routes. Configuration access must not become an execution/approval bypass.
6. Core audit identifies the service caller; HRMS journal audit identifies the
   human and operation key. Both matter. Multi-call actions are recoverable
   sequences, not distributed database transactions.
7. Preserve existing tenant customizations. Published workflow versions and
   existing enrollments are not silently migrated by an installer rerun.

Baseline: `e583a69f7adb0fc5f87a93cd161590ee54bb2ca3`. The boundary check passed
for 1,416 original backend/frontend files during this handover preparation.

## 3. Implemented product experience

### Local follow-up: Allocations workspace (2026-10-05)

After this handover was created, a separate `/hrms/allocations` workspace was
added on `feat/hrms-allocations-workspace`. It is not part of the last production
release recorded below. It adds Delivery navigation, an allocation directory,
project/status/search filters, details, a separate request view and an Add
allocation drawer. It reuses the existing project API, native Allocation and
AllocationChange records, configured forms, action handlers and permission
settings. Project team cards link to it. No core or database-model changes were
needed. See [allocation implementation](design_docs/hrms_allocations.md).

| Module / route | Delivered behavior | Main implementation |
| --- | --- | --- |
| My work `/hrms/my-work` | Permission-aware shortcuts, onboarding actions, project/allocation approvals, cockpit approvals and content awaiting publication; coherent loading/error/empty states | `pages/MyWorkPage.tsx`, `components/WorkPanel.tsx` |
| Employees `/hrms/employees` | Directory and configured employee creation; manager/role choices, native identity/record creation and onboarding orchestration | `service.py`, `catalog.py`, `pages/EmployeeDirectoryPage.tsx` |
| Onboarding `/hrms/onboarding` | Eight dependent steps, authorized owners, case completion checks and My work integration | `onboarding_template.py`, `service.py`, `pages/OnboardingPage.tsx` |
| Leave `/hrms/leave` | Employee requests, manager/team decisions, native states/transitions and no employee self-approval | `service.py`, `pages/LeaveRequestsPage.tsx` |
| Performance `/hrms/performance` | Cycles, participant/owner selection, goals, self/manager reviews, requested project feedback, calibration, publication, acknowledgement and audited reassignment | `performance.py`, `performance_catalog.py`, `performance_contracts.py` |
| Projects `/hrms/projects` | Project directory, view/edit details, add project/customer, allocations, dated capacity preview, approval/amendment/release flows, commercial-field filtering | `projects.py`, `project_catalog.py`, `project_contracts.py`, `pages/ProjectsPage.tsx` |
| HR Cockpit `/hrms/cockpit` | Policies, L&D events, yearly holiday calendars, job descriptions and openings; draft/review/publish, revisions, audience/date windows, published-item visibility | `cockpit.py`, `cockpit_catalog.py`, `pages/CockpitPage.tsx` |
| Workflows `/hrms/workflows` | Unified authorized operational records and detail/actions using native table, toolbar, columns/filtering and sheet primitives | `workflow_view.py`, `workflow_config.py`, `pages/WorkflowsPage.tsx` |
| Settings `/settings` | Native configuration editors for forms, entities, workflows, users/roles and other available sections; HRMS project/cockpit permission editors; organization details | `settings_gateway.py`, `pages/PlatformSettings.tsx`, `pages/OrganizationSettings.tsx` |
| Public `/public` | Anonymous, tenant-bound published information; category links from login | `cockpit.py`, `pages/PublishedContent.tsx` |
| Employee resources `/hrms/content` | Authenticated published-information view; reachable through company resources, not a separate left-menu item | `pages/PublishedContent.tsx` |

All frontend paths in the table are relative to `frontend/src/skins/hrms_native/`;
Python paths are relative to `applications/hrms_api/hrms_app/`.

### Navigation decisions

The menu is grouped by purpose: My work, People, Delivery, HR publishing,
Tracking; Settings remains at the bottom. Entries depend on capabilities, not
an unrelated menu per job title. Lucide outline icons accompany items. Projects
is a directory/details workspace; operational workflows belong in Workflows.
The separate Published information menu item was removed at the user's request.

`TenantHeader.tsx` shows the current organization above a smaller Newtuple logo.
Name and roles come from authenticated APIs (`/hrms/organization` and
`/hrms/capabilities`); initials are derived from the name. The dropdown shows
the current tenant and an authorized Organization settings link. It is not a
general cross-tenant switcher. `capabilities.ts` holds these queries. Session
query caches reset when user/organization changes in `App.tsx`.

### Projects and allocations

Native types include Customer, ProjectRole, Project, ProjectChange, Allocation
and AllocationChange. Draft change requests do not immediately change approved
operational values. Decisions are revision checked and require the designated
independent approver. Allocation approval recalculates date-based capacity;
over-100% capacity needs a reason and independent approval. Live allocations
and pending requests must be resolved before project closure.

Settings → Roles → Project access configures tenant overrides for project and
allocation capabilities. Native roles remain the catalog; overrides live in
the HRMS journal database and are revision checked/audited. Commercial fields
are filtered server-side. See [project walkthrough](design_docs/hrms_projects_local.md).

### HR Cockpit and public visibility

The designated approver can act from My work as well as Cockpit/Workflows.
Publishers also see approved items awaiting publication in My work. Native
types: `HRMS.Policy`, `HRMS.LearningEvent`, `HRMS.HolidayCalendar`,
`HRMS.JobDescription`, `HRMS.JobOpening`.

Public visibility requires public audience, a published effective version and
valid dates. Employee-only, paused, closed, archived or expired content is not
anonymous public content. This explained an earlier report that a job was
"published" but absent on Careers: the screenshot showed Closed and Employees.
Careers groups job descriptions and openings. The public endpoint accepts no
tenant override and returns only allowed display fields. It renders text, not
untrusted raw HTML. See [cockpit behavior](design_docs/hrms_cockpit.md).

Published content is immutable through the product surface; revisions create
new records/enrollments linked by publication identity. Withdrawal of a newer
version does not resurrect an old publication. Documents currently use public
HTTPS links; private uploads/signed delivery are not implemented.

## 4. Configuration-driven forms, states and permissions

- Shared `forms/ConfiguredForm.tsx` and `ConfiguredField` read the installed
  pack's form via `/hrms/forms/{entity_type}` and apply labels, placeholders,
  required/read-only flags, column span and available enum/picklist metadata.
- Native field display labels are stored in `description`. Relation input IDs
  are mapped to display-name fields; this fixed PM name → Project Manager not
  appearing in Create project. Do not change stored field keys to rename labels.
- Forms refresh on mount/focus and invalidate on native form-change events.
  Missing/inactive configuration is shown as an error.
- This is presentation binding for implemented command inputs, not a generic
  arbitrary-field persistence engine. New fields/types/calculations or command
  semantics still need explicit HRMS implementation. Required business inputs
  and authorized relation choices remain enforced.
- `workflow_config.py` resolves actual enrolled workflow versions. State/order,
  terminal markers, transition labels and destinations come from native data.
  Existing enrollments remain version-pinned; changing the latest definition
  does not automatically migrate them.
- New trigger/state semantics need HRMS handlers. Displaying a configured
  transition does not authorize bypassing domain checks through a generic API.
- Base HRMS capabilities live in `role_capabilities.json`. Project and cockpit
  capability overrides are editable in tenant Settings. Other product
  capability mappings are application configuration, not all editable in UI.

## 5. Self-hosted tenant and administrator setup

The original failure was a platform-owner login in the platform organization.
HRMS rejected it for lacking the correct HRMS membership/token context. This
caused incomplete navigation and an indefinitely displayed "Loading role…".

Delivered fix:

1. Existing native bootstrap creates the active configured organization and
   tenant administrator from the deployment environment.
2. `provisioning.py::ensure_tenant_administrator` verifies native identity,
   active tenant membership, active organization and matching tenant role.
3. The installer grants that administrator the native tenant `superadmin`
   role when absent and verifies it through native APIs.
4. Reruns reuse tenant/configuration and preserve extra roles on an existing
   Super Admin. They do not reset passwords. Wrong/inactive tenants fail closed.
5. Sidebar identity, Settings → Organization and explicit role-load error text
   expose the actual tenant context.

| Identity | Config key | Last configured production email | Purpose |
| --- | --- | --- | --- |
| Tenant Super Admin | `HRMS_ADMIN_EMAIL` | `hrms-admin@newtuple.com` | Normal HRMS administration and tenant Settings |
| Platform owner | `HRMS_OWNER_EMAIL` | `hrms-superadmin@newtuple.com` | Separate platform administration/installer credential |
| Application service | `HRMS_SERVICE_EMAIL` | `hrms-app-service@newtuple.com` | Internal orchestration only |

Read credentials through an authorized operator from the protected runtime
environment; do not copy them here. Keep emails distinct and the organization
ID stable. No employee records or local demo data are needed for tenant admin
access. Demo accounts such as `demo.superadmin@newtuple.com` are local fixtures,
not production bootstrap identities.

**Not delivered:** the user's proposal that Super Admin should automatically
approve its own business actions. Existing independent-approval guards still
apply to projects, content and performance. Full configuration access does not
mean unrestricted self-approval. A future auto-approval policy must use native
transitions, explicit tenant policy and audit; do not simply skip guards.

Native Users/Roles/invitation screens are exposed, but a complete HR invitation,
email delivery, account activation and first-run setup journey has not been
verified end-to-end in production. Do not describe it as finished onboarding.

## 6. Design decisions to preserve

Use the supplied Newtuple guideline and branded login as the baseline:
cobalt `#0047AB`, system font, light page headings, semibold section headings,
rounded cards, generous but deliberate spacing and Lucide outline icons.
Reuse skin-local `brand.css`, `WorkPanel`, `BrandLogo`, `BrandFooter` and layouts.
Keep authorization and configuration independent of presentation.

- Public information uses cards for Policies, Learning & development, Holiday
  calendar and Careers, replacing the original plain links.
- Shared footer has only the geometric wave: no copyright panel, large blue
  strip or promotional links. Authenticated pages use a compact 48px vector
  `BrandWave`; public pages retain the full-resolution supplied PNG. This fixed
  the jagged/blurry result from compressing a raster into a shallow footer.
- Logo whitespace is cropped by CSS without altering the original image.
  Sidebar branding is smaller beneath the tenant header; public branding remains.
- Login headline is "Everything that connects us. All in one place." Desktop
  top padding was reduced from 76px to 32px, mobile to 24px. "No sign-in needed"
  was removed. The existing supporting paragraph remains.
- Always include loading, retry/error and genuine empty states. Never report
  an API failure as zero pending work.

Original reference files on the original developer's workstation:
`C:/Users/Priyanka/Newtuple/HRMS/Newtuple Design Language Guideline.docx` and
`C:/Users/Priyanka/Newtuple/Brand Assets/`. Portable assets are checked into
`frontend/public/hrms-brand/`; use the repo branding document for handover.

## 7. Local development and validation

Prerequisites: Docker Desktop/Compose and PowerShell for the HRMS scripts;
Node/npm for frontend checks. Core uses FastAPI, SQLAlchemy, Pydantic, PostgreSQL
and uv-managed Python; the HRMS adapter has its own `requirements.txt` and Dockerfile.

From repository root:

```powershell
# Current native HRMS, not the older compatibility runtime
powershell -NoProfile -File scripts/hrms-local.ps1 native-up

# Optional LOCAL demo accounts; credentials remain in ignored local files
powershell -NoProfile -File scripts/hrms-local.ps1 native-demo-users

# Test current source in an isolated image
docker build -t hrms-handover-check applications/hrms_api
docker run --rm hrms-handover-check python -m pytest tests -q -p no:cacheprovider

# Architecture gate (use backend/.venv/Scripts/python.exe if needed on Windows)
python scripts/verify-platform-boundary.py

cd frontend
npm ci
npm run build
```

Local configuration is `.hrms.local.env` (ignored). Local demo credentials are
`.hrms-demo-local/users.json` (ignored). Never use these as production seed data
or deploy their values. The native UI is port 5182; the compatibility runtime
uses 5181. `scripts/hrms-local.ps1 up` starts the older path; use `native-up`.
Generic Makefile port documentation belongs to the generic platform, not this
HRMS composition. Inspect `docker-compose.hrms.yml` for actual mappings.

Additional local smoke actions: `native-test`, `native-performance-test`,
`native-project-test`. Project smoke requires demo users; performance smoke
expects the local employee fixture. These create/retain named test records and
must not be run against production casually. `native-migrate-steps` is the
explicit legacy-step migration job, not part of ordinary startup.

Last relevant validation:

- 89 HRMS tests passed after tenant provisioning and organization endpoint tests.
- Native API provisioning integration ran twice successfully (idempotent rerun).
- Frontend TypeScript/production build passed; CI also builds the frontend image.
- Existing native authentication circular-chunk and large-bundle warnings remain.
- Core boundary check passed again on 2026-10-05 for 1,416 tracked core files.

The backend virtualenv on this workstation lacked `psycopg` for the full HRMS
suite; the adapter Docker image supplies its declared dependencies. Use that
test path rather than mistaking a missing local dependency for a product failure.

## 8. Production, CI/CD and operational isolation

Server: `62.238.103.67` (Hetzner Ubuntu, approximately 2 vCPU / 4 GB RAM).
Three apps share it. Workout owns existing ports 80/443 and its edge Nginx;
legacy HRMS is on 8081; this HRMS uses 8082 and its own web-container Nginx.
Do not modify/reload the other apps' Nginx or run host-wide Docker cleanup.

| Item | Value |
| --- | --- |
| Compose project | `newtuple-hrms-production` |
| Workflow | `.github/workflows/hrms-production.yml` |
| Compose / rollout scripts | `deployment/hrms/compose.yml`, `deployment/hrms/deploy.sh` |
| GitHub deployment environment | `hrms-production` |
| Deploy account | `hrms-deploy` (dedicated SSH key; Docker access) |
| Runtime environment | `/opt/newtuple-hrms/production.env`, mode 600 |
| Releases | `/opt/newtuple-hrms/releases/<full-commit-sha>/` |
| Active release | `/opt/newtuple-hrms/current` symlink |
| Database backups | `/opt/newtuple-hrms/backups/` |

Repository variables: `HRMS_PRODUCTION_ENABLED=true`,
`HRMS_DEPLOY_HOST=62.238.103.67`, `HRMS_DEPLOY_PORT=22`,
`HRMS_DEPLOY_USER=hrms-deploy`.

Repository secrets: `HRMS_DEPLOY_SSH_KEY`, `HRMS_DEPLOY_KNOWN_HOSTS`,
`HRMS_PRODUCTION_ENV_BACKUP` (recovery copy, not read during routine deployment).
Use the `priyanka-newtuple` GitHub identity. The original authorized operator's
SSH key path is `C:/Users/Priyanka/.ssh/hetzner-priyanka-server`; this is not the
CI key and is not a transferable credential. Arrange authorized access separately.

Pipeline on every main push (or manual main dispatch):

1. Verify core boundary; build unchanged platform, HRMS adapter and frontend.
2. Run HRMS tests and frontend type-check/build on the GitHub runner.
3. Save images as a checksummed artifact and transfer via strict-host-verified SSH.
4. Serialize rollout with a lock; use the uniquely named Compose project.
5. Dump both HRMS databases before platform migration/startup.
6. Start platform, run the one-shot installer, start adapter and web; wait healthy.
7. Verify health/login and update the release pointer.

No database/API host ports are exposed in production. Each deployment has its
own network/volumes; memory caps and log rotation limit resource usage. Never
copy local databases to production. GitHub artifacts are retained for seven days.
Releases and backups require an operator retention policy; avoid global prune.

Deployments can briefly interrupt this HRMS. They are not blue/green. The previous
release pointer is retained, but rollback is NOT automatic: assess migration
compatibility before reverting code or restoring both database dumps. Include
uploads, encryption key and secrets in an off-server recovery plan. See the
[complete runbook](deployment/hrms/README.md).

HTTP-only IP access was explicitly chosen temporarily. Domain/TLS, production
SSO and outbound email configuration remain follow-ups. Do not assume visible
Google/Microsoft buttons mean providers are configured.

### Last verified production release

`419374a88077f5f475ca7bc1bd584d0824a2957c`:
[successful workflow run](https://github.com/priyanka-newtuple/sm_hrms/actions/runs/36713210179).
After rollout, served assets were checked for the new headline, removed text
and reduced padding. Responses remained workout `301`, legacy HRMS `200`, new
HRMS login `200`. Tenant admin login, active organization, role `superadmin`,
Settings and module capabilities were verified after the tenant fix deployment.
These checks are not a full visual/end-to-end production regression suite.

Useful read-only operator checks:

```text
gh run list --workflow hrms-production.yml --limit 5
gh run view <run-id> --log-failed
readlink -f /opt/newtuple-hrms/current
docker ps --filter label=com.docker.compose.project=newtuple-hrms-production
```

Use the known successful response baselines for all three apps before/after
rollout. Never print `production.env`, private keys or authentication tokens in logs.

## 9. Important remaining work and caveats

- Super Admin automatic business approval is proposed, not implemented (see §5).
- First-run HR invitation/activation/email delivery needs end-to-end completion.
- Offboarding, timesheets, assets and helpdesk are not delivered modules simply
  because old plans or screenshots mention them.
- Historical performance/project data migration and reconciliation remain open.
  Preserve historical IDs, actors, dates and states; do not fabricate approvals.
- Recovery journal exists, but an operator recovery UI, durable outbox and
  automated reconciliation are outstanding. Recovery snapshots may contain
  sensitive HR data even though the journal is not the master record store.
- Native onboarding tasks were represented as workflow-backed OnboardingStep
  entities because a generic task API permission gap could not be fixed without
  touching core. Do not reintroduce direct core patches.
- Existing enrollments require explicit migration after workflow semantic changes.
- Performance reminders/automatic deadlines, attachments, autosave, reporting,
  360 reviews and automatic allocation-driven feedback are not complete.
- Private content attachments, email notifications and richer calendar editing
  are not implemented by Cockpit.
- Navigation grouping is skin code driven by capabilities; a fully editable
  tenant navigation designer is not implemented.
- Monitoring, backup restore drills, off-server retention, capacity/load tests
  and production security configuration need operational ownership.

## 10. Delivered commit milestones

| Commit | Work |
| --- | --- |
| `4f4ef9ee` | HR Cockpit publishing and configurable project access |
| `4583feaf` | Branding, public information pages and shared footer |
| `50c3400d` | My work redesign and sharper compact footer |
| `c408a895` | Consistent workspace modules, icons and grouped role-aware navigation |
| `b343c9fd` | Isolated main-branch production pipeline |
| `ca5fd329` | Self-hosted tenant Super Admin provisioning and organization Settings |
| `d5e3d578` | Database-backed tenant sidebar header and smaller logo |
| `419374a8` | Latest login headline and spacing |

## 11. Existing documentation and handover hygiene

- [Architecture decisions/migration plan](design_docs/hrms_migration_plan.md)
- [Current application-layer boundary](design_docs/hrms_application_layer.md)
- [Earlier native migration context](design_docs/hrms_native_backend_migration.md)
- [Projects design](design_docs/hrms_projects_design.md) and
  [implemented project behavior](design_docs/hrms_projects_local.md)
- [Performance implementation and limits](design_docs/hrms_performance_management.md)
- [Cockpit implementation and limits](design_docs/hrms_cockpit.md)
- [Local demo accounts](design_docs/hrms_demo_users.md)
- [Production deployment](deployment/hrms/README.md)
- [HRMS branding](frontend/src/skins/hrms_native/components/BRANDING.md)
- [Generic core architecture](design_docs/state_machine.MD)

Some older documents retain earlier test totals, old navigation wording (e.g.
Published information in the sidebar) or historical plans. Use this handover
and current code to distinguish delivered behavior from those snapshots.

At handover, `git status` reports modifications to several original core files,
but their normalized diffs are empty and the core boundary check passes. These
are pre-existing working-tree/line-ending noise observed throughout the session.
Do not bulk-stage, reset or normalize them as part of a feature. Inspect real
diffs, stage explicit paths, and keep unrelated work intact. This handover itself
is documentation only; creating it does not commit, push or deploy anything.
