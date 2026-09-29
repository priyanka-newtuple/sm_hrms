# HRMS migration onto the state machine platform

> **Architecture update — 2026-09-28:** The current implementation uses a separate HRMS application layer over public platform APIs. Core source has been restored to the original baseline. Earlier entries below describing in-core HRMS adapters, direct model/service access, native task writes, or the retired import/demo commands are historical and superseded by [the current architecture](hrms_application_layer.md). Employee/onboarding/leave slices are migrated; full legacy feature parity remains outstanding.

Date: 2026-09-24  
Status: Updated after inspecting the local legacy source; implementation in progress on `fix/hrms-foundation`.  
Scope: Full legacy feature parity for the first local review, as requested after the initial plan.

## Implementation addendum — full legacy parity

The local source at `C:\Users\Priyanka\Newtuple\HRMS` was discovered after the first plan. It includes all of the following signed-in modules, and the first release must preserve their behavior:

| Module | Source functionality and rules to retain | Platform integration path |
| --- | --- | --- |
| Identity, roles, directory and profile | Google sign-in, local demo personas, role feature permissions, record scopes, employee fields and documents | Preserve the authorization service while mapping identity to the platform tenant; retire duplicate login only after an authenticated bridge is tested |
| Customers, projects, project approvals and allocations | Customer/project records, manager visibility, approval gates and overbooking rules | Version project approval states with the shared evaluator; retain constrained relational data where generic records cannot express booking rules |
| Timesheets, holidays and leave | Daily/weekly entry, holiday/leave calculations, manager approval and row locks | Version timesheet states with the shared evaluator; retain transactional line and calendar storage |
| Onboarding and offboarding | Configurable templates, task dependencies, invitations, documents, assets and allocations | Use the shared evaluator for record/task lifecycle; retain legacy orchestration until each side effect has a tested platform adapter |
| Performance | Cycles, goals, reviews, calibration, publication and acknowledgements | Migrate workflow definitions and use existing role-scoped rules; preserve the existing presentation |
| Assets, helpdesk and work inbox | Assignment, tickets, status transitions and cross-module action queue | Reuse platform task/notification primitives after matching existing access semantics |
| HR cockpit and public content | Policies, openings/referrals, learning events, holidays and travel form | Reuse skin extension and public routes; preserve publish/approval behavior and public field projection |

### Compatibility boundary

The first integration keeps the legacy relational HRMS domain in `backend/hrms/` and the corresponding frontend in `frontend/src/skins/hrms/`. This preserves full user journeys while allowing the product to run from this repository. The shared platform workflow evaluator validates declared HRMS state changes. Authentication, role scope, notification orchestration and rich domain tables remain in the HRMS package for this release. This is a staged migration, not a claim that every HRMS feature already uses generic entity storage or the platform's workflow persistence and RBAC implementation.

The HRMS Docker Compose project has its own database volume and loopback ports. It never imports the running legacy database. Its local demo sign-in is explicitly enabled for local development and rejected in staging/production. The HRMS compatibility deployment is scoped to one configured organization; extending it to multi-tenant serving requires database-level tenant foreign keys, platform membership checks and migration of the remaining domain services before production.

### First-release exit gates

1. The new Compose stack builds and serves its own web/API/database without port or volume overlap with the legacy stack.
2. Existing legacy backend tests run against only `sm_hrms_test`; the test fixture refuses other database names.
3. Employee, manager, Finance and HR journeys work through the new local URL, including the signed-in modules above and public routes.
4. Shared platform frontend still builds in its default skin, while `VITE_SKIN_ID=newtuple-hrms` loads the HRMS product shell.
5. Workflow transition checks, org scoping and local-auth restrictions have dedicated regression tests.
6. Production readiness is evaluated separately: replace duplicate identity, validate per-tenant row/relationship isolation, migration mapping and notification delivery before accepting live employee data.

## Recommendation

Build HRMS as a product skin plus tenant configuration on the existing platform. Reuse authentication, entities, relations, forms, workflow execution, tasks, audit, notifications, file handling, and administrative screens. Add an employee-oriented frontend and narrowly scoped backend extensions where HR rules require them.

Do not translate every HRMS screen into a workflow board. Calendars, employee profiles, and timesheet entry need appropriate interfaces; approval lifecycles can still use the common workflow engine underneath. Keep the platform's workflow and configuration tools available to authorized administrators.

## 1. Evidence and boundaries

### Deployed application inspected

Source: https://62-238-103-67.sslip.io/ . The root redirects to a Newtuple account login. The following pages were inspected without signing in:

| Surface | Observed behavior | Migration implication |
| --- | --- | --- |
| Login | Newtuple branding and Google/Newtuple account sign-in | Reuse platform Google OAuth, reconcile identities and org membership |
| Organization Policies | Public published-policy listing; no published policies visible | Configurable policy records and a dedicated reading page |
| Travel Request | Public form; sign-in required to submit; full name, work email, origin, destination, start/end dates, trip type and purpose | Reuse forms and transitions; employee identity must be derived or verified server-side |
| Travel guidance | Page says manager and Finance review requests | Proposed two-stage approval; actual order and exceptions require confirmation |
| Open Positions / Referrals | Public openings plus a referral form; sign-in required to refer | Reuse ATS Job/Candidate/Application where their schemas fit; preserve referrer relationship |
| L&D calendar | Month navigation, search, month filter and calendar grid | Reuse event records and create a calendar presentation |
| Holiday calendar | Year selector; date, holiday, location and type columns; page says holidays are used by timesheets | Shared holiday data; inspect timesheet calculation rules before migration |
| Tiffin Tuple / Templates | Links to another app and Google Drive | Preserve normal links initially; migrating those applications is outside initial scope |

The signed-in dashboard, employee/manager/admin screens, source database, API implementation, and approval rules have not been inspected. Timesheets are referenced by visible copy, but their behavior is unverified. Leave, attendance, payroll, expenses, onboarding, and performance management must not be assumed to exist or included as committed scope without discovery.

### Platform evidence

Paths below are relative to this repository.

| Evidence | What it enables or constrains |
| --- | --- |
| `frontend/src/skins/registry.ts`, `frontend/src/skins/types.ts` | Customer skin injection, branding, navigation, custom pages, component overrides and a custom home route |
| `frontend/src/App.tsx` | Skin custom pages are currently mounted inside the protected layout; anonymous HRMS pages need a deliberate extension |
| `frontend/src/core/componentRegistry/types.ts` | Existing login, sidebar, topbar, entity detail and list view override slots |
| `frontend/src/pages/records/detail/components/` | Existing entity tables and schema-driven create/edit controls |
| `frontend/src/core/services/`, `core/hooks/`, `core/queryClient.ts` | Shared API/auth and server-data infrastructure; reuse rather than adding a second client |
| `backend/entities/`, `forms/`, `workflow/`, `tasks/` | Generic records, relations, forms, lifecycle execution, tasks and event history |
| `backend/roles/models/interface.py`, `backend/roles/manager.py` | Entity condition values currently accept `LITERAL` only; dynamic self/team permissions are a gap to design and verify |
| `backend/workflow/models/interface.py` | Current guard enum covers presence, equality, numeric comparisons and date comparisons; do not assume richer policy/relationship guards mentioned in older docs are implemented |
| `backend/workflow/manager.py` | Existing transition idempotency handling to reuse and test for HR approvals |
| `backend/bulk_import/` | Existing import infrastructure to evaluate; not yet proven to preserve legacy history or exact migration semantics |
| `backend/auth/manager.py` | Google OAuth support already exists |

This is a targeted code review, not a full security or runtime audit. Some local architecture notes refer to old folder structures; use current code and the repository's root instructions when implementation starts. New server-data hooks should follow the current TanStack Query convention; Zustand is for client interaction state.

## 2. Target architecture and reuse boundaries

1. **HRMS presentation:** a `newtuple-hrms` skin, employee home, My Requests, manager approvals, profiles and calendars. Reuse existing controls, layout slots, query infrastructure and form rendering.
2. **HRMS configuration:** versioned entity schemas, relations, forms, workflows, role permissions, views and notification templates installed idempotently per organization.
3. **Shared platform:** existing authentication, authorization foundations, workflow runtime, records, audit, documents and tasks remain the common foundation.
4. **Targeted domain services:** add backend logic only for rules that configuration cannot safely express, such as manager resolution, self-approval prevention, or time calculations if confirmed in scope.

Keep an Employee business record distinct from an authenticated User account. Link them within an organization using stable IDs; an employee may exist before receiving a login. Do not use email as the permanent join key or create a second authentication system.

Prefer generic entity records for configurable HR master data and requests. For high-volume timesheet lines or transactional balances, first assess constraints, indexing, reporting and concurrency; dedicated relational tables may be justified. No new schema-per-entity migrations are needed merely to add configurable record types.

## 3. Proposed feature mapping

Entity names are proposals, not declarations that these schemas already exist.

| Feature | Configuration and reuse | New work / decision |
| --- | --- | --- |
| Employee foundation | `HRMS.Employee`, `HRMS.Department`, location and manager relations; existing user accounts | Identity mapping, self/team authorization; profile UI once source behavior is known |
| Policies | `HRMS.Policy`, file/document references, publication status | Reading page and public-safe response; add acknowledgement tracking only if required |
| Travel | `HRMS.TravelRequest`, schema-driven form, workflow tasks, notifications and audit | Employee request page and manager/Finance inbox; approval eligibility checks |
| Referrals | Reuse compatible ATS records; add referral attribution or `HRMS.Referral` if it has its own lifecycle | Employee-facing open jobs/referral page; duplicate handling and restricted candidate visibility |
| L&D | `HRMS.LearningSession` and configured admin forms | Calendar UI; enrolment/attendance only if the current app requires them |
| Holidays | `HRMS.Holiday`, date/location/type and publication metadata | Calendar/list UI; rules for location-specific dates and timesheet use |
| Timesheets, if confirmed | Shared users, projects if applicable, holidays, approval workflow and audit | Weekly grid, entry validation, totals, locking and reporting; storage decision after source review |
| Other HR modules | Assess each against records/forms/workflows first | No payroll/leave/attendance scope or schedule assumed yet |

## 4. Frontend plan

### Preserve the HRMS experience

- Match the observed Newtuple branding, horizontal navigation, blue accents, rounded content panels and page headings through skin/theme configuration and existing slots.
- Set the skin home route to an employee landing page, rather than exposing Workflows as the employee's default screen.
- Offer role-appropriate navigation: employees see their work; managers see approvals; HR administrators see management/configuration screens. Hiding navigation is not authorization.
- Keep the public policies, travel information, openings, L&D and holiday routes if that access model is intentional. Submission remains authenticated.
- Keep ordinary external links to Templates and Tiffin Tuple. Do not forward platform session tokens to these destinations; audit the existing skin `externalUrl` behavior before reusing it because its type documentation describes token forwarding.

### Reuse before building

Use existing entity form controls for travel/referral fields, shared tables for administrative lists, existing file components for attachments, and the workflow history UI where appropriate. Extract reusable pieces only when a custom page cannot compose the existing controls cleanly.

Likely custom pages: HRMS home, My Requests, Approval Inbox, policy reader, learning calendar, holiday page and employee profile. A timesheet grid is conditional on discovery. Employee approvals should be clear actions on a request, with any required reason fields; users need not understand the platform's workflow-builder terminology.

### Planned code locations

- `frontend/src/skins/hrms/`: new manifest, branding and skin-owned presentation; register via the existing customer-skin mechanism where practical.
- `frontend/src/pages/hrms/`: route-level pages.
- `frontend/src/core/hooks/`, `core/services/`, `core/types/`, `core/stores/`: hooks, typed API adapters and client state following existing conventions.
- `frontend/src/App.tsx` and `skins/types.ts`: small generic public-route extension only if retaining anonymous pages; protected custom pages already have an extension point.
- Existing shared components: modify only for a demonstrated reusable capability, with regression coverage for the default skin.

Confirm exact paths and reuse boundaries during implementation. Avoid replacing the shared layout or copying the old app's entire frontend before reviewing its source and dependencies.

## 5. Authorization and workflow design

Resolve this before loading employee data. Tenant isolation alone does not prevent employees in the same organization from reading each other's HR records.

| Actor | Proposed scope to validate with HR |
| --- | --- |
| Anonymous | Only explicitly published, safe policy/job/calendar fields |
| Employee | Own permitted profile fields and requests; approved public/shared content |
| Manager | Requests assigned to them and approved team data; not all employees |
| HR administrator | Authorized HR records and configuration within their organization |
| Finance reviewer | Travel/financial review fields relevant to their assigned work |

Extend the shared authorization policy layer with trusted actor/employee context and explicit relationship scope, or provide a narrowly scoped HRMS service that enforces equivalent rules. Prefer one reusable policy path over per-page endpoint exceptions. A client-supplied employee ID or filter must never establish access.

Apply policy consistently to list/detail, search, counts, exports, relations, attachments, tasks, comments, notifications and workflow transitions. Retain field-level restrictions and verify indirect access through agents/MCP and dashboards. Every tenant-data query still requires organization scoping.

**Proposed travel lifecycle, subject to source verification:**

`Draft -> Manager Review -> Finance Review -> Approved`

Add Reject, Return for Changes and Cancel only with agreed semantics. Define whether edits invalidate approvals, who can cancel at each step, who replaces an absent manager, and whether the approving manager is captured at submission or resolved dynamically. Capture acting user, reason, timestamps and the policy/workflow version.

Server-side checks must cover date order, authenticated ownership, active employee status where required, assigned approver eligibility and no self-approval. Simple field/date checks can reuse existing guards. Relationship and policy checks require verified backend support; they are not currently justified as configuration-only features by the inspected guard enum.

Reuse transition concurrency and idempotency mechanisms. Ensure repeated submissions/approvals do not create duplicate tasks or notifications. Test atomic state changes and retry behavior before claiming end-to-end guarantees.

## 6. Configuration installation

Create a versioned HRMS configuration package and an explicit organization-scoped installer. Install in dependency order: entity types, relations, forms, workflow definitions, roles/permissions, views and notification templates.

The installer must support dry-run, detect existing versions, be safe to rerun, and avoid overwriting tenant edits silently. Keep business configuration separate from Alembic structural migrations. Add actual database migrations only where schema constraints or platform capabilities require them, following the migration guidelines and current head at implementation time.

## 7. Delivery sequence and acceptance gates

| Phase | Deliverable | Exit criteria |
| --- | --- | --- |
| 0. Complete discovery | Signed-in employee/manager/admin inventory; source/API/schema review; current-rule and parity matrix | Every current feature classified as migrate, retain externally, defer or retire; unresolved rules assigned for decision |
| 1. HRMS foundation | Skin skeleton, identity mapping, config installer, authorization design and implementation | Employee and manager scopes proven through API tests; default platform skin still works |
| 2. Travel pilot | Request form, My Requests, manager/Finance approvals, notifications and audit | One complete employee-to-reviewer scenario passes, including denial, retry and concurrent-action cases |
| 3. Portal parity | Policies, holidays, L&D, referrals and external links | Match agreed fields, access rules, publication behavior and responsive layouts |
| 4. Remaining authenticated modules | Timesheets and any other confirmed modules | Source behavior and calculations match; no unapproved additions to scope |
| 5. Migration rehearsal | Repeatable import and reconciliation report in staging | Counts, relationships, workflow states, documents and selected histories reconcile; second run creates no duplicates |
| 6. Pilot and cutover | Representative employee/manager/HR pilot; production migration and rollback runbook | HR acceptance, permissions review, restore test and operational checks complete |

Travel is the proposed first workflow because its fields and reviewer roles are visible and it exercises the platform's key reusable capabilities. If signed-in discovery identifies a more critical feature, reorder the pilot before implementation. Do not assign firm dates or reuse percentages until source scope is verified.

## 8. Data migration and cutover

1. Inventory source tables, stable keys, relationships, file storage, approval history, identities and integrations. Agree timezone/date handling and the actual organization/location model.
2. Produce a field/status mapping. Preserve source system and source IDs with an organization-scoped uniqueness rule or mapping table. Map users, employees and managers first, then reference data, business records, files and history.
3. Use deterministic migration scripts with checkpoints, validation and explicit failures. Evaluate existing bulk import for suitable record types; do not use probabilistic extraction as the authoritative migration path.
4. Preserve original timestamps, actors and legacy states as provenance. Do not fabricate platform transition history by replaying approvals. Import current workflow state through a controlled path that suppresses operational notifications/tasks unless deliberately required.
5. Reconcile source/target counts by type and state, orphan relations, required fields, attachments and relevant totals. Sample complete histories with HR. Test reruns and partial failures.
6. Rehearse on staging, then pilot with an explicit source of truth for each migrated module. Avoid uncontrolled dual writes.
7. At cutover, freeze writes or use a verified incremental migration, take backups, import the final delta, reconcile, update OAuth callback configuration and routing, and switch traffic. Keep the legacy app read-only for an agreed period.
8. Define rollback thresholds and ownership. Before new writes, rollback can restore routing to the old app. After new writes, reconcile/export those records before switching back; restoring an old snapshot alone would lose work.

The copied GitHub deployment workflows refer to the original platform environments. Review them and create HRMS-specific staging/production configuration before merging into a deployment branch. The earlier code import did not establish an HRMS deployment pipeline.

## 9. Verification

- Backend: architecture constraints, cross-organization isolation, same-organization self/team scope, field restrictions, forged owner IDs, self-approval, delegated access if required, public publication filters and file access.
- Workflow: happy path, rejected/returned requests, edits after submission, repeated actions, concurrent approvals, task/notification retry behavior and complete audit attribution.
- Frontend: type/build checks and Playwright journeys for employee, manager, Finance and HR; direct-route access; default-skin regression; mobile layouts and keyboard use.
- Migration: dry-run, idempotent rerun, interrupted batch recovery, state/history mapping and attachment reconciliation.
- Performance: test realistic record volumes and team/calendar queries before choosing indexes or specialized storage.

## 10. Decisions needed to finalize the plan

1. Access to the authenticated app and the old HRMS source repository or local folder; representative employee, manager and HR views.
2. Which existing modules are mandatory for the first release, especially timesheets and any features hidden behind login?
3. Preserve the existing look closely, or keep branding/navigation and adapt to platform components? Proposed default: preserve familiar navigation and key interactions, reuse platform controls.
4. Must every current public page remain anonymous, and which records/fields may be published?
5. Actual travel approval order, manager hierarchy, delegation, Finance scope and edit/cancellation rules.
6. Data volumes, history retention, file locations, integrations and acceptable write-freeze window.

## Local implementation status (2026-09-24)

The HRMS backend and frontend are now present in this repository on `fix/hrms-foundation`. The isolated Docker stack builds and runs on `http://localhost:5181`, with a dedicated API and database. Legacy backend tests (99) pass against `sm_hrms_test`, and the frontend production build passes. Local seeded role login, `/auth/me`, and the HR cockpit dashboard were smoke-tested through the new web URL.

These checks establish a local review build, not completion of the production gates above. In particular, the compatibility service retains separate HRMS authentication and domain persistence. Platform identity/RBAC integration, database-enforced cross-tenant relationships, source-data migration rehearsal, and full browser journey validation remain open. The earlier sections describe the original target design; the implementation addendum documents the compatibility path chosen to satisfy full legacy parity first.

## Native-backend correction (2026-09-24)

The product goal is for platform entities, form schemas, fields, published state machines, transitions and approval permissions to own HRMS records. The compatibility backend is only a parity reference and temporary preview. The table-by-table migration design is in [hrms_native_backend_migration.md](hrms_native_backend_migration.md).

An isolated native platform stack now runs on port 5182 (UI) and 8012 (API). Its installer uses the actual platform entity, forms and workflow managers to publish v1 definitions for Leave Request, Timesheet Entry, Project Change and Job Opening. The installer reruns without overwriting tenant edits. These definitions are present in the platform database, but the HRMS UI at port 5181 still writes to the compatibility backend; approval actors, relations, remaining modules and data cutover have not yet moved. Do not describe this stage as completed backend migration.

## Application-layer performance implementation (2026-09-28)

New performance cycles, goals, reviews and project feedback now use native entity/form/workflow configurations through the separate HRMS application API. The core platform source remains unchanged. The application enforces author/approver separation, assigned managers, 100% goal weights, publication privacy, returns, audited reassignment and resumable operations. The frontend includes Performance plus permitted detail actions in the reused core workflow table.

See [hrms_performance_management.md](hrms_performance_management.md) for architecture, APIs and the local walkthrough. This does not import historical performance records or complete full legacy parity. Allocation-driven feedback and remaining modules still require migration; current project feedback uses explicit manager selection of project reference and reviewer.

## Application-layer projects implementation (2026-09-28)

Projects and allocations now use native entities and workflow transitions through the separate HRMS API. The local UI reuses the core pipeline table with project details, customer creation, named approvers, staged amendments, capacity previews, release requests and My Work approvals. PM, DM and independent Super Admin scope is enforced separately from commercial-field access. Tenant locking, record revisions and resumable journal operations protect approval/application sequences. Eligible allocation approvals complete the ready onboarding allocation step.

See [hrms_projects_local.md](hrms_projects_local.md) for the local walkthrough and exact policy. Legacy project/allocation imports, timesheet eligibility integration, automatic performance reviewer selection, exports and full customer-management remain follow-on work. No original core platform files were changed.
