# Allocations workspace

Added 2026-10-05 in the HRMS skin at `/hrms/allocations`, under Delivery.
This exposes existing allocation data as a first-class workspace. It creates
no new entities, database tables, API permissions or core platform changes.

## Data relationships

```text
HRMS.Project  <-- project_id -- HRMS.Allocation -- employee_id --> HRMS.Employee
                                    |
                              project_role_id
                                    v
                             HRMS.ProjectRole

HRMS.AllocationChange -- project_id --> HRMS.Project
                     -- allocation_id --> HRMS.Allocation (amend/release)
```

An initial allocation request has no allocation record until approved and
applied. The existing `ProjectsService` controls creation, approval, dated
capacity checks, revisions, release, tenant scoping and commercial filtering.
An approval request is not committed capacity. No employee or project master
data is copied into a new application store.

## UI and APIs

- `AllocationsPage.tsx` uses the existing shared `useProjects` query for
  `GET /hrms/projects`. Counts and rows derive only from authorized results.
- Allocations and Requests are separate views with project/status filters and
  employee/project/role search. Project links open the existing project detail.
- Add allocation lists only projects whose server-provided actions include
  `request_allocation`. It reuses `ProjectAction`, configured allocation fields,
  eligible employee/role options, capacity preview and existing action endpoints.
- Saving creates a draft request; Requests links to the existing Workflows
  detail for submission and approval. My work continues using the same inbox.
- Allocation details reuse `ProjectDetail` for permitted amendment, release
  and native lifecycle actions. State labels use native workflow configuration.
- Shared `ProjectRecovery` exposes resumable operations on both directories;
  project recovery was extracted from the old project heading rather than copied.
- Deep links: `?project=<id>` filters the directory and `?allocation=<id>` opens
  a detail. Missing/out-of-scope allocation IDs show an unavailable message.
- Project assigned-team cards link back to this workspace.

## Access configuration

Settings → Roles → Project and allocation access remains the configuration
surface. `project:view` grants access to both directories; `allocation:request`
and project-management scope control requesting/amending/releasing allocations.
There is deliberately no second permission matrix or duplicate workflow.
PM assignment, independent approver, employee scope, capacity and field privacy
checks remain server-enforced. A separate allocation-only visibility capability
would be a later product policy change, not a core modification.

## Validation

Focused UI tests cover authorized creation targets, reuse of the allocation
command, configured status labels, filtering, request/committed separation,
workflow navigation, read-only visibility, access denial and retry on failure.
Existing HRMS project tests cover approval, capacity, scope, private commercial
fields, release, idempotency and recovery. Run the platform boundary verifier
and frontend build before merging. Do not run local fixture smoke tests on
production or assume a new route has been deployed before a main release.
