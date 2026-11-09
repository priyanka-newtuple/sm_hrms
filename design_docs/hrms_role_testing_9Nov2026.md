# HRMS role permission testing and defect fixing — 9 Nov 2026

Scope: HR Full, Office Admin, Employee, Project Manager and Delivery Manager.
Environment: **local only** (`localhost:5182`) on `main` at `ca467e34` plus the
fixes below, using the ignored demo accounts in `.hrms-demo-local/`. Local
databases were backed up before testing. Production was not touched.

## Principles every test and fix respects

1. Native entities, fields, forms, workflows, states, transitions and role grants
   are the system of record. A Settings change must change app behaviour without
   a code change or redeploy.
2. HRMS capabilities come from native effective grants (`policy.py`); record and
   field visibility come from native Entity Access and field permissions.
3. The HRMS layer never imports core code or reads platform tables; the core
   boundary check passes. No native core source changed.
4. Human actions run with the human's token so native permissions decide; only
   HRMS-internal bookkeeping uses the service identity.
5. Tenant scoping and independent-approval guards stay intact.
6. Each fix removes the dead or duplicate code it touches and adds a regression test.

## Method

Per role, as a human tester would: probe capabilities, native grants and every
HRMS read endpoint; run the role's real flows with disposable records; try
actions outside the role (UI hidden **and** API refused); then, as Super Admin,
change grants/fields/capabilities through the Settings configuration gateway and
confirm the role's UI and API follow, then restore. Browser spot checks confirmed
the Office Admin and Project Manager menus and pages.

## Results

| Suite | Cases | Result |
| --- | --- | --- |
| Office Admin asset flow (add, validate, edit, issue, employee view, archive, negatives) | 16 | 16 pass |
| PM / DM / approver project & allocation flow (customer, project approval, both allocation routes, capacity, visibility, commercial privacy) | 33 | 33 pass |
| HR Full + leaver offboarding (start, employee checklist, clearance, departure/access removal, completion, privacy) | 21 | 21 pass |
| Employee self service (leave, WFH) + HR WFH policy/decision | 12 | 12 pass |
| Settings reflection (entity grant, field hidden, field view-only, HRMS capability, entity view) | 8 | 8 pass |
| HRMS unit tests / deployment tests | 757 / 35 | pass (one pre-existing flaky cockpit test, see below) |

Expected visibility confirmed: Employee sees only projects they are allocated to;
Office Admin and HR Full see operational projects without commercial values;
PM sees assigned projects and own drafts; DM and Super Admin see all.

## Defects fixed

| ID | Sev | Area | Defect | Fix |
| --- | --- | --- | --- | --- |
| D1 | P2 | All forms | `/hrms/forms/*` ignored native field permissions: hidden fields shown and view-only fields editable. | `policy.field_access()` mirrors native rules (system role bypass; no grants = no fields; view/edit/mask). Used by forms and offboarding; offboarding's duplicate `visible_fields` (role-name bypass + extra call) removed. Field grants now travel on the session `Actor`. |
| D2 | P1 | Create (assets, projects, cockpit, performance, WFH) | Creating a record required a human field grant on HRMS's internal `hrms_operation_key`; Office Admin could not add assets. | `PlatformClient.create_record` creates with the human token without the marker; the service identity writes the marker. |
| D3 | P1 | Assets | A definitively rejected create left a reservation that blocked **every** asset operation in the tenant. | Release the reservation on definite (4xx) rejection; uncertain outcomes stay reserved. |
| D4 | P2 | Record panel | Asset/offboarding records showed no state and no Archive (delete) control despite native delete grant. | Metadata resolves the entity type from the native record and reads grants from the session. |
| D5 | P2 | Assets | An employee saw their issued assets only if they could read the whole employee directory. | Resolve the account's own profile via the service, as leave does. |
| D6 | P1 | Allocations | Every allocation approval failed: it completed a step in the retired legacy Onboarding Case workflow. | Removed the coupling and the whole dead legacy case/step onboarding code (`onboarding_template.py`, 12 service methods, models, platform helpers, 15 tests of deleted code). |
| D7 | P1 | Offboarding | Departure/HRMS access removal raised `TypeError` (missing `token`) since PR #42 — offboarding could not complete. Test mock hid it. | Pass the acting human's token; mock now enforces the real signature. |
| D8 | P3 | Local stack | Offboarding could not start locally: `hrms-app` had no public address. | `HRMS_PUBLIC_URL` default for the local compose service. |
| D9 | P3 | Offboarding | A field shared by two forms of one state rendered twice. | De-duplicate state fields. |
| D10 | P1 | Offboarding | "Your offboarding" list returned 403 for everyone once any other case existed: the service lacked `entity_record:read` (installer spec dropped it). | Service role spec includes `entity_record:read` and `email_template:read`. |
| D11 | P1 | WFH | Same class as D3: a rejected first write blocked every WFH operation. | `Operation.release()`; release on definite rejection of the first write. |
| D12 | P1 | Projects | Same class: a rejected first step blocked every project operation ("needs recovery" forever). | Step body extracted to `_apply_step`; release on definite rejection of step 0 (lost creates stay reserved). |
| D13 | P2 | WFH | Updating an existing WFH policy always failed ("Not on the configured form: identifier"). | Exclude the platform-generated identifier; updates keep the creation marker. |
| D14 | P2 | WFH | A policy in draft (e.g. created in Settings) could never be activated from the app. | Saving activates a policy still in draft. |

## Role configuration (native Settings), applied locally

The app correctly reflected whatever Settings held; most "access" failures were
roles missing native grants. The installer seeds only HRMS capability keys, never
Entity Access, so on a fresh tenant these must be configured in Settings → Roles.
Applied locally as an admin would (not to production):

| Role | Native grants added |
| --- | --- |
| Office Admin | `entity_record:read`, `form:read`; Asset fields view/edit; Asset workflow + issue; read-only Customer/Project/Allocation (non-commercial fields) |
| Employee | `entity_record:read/write`, `form:read`, comments/files; own-asset fields (view); Leave and WFH request create/edit + cancel transitions; read-only project family |
| Project Manager / Delivery Manager | record/workflow/form/comment/file catalog keys; Customer, Project, ProjectChange, Allocation, AllocationChange view/create/edit + fields + all their transitions; Employee view (name/designation/status fields) |
| HR Full | `user:read`, `user:write`; restored `wfh:view/request/approve`, `performance:manage`; WFH policy fields + activation; read-only project family |

## Observations (not changed)

- **Production roles:** `hrms_manager` no longer exists and Office Admin has no
  offboarding access in production (preserved by the 9 Nov release). Production's
  staged offboarding therefore relies on HR / Super Admin for project-release and
  asset-clearance stages.
- **Docs:** `hrms_projects_local.md` says a PM's allocation request goes to the DM;
  since `e375eb07` the code routes other requesters to the project's PM and the
  PM's own request to an independent `project:approve` holder. The doc is stale.
- **Draft visibility:** a DM named on a PM's draft project does not see it (code
  limits drafts to creator, PM and approver).
- **Hard-coded business values:** offboarding clearance statuses and project state
  action maps (including a dead `planned` project state) are in code, so renaming
  them in Settings would not be reflected.
- **Local/production parity:** local `install.py` does not run the post-install
  steps `deploy.sh` runs (notifications, onboarding bridge/routing/assets, email).
- **Tooling:** `tools/seed_demo_users.py` asserts the pre-PR #42 capability lists
  and fails after creating profiles.
- **UI:** the Projects page hero text wraps one word per line at ~800px width.
- **Flaky test:** `test_cockpit.py::test_revision_keeps_previous_publication_…`
  fails intermittently on unmodified `main` too.

## Agent Feedback

- Started: 9 Nov 2026
- Completed: 9 Nov 2026
- Notes: Local demo memberships were suspended and demo employee profiles were
  missing; both were restored through native APIs / the demo seeder. A stale local
  Asset workflow draft (version 0) was archived so the installer could run. Test
  records were created with `QA` names; one QA offboarding case was archived.
