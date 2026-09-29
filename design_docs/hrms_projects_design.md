# Projects and allocations: proposed native-platform design

Original design: 2026-09-28. The project/allocation runtime is now implemented locally; see [hrms_projects_local.md](hrms_projects_local.md) for the delivered scope, approval policy and remaining integrations. The evidence below records the pre-implementation baseline.

## Evidence and current installation

Reviewed the legacy permission matrix, scope filters, serializers, project service, project approval service, allocation service/capacity calculation, models and approval tests. These describe the checked-in default policy, not an audit of per-user grants in the legacy production deployment.

The local native entity-type API currently lists Employee, JobOpening, LeaveRequest, OnboardingCase, OnboardingStep, PerformanceCycle, PerformanceGoal, PerformanceReview, ProjectChange, ProjectFeedback and TimesheetEntry under HRMS. Customer, Project and Allocation are not installed. ProjectChange already contains project_id, requested_by_id, kind=initial/amendment, proposed and note, with draft/pending/changes_requested/rejected/approved workflow states. Configuration presence is not implementation: the runtime service role currently excludes ProjectChange and TimesheetEntry, and the product capability map has no Projects/Allocations permissions or dedicated project-manager role.

## Legacy policy

| Role | Projects | Allocations | Project approval |
| --- | --- | --- | --- |
| Super Admin | All; create/manage | All; create/manage | Yes; direct creation is auto-approved in legacy |
| Delivery Manager | All; create/edit/submit | All; create/edit | No by default |
| Project Manager | Create with self as PM; manage assigned projects | Manage allocations on managed projects | No by default |
| HR Full / HR Basic | Read operational projects across organization | Read across organization | No |
| Finance | Read across organization; commercial field grants | Read; billing-rate access | No |
| Office Admin | Basic read across organization | Basic read across organization | No |
| Employee / Recruiter | Assigned projects | Own allocations | No |

Draft projects are further restricted to owners and project approvers. Manage expands to view/create/edit, not approve. Scope and commercial fields must be checked independently. PM has billing rate, customer contract value, project revenue and margin grants within their scope; Delivery Manager, Finance and Super Admin have broader commercial access. HR compensation access does not confer project-commercial access.

Legacy project amendments preserve live approved values until decision. Submitted requests cannot be edited without withdrawal. Self-approval of submitted requests is forbidden; Super Admin direct creation is a separate explicit exception. Approval rechecks date bounds against committed allocations.

Legacy allocations have no approval queue. Authorized PM/DM/Super Admin writes save directly. Planned and active allocations consume capacity. Over 100% requires confirmation and a reason, not independent approval. Same-person/same-project overlapping allocation is rejected. Capacity uses date intervals, not a sum of every row that overlaps the overall window. New allocations require an approved planned/active project, valid employee and project role, and dates inside the project. Cancellation retains history. Allocation creation can complete the onboarding allocation step.

Identified boundary to improve: the legacy project serializer strips billing rate, revenue and margin, but does not remove budget_amount, although approval proposal serialization does. The new implementation must consistently filter current records, proposals, history, capacity previews and exports; denied commercial fields must also be rejected in writes.

## Entity model and workflow separation

| Native entity | Plan |
| --- | --- |
| HRMS.Employee | Reuse employee identity, status and reporting-manager reference |
| HRMS.Customer | Add customer/account owner, contacts, contract dates/currency, restricted commercial fields and active/archived lifecycle |
| HRMS.Project | Add customer, PM/DM references, dates, engagement type, practice, health, budget/hours and restricted commercial values; draft/planned/active/on_hold/completed/archived lifecycle |
| HRMS.ProjectChange | Reuse for initial approval and staged amendments; extend with expected project revision, named approver snapshot and decision/application provenance |
| HRMS.ProjectRole | Add configurable project-role reference records; distinct from login/RBAC roles |
| HRMS.Allocation | Add employee/project/project-role references, percentage, dates, billable flag, rate override and allocated-by identity; planned/active/completed/cancelled lifecycle |
| HRMS.AllocationChange | Add initial/amend/release proposal, expected revision, requested-by, named approver, reason and native approval workflow |
| HRMS.TimesheetEntry | Reuse the installed configuration; later enforce approved operational project and valid employee allocation |
| HRMS.ProjectFeedback | Reuse; add stable project/allocation references in a versioned schema migration, retaining existing textual project_reference for old records |

Project operational state and approval request state remain separate. An active project stays active while an amendment is reviewed. Initial project creation can create a non-operational draft Project shell because the existing ProjectChange requires project_id. Initial allocation requests need no committed allocation until approval.

Project change: Draft -> Pending approval -> Approved; request changes returns to an editable draft; rejection retains immutable decision history; author can withdraw pending requests. Extend the configured v1 workflow deliberately for withdrawal rather than changing core or silently overwriting published configuration. Resubmission increments proposal revision; decisions must match the reviewed version.

Allocation change: Draft -> Pending approval -> Approved / Changes requested / Rejected; withdrawal allowed before decision. Only approval/application creates or changes committed capacity. Pending requests appear separately as proposed demand, not booked capacity. Operational allocation then moves Planned -> Active -> Completed, with explicit cancellation/release transitions.

## Recommended approval policy (changes from legacy, not existing behavior)

Preserve legacy viewing/management scopes. Add an explicit project-approver capability initially mapped to an HRMS business Super Admin. A platform infrastructure administrator is not automatically an HRMS business approver. Remove the implicit Super Admin self-approval exception by default; any emergency bypass must be an explicit, audited policy rather than an accidental consequence of broad permissions.

Project creation/material amendments go to the configured independent project approver. Finance is a commercial reader by default, as in legacy; additional Finance sign-off for specified commercial changes can be a later explicit policy.

Recommended allocation policy: PM submits -> assigned Delivery Manager approves. If the Delivery Manager is the requester, route to an independent project approver. Missing/inactive/self approvers block submission until a valid assignment is made. Over-allocation always requires a reason and designated exception approval, with capacity rechecked at final decision. Routine allocation approval is a deliberate addition to legacy; a compatibility policy can retain direct commits while still performing validation, native transitions and audit. Do not add multiple approval stages without a business requirement.

Project-manager role must be distinct from the existing generic reporting-manager role. Capability, action-specific record scope, field permission, current workflow state and assigned decision owner are all required. Do not combine HR read-all scope with PM edit-assigned to accidentally grant edit-all to a multi-role user. Assignment checks use immutable IDs while UI shows names. Snapshot approvers and audit explicit reassignment.

## Core and application responsibilities

Core remains unchanged: native entities, forms/fields, enrollments, transition execution and audit through public APIs. All additions are product definitions and HRMS-layer services. Runtime has no platform SQL access or imports of platform managers. Browser native mutation bypass stays blocked; service grants expand only to necessary entity types, fields and transitions.

HRMS services perform relationship validation, action/record/field checks, approval routing, interval-capacity calculation, staged amendment comparison, version checks and UI projection. Proposed API families are `/hrms/projects`, `/hrms/projects/{id}/changes`, `/hrms/allocations`, `/hrms/allocations/preview` and request action endpoints. These compose native entity APIs; they introduce no second project master.

Use application-owned tenant locking initially for all project/allocation writes and a durable operation journal. Validate fresh native records under the lock; recheck capacity and revisions when applying approval. Preserve idempotency markers and link human audit to native transitions. Multiple HTTP writes are not an atomic database transaction. Show approved-but-not-applied requests as pending application; prevent their incomplete records from enabling allocations, timesheets or onboarding completion. Resume from checkpoints after failure, with dependent writes blocked until reconciliation. If a future generic platform transaction/CAS capability is necessary, propose it upstream separately.

These guarantees rely on a single controlled HRMS mutation path across workers. Arbitrary native administrative writes/importers can bypass application locks, so they require controlled maintenance/reconciliation. Performance approvals currently also serialize through the application journal; project work should reuse that mechanism without duplicating an approval engine.

## Screens and integrations

Projects uses native table/filter/sort/detail primitives with Summary, Team/Allocations, Approval history and permission-gated Commercial tabs. Approval view shows current versus proposed values, requester, named approver, stage and permitted inline actions. Allocation preview shows dated capacity segments without exposing unauthorized projects or financial data; limited-scope users see aggregate other commitments instead of unrelated project details. Approvals also appear in Quick actions and Workflows.

Approved allocations can complete the corresponding ready onboarding step through its native transition, enable timesheets and supply project reviewers to performance cycles. Feedback creation deduplicates by review/project/reviewer, records source allocation references, and snapshots reviewer ownership for traceability. An allocation approval must not unlock a dependency until its native operational record is applied successfully.

## Implementation and migration order

1. Resolve policy choices: legacy direct allocation versus approval by default; direct Super Admin project creation exception; who holds project approval capability.
2. Install versioned customer/project/reference definitions and extend ProjectChange; migrate stable employee/customer/project IDs and role mappings.
3. Implement project creation, versioned amendments, independent approval and core workflow UI composition.
4. Implement allocations/capacity preview, approval/release, concurrency and recovery; migrate existing approved allocations without fabricating historical transitions.
5. Wire onboarding, timesheet eligibility and allocation-driven performance feedback.
6. Reconcile counts/states/references/history and test all role+scope combinations, direct-route denial, commercial read/write filtering, self-approval, double submission, stale versions, concurrent overbooking, partial writes and reruns.

Preserve existing projects' legacy approval state and allocation history as provenance. Do not reopen approved historical work merely to make it pass through the new approval policy.
