# Projects: local implementation and testing

The Projects module is available at http://localhost:5182/hrms/projects. It uses the core platform's pipeline table, filters and workflow drawer. Project-specific forms and orchestration are in the HRMS application layer; core source is unchanged.

## Try the demo

The real-platform test leaves **Local Projects Review** with Demo Project Manager as PM, Demo Delivery Manager as DM, and a 50% Demo Employee allocation in February–April 2043. The project and allocation are active. The dates deliberately avoid real staffing periods.

1. Sign in as `demo.delivery-manager@newtuple.com`. Open Projects. You can create customers and projects, submit project requests, and manage allocations.
2. Choose **Add project**. Select an existing customer, or choose **Create customer** beneath the Customer field to create one in the same drawer. Saving selects the new customer automatically; cancelling returns to the preserved project draft. Customer creation requires `customer:create` and is hidden for a configured read-only Customer field. Select a PM, DM, dates and an independent Super Admin approver.
3. Open the new **Project Approval** row and **Submit**. A draft project shell is not yet operational.
4. Sign in as `demo.superadmin@newtuple.com`. Open the request from My Work, Projects or Workflows. Compare current/proposed values and approve, reject or request changes.
5. Sign in as `demo.project-manager@newtuple.com`. Open the approved project and **Request allocation**. Choose an employee, project role, dates and percentage; **Preview capacity** checks actual date intervals. Open the resulting Allocation approval row and submit it.
6. Sign in as the named DM to approve. Capacity is committed only after approval is applied. If the DM created the request, an independent Super Admin must approve it.
7. For amendments, open the project or allocation and propose a change. Approved values remain unchanged while the request is under review. Pending authors can withdraw, edit and resubmit. Decisions use the exact reviewed revision.

Passwords are in the git-ignored `.hrms-demo-local/users.json`. See `hrms_demo_users.md` for a PowerShell clipboard command.

## Current permission policy

| Role | View | Create/manage | Decide requests | Commercial values |
| --- | --- | --- | --- | --- |
| Delivery Manager | All operational projects; own/assigned drafts | All operational projects and allocations | Named DM for allocation requests made by another person | All |
| Project Manager | Assigned projects | Create with self as PM; manage assigned projects/allocations | No default project approval grant | Assigned projects |
| Super Admin | All, including drafts | All | Named independent project approver; DM-originated allocation requests | All |
| HR Full / HR Basic | All operational projects/allocations; approved request history | None | None | Hidden |
| Finance | All operational projects/allocations; approved request history | None | None by default | Visible |
| Office Admin | All operational projects/allocations | None | None | Hidden |
| Employee / Recruiter / Reporting Manager | Projects with their allocations; own allocations | None | None | Hidden |
| Platform Admin / Viewer / Performance Approver | Only employee-linked assignment scope, if any | None | None | Hidden |

Platform Admin is not automatically a business project approver. Adding a read-all role to a PM does not grant manage-all. Draft visibility is limited to the creator, assigned PM and business approvers. Historical requests without an approver need migration before new actions are allowed.

## Native records and workflow stages

- `HRMS.Customer`: customer reference and contact/commercial metadata; creation supported. No standalone CRM UI.
- `HRMS.ProjectRole`: legacy staffing-role records retained for history. New choices come from the native Allocation form Project role picklist, independently of login roles.
- `HRMS.Project`: Draft → Planned → Active → On hold / Completed → Archived. Resume returns an on-hold project to Active.
- `HRMS.ProjectChange`: reused existing request entity; Draft → Pending → Approved / Changes requested / Rejected. Withdrawal returns Pending to Draft; Revise reopens returned/rejected requests.
- `HRMS.Allocation`: Planned → Active → Completed, with approved cancellation/release preserving history.
- `HRMS.AllocationChange`: initial, amendment and release requests, with the same independent approval lifecycle.

The installer adds missing fields, a v2 ProjectChange form, and publishes an additive workflow version for withdrawal. It preserves the existing workflow definition's configuration. Previous enrollments remain pinned; it does not fabricate migrated approvals or reset their state.

## Application boundary and API

`applications/hrms_api/hrms_app/projects.py` composes native public HTTP APIs for data, enrollment and transitions. Product permissions are in `role_capabilities.json`; schemas/workflows are in `project_catalog.py`; inputs are in `project_contracts.py`. `frontend/src/skins/hrms_native/pages/ProjectsPage.tsx` provides forms/details/inbox and the existing HRMS Workflows page reuses native table components.

- `GET /hrms/projects`: scope-filtered projects, requests and allocations; commercial filtering includes proposals.
- `GET /hrms/projects/options`: authorized reference choices.
- `POST /hrms/projects/actions`: customer/project creation.
- `POST /hrms/projects/{entity_id}/actions`: version-checked request decisions and operational transitions.
- `POST /hrms/projects/{project_id}/capacity`: aggregate dated capacity preview. Optional `allocation_id` excludes the allocation being amended and is checked against the project.
- `GET /hrms/projects/pending-actions`: the current actor's recoverable operations.
- Existing `GET /hrms/workflows`: also projects/allocations and their approval requests.

Only the necessary native entity/field/workflow permissions are granted to the internal service identity. Browser calls cannot directly mutate native entities. No second project master or platform-table access was introduced.

All writes use the application-owned tenant lock and durable journal. A partial project operation blocks subsequent project mutations until resumed with its original key. The UI offers Resume operation. Record markers prevent duplicate creation after retries; an uncertain create without a discoverable record requires explicit reconciliation. The human actor and operation key are audited and attached to transition inputs. This is a recoverable sequence of public API calls, not a distributed transaction. Direct native administrative writes require controlled reconciliation.

## Business checks and integration

Allocations require an approved planned/active project, active employee, valid staffing role, dates within the project and no same-employee/same-project overlap. Planned and active allocations consume capacity. Over 100% requires a reason and independent approval; final decisions recalculate capacity. Proposed requests do not reserve capacity. Closing a project requires live allocations to be completed/released and pending allocation requests to be resolved.

Successful allocation approval also completes onboarding step 8 when that employee has a ready step and the approver is authorized to complete it. Dependencies and owner permissions remain enforced; otherwise the step remains in My Work. Release cancels the allocation's whole interval; use an approved amendment to shorten dates while preserving an earlier interval.

Existing timesheet validation, automatic project-reviewer selection for performance, legacy data import/reconciliation, reporting/exports and a full customer-management UI are follow-on integration work. This module does not claim those features or a production data migration are complete.

## Verification

```powershell
./scripts/hrms-local.ps1 native-up
./scripts/hrms-local.ps1 native-project-test
```

The local test reads demo credentials without printing them and saves repeatable test request bodies in `.hrms-demo-local/projects-smoke.json`. It checks native project/allocation approvals and replay, workflow withdrawal/resubmission, commercial-field filtering, employee scope, self-approval denial, overlap rejection and operational start transitions.

Unit tests cover permission combinations, tenant boundaries, interval capacity, stale versions, approval-time capacity rechecks, operational stages/date bounds, release, onboarding integration and failure after an approval transition with retry recovery. Core integrity is checked with `python scripts/verify-platform-boundary.py`.


## Configurable allocation access

Projects is a directory with one row per project. Open **View details → Add allocation** to draft a staffing request. Submit and review the resulting request in **Workflows**. Allocations become committed only after independent approval. The action is available for approved planned/active projects where the user can manage staffing.

Super Admin can change these permissions in **Settings → Roles → Project and allocation access**. Defaults allow assigned Project Managers, Delivery Managers and Super Admin to request allocations. Existing read-only scopes for other roles are preserved. A user needs `project:view`, a project management scope, and `allocation:request`; multiple roles combine. Management of assigned projects still requires the actor to be the project's PM. Approval requires the designated independent approver and the applicable management/approval permission.

GET/PUT `/hrms/settings/project-access` manage tenant-scoped overrides in the HRMS application's own database. Saves are audited and revision checked. Native roles are the role catalog, fetched with the configuring user's token. Overrides affect only project capabilities; they cannot grant platform configuration or HR permissions. The API rechecks policy on each authenticated request. Browser menus refresh on navigation/refocus; refreshing the page also picks up a changed policy. Native state-machine code, workflow execution and core database tables are unchanged.


## Project role picklist

The allocation Project role dropdown reads every value and label from the native
`HRMS.Allocation` form (`hrms_allocation_form_v1`), field `project_role_id`.
As a tenant Super Admin, open native **Settings > Forms**, edit **Allocation form**,
and configure the **Project role** field picklist. Maintain its options through
**Settings > Fields > Picklists** (initial name: **HRMS Project roles**).
The application refreshes the choices when reopened/refocused or when a form save
broadcasts a change. Server validation reads the current list for allocation
requests, amendments, capacity previews and approval. Removed values cannot be
used for new or approved allocations; existing allocation history retains its
saved role label. Labels can change independently of stable option values.

The installer attaches a native picklist through public platform APIs. Its six
initial roles are Project Manager, Engineer, QA Engineer, Designer, Business
Analyst and Consultant. On first migration, it also includes all legacy project
roles, preserving their IDs as static values so existing drafts continue to work.
New options may use ordinary string values; no ProjectRole record is required.
Existing picklist bindings and configured enum choices are preserved, and later
installs do not re-add deliberately removed options or reset a tenant's list.

Run the regular HRMS installation, or run the targeted migration with the same
installer environment: `python -m hrms_app.install_project_roles`. Deploy this
configuration migration together with the API/UI change. An empty list remains
empty with guidance in the form; a missing/inactive form produces an error.
