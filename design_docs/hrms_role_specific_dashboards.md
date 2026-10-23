# HRMS role-specific dashboards

Date: 2026-10-21
Status: Discussion captured for later implementation. No dashboard changes implemented by this document.

## Purpose

Provide useful dashboards for each business role using the native platform's dashboard capabilities. Keep the HRMS font, colors, spacing and component styling consistent with the existing application.

## Confirmed requirements

- HR, Project Manager (PM), Delivery Manager (DM), Office Admin and Super Admin should have different dashboards.
- Employee-only users do not need a dashboard. Keep My Tasks as their work entry point.
- Reuse native platform capabilities wherever possible.
- Preserve existing functionality, permissions and workflow behavior.
- Keep the native platform core generic and untouched. Put HRMS integration in the HRMS application and skin layers.

## Native platform findings

These findings are based on source inspection, not a live audit of each role's configuration.

| Capability | Current support |
| --- | --- |
| Separate saved dashboard definitions | Backend stores definitions by organization and dashboard key. |
| Dashboard selection in the current page | The native page loads and saves the `primary` dashboard. No role-to-dashboard selector was found. |
| Role permissions | Native `dashboard:read` and `dashboard:write` control viewing and editing. These do not constitute per-dashboard role assignments. |
| Layout | Dragging, resizing and saving widget layouts. |
| Widgets | Number cards, tables, activity lists, charts, gauges, custom queries, button cards, embedded views and text/content blocks. |
| Charts | Bar, line, area, pie and funnel. |
| Filters | Global time filter, widget filters and anchor entity filtering; support depends on the selected metric. |
| Refresh | Manual refresh is available. Automatic refresh was not verified. |
| Custom queries | Configured projection-view sources, filters, grouping and count/sum/average/minimum/maximum aggregations. Do not assume arbitrary SQL or unrestricted joins. |
| Embedded views | Workflow list, pipeline board and embed link. |
| HRMS exposure | A general dashboard route and dashboard API gateway were not found in the HRMS integration inspected. |

Available native metrics include entity counts, counts by entity type or field, workflow state counts, records currently in a state, records reaching a state during a period, transition trends, recent activity, SLA breaches and SLA compliance.

The native funnel represents current stage counts. It is not automatically a historical conversion funnel. Offer acceptance percentage, average onboarding duration and other business calculations need explicit definitions and may require additional support.

### Important access limitation

The native dashboard service currently rejects actors with restricted workflow access through `_deny_restricted_workflow_actor`, with the message:

> Dashboards are unavailable for workflow-restricted roles

This prevents aggregates from exposing hidden workflows. Role-specific dashboards cannot be implemented safely by changing the layout alone or removing this restriction.

Native field-permission handling exists, but HRMS project, team and relationship scopes must also be enforced. Counts, charts, query previews and embedded views require the same access discipline as record lists.

## Proposed dashboard content

The following content is a proposal to refine before implementation, not a confirmed metric specification.

| Role | Suggested dashboard | Intended data scope |
| --- | --- | --- |
| HR | Offers awaiting review, accepted offers awaiting joining, onboarding progress, completed onboarding trends, department headcount and overdue HR work | Records authorized for the user's HR role |
| Project Manager | Project progress, team allocations and pending approvals | Their authorized projects and team |
| Delivery Manager | Delivery portfolio, staffing and allocation gaps | Their authorized delivery scope |
| Office Admin | Pending IT/workplace provisioning, asset assignments and operational tasks | Their authorized operational records |
| Super Admin | Organization overview across HR, delivery and operations | All records authorized for the tenant business Super Admin |
| Employee only | No dashboard | My Tasks remains available |

Business Super Admin access must remain distinct from platform-wide organization administration.

### Suggested first HR dashboard

1. Number cards: active employees, offers awaiting review, accepted offers awaiting joining, onboarding in progress.
2. Offers by configured workflow stage.
3. Onboarding by stage of the existing Add Employee workflow.
4. Employees grouped by department.
5. Monthly onboarding completions, using the date records reached the completion state.
6. Work requiring attention, including overdue review or provisioning where due dates or SLAs exist.

Use actual configured workflow identifiers and states. Do not assume a particular offer joining state, fabricate missing dates or use the retired HRMS.OnboardingJourney entity.

## Proposed implementation approach

### 1. Reuse native definitions and widgets

- Use separate dashboard definitions for HR, PM, DM, Office Admin and Super Admin where supported through public platform APIs.
- Reuse native rendering, layout and widget components where their interfaces allow it.
- Keep HRMS-specific UI adapters and styling in `frontend/src/skins/hrms_native/`.
- Do not modify the native page merely to replace its hardcoded `primary` key. First assess reusable components and provide the selection integration in the skin.

### 2. Add role-to-dashboard selection in HRMS

- Resolve dashboard eligibility on the server from authenticated roles/capabilities.
- Expose only eligible dashboards in navigation and any dashboard selector.
- Deny direct requests for dashboards the actor cannot access, even if they know the key.
- Keep role mapping configurable where practical. The configuration location and editing surface need to be chosen before implementation.
- Proposed multi-role behavior: allow a user to switch among their permitted dashboards. Decide the default-selection rule before implementation.
- Employee-only users have no dashboard route access or navigation item; users who also hold a qualifying role may access that role's dashboard.

### 3. Enforce authorized data scope

- Put HRMS-specific orchestration and aggregation in `applications/hrms_api/`.
- Use public platform APIs; do not query platform database tables directly.
- Pass the human identity through the authorized integration. Do not substitute an elevated service identity to bypass native restrictions.
- Validate dashboard keys, metric requests, queries and filters server-side.
- Apply tenant, workflow, entity, field and HRMS relationship permissions before calculating totals or returning records.
- Treat frontend filters as presentation controls, not access controls.
- Where native dashboard endpoints reject workflow-restricted roles, retain the restriction. Determine whether an HRMS adapter can calculate the required metrics from authorized public record APIs. If no safe API exists, record that capability as blocked pending a platform capability rather than bypassing authorization.
- Ensure any aggregation covers all authorized result pages. Do not calculate organization totals from a single page of records.

### 4. Preserve HRMS presentation and behavior

- Follow the existing HRMS brand styles, cobalt palette, rounded cards and typography.
- Separate loading, empty, permission-denied and error states. Failed requests must not appear as zero work.
- Decide edit rights separately from view rights. Having a business dashboard should not automatically grant dashboard configuration access.
- Keep dashboard navigation and widget links consistent with current HRMS workflows and single-panel record details.

## Decisions needed before implementation

1. Final widgets and metric definitions for each role.
2. Exact PM and DM project/team visibility rules and Office Admin record scope.
3. Who may edit each dashboard versus only view it.
4. Where role mappings are configured and how multiple roles determine the default dashboard.
5. Whether Super Admin can switch to other role dashboards as well as see an organization overview.
6. Definition of an active employee, pending offer, joining status, overdue work and completion reporting period.
7. Which metrics can use native endpoints unchanged and which require authorized HRMS aggregation.

## Implementation and validation checklist

- Inventory current role permissions, native dashboard APIs and reusable component interfaces.
- Confirm safe data access for every proposed widget before exposing it.
- Implement dashboard mapping and access checks in the HRMS layer.
- Configure dashboards and add themed navigation/rendering in the HRMS skin.
- Verify HR, PM, DM, Office Admin, Super Admin, Employee-only and multi-role accounts.
- Test direct unauthorized dashboard-key requests, filter tampering, cross-tenant access and restricted field exposure.
- Verify aggregate counts against authorized source records, including pagination and date boundaries.
- Verify denied or failed requests never render as successful zero totals.
- Test loading, retry, empty states, switching dashboards and existing workflow links.
- Run appropriate backend tests, frontend build and `python scripts/verify-platform-boundary.py`.

## Source references

- `frontend/src/pages/dashboard/index.tsx` — current dashboard page.
- `frontend/src/pages/dashboard/hooks/useDashboard.ts` — loading and saving the `primary` dashboard.
- `frontend/src/pages/dashboard/lib/constants.ts` — widget options.
- `frontend/src/pages/dashboard/lib/embeddedWidgets.tsx` — embedded views.
- `backend/dashboard/db_models.py` — dashboard definitions keyed by organization and key.
- `backend/dashboard/controller.py` — native dashboard API and read/write permissions.
- `backend/dashboard/manager.py` — access restriction and query/field permission handling.
- `backend/dashboard/metrics.py` — metric catalog and implementations.
- `backend/dashboard/models/request.py` — query and widget data contracts.
- `frontend/src/skins/hrms_native/App.tsx` — HRMS routes.
- `applications/hrms_api/hrms_app/settings_gateway.py` — explicit native configuration gateway.
- `design_docs/hrms_migration_plan.md` — HRMS/platform architectural boundary.
