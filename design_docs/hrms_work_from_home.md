# Work from home

Implementation: `applications/hrms_api/hrms_app/wfh.py`, `wfh_catalog.py`, and
`frontend/src/skins/hrms_native/pages/WorkFromHome.tsx`. Native platform source
is unchanged. The existing installer adds the packs and service permissions
through public platform APIs. Existing native form/workflow edits are preserved.

## User journeys

- HR Full and tenant Super Admin open **HR Cockpit → Work from home → Policy**.
  Select the year using the calendar month controls, enter annual full-day
  allowance and minimum calendar-day notice, then save. No allowance is silently
  assumed on first install: requests require an active policy.
- Employees open **Employees → Work location calendar**, select weekdays, add
  an optional private note, and submit to HR. They can review their requests and
  cancel pending/approved requests when every requested date is still current
  or future. Another HR approver must decide an HR employee's own request.
- HR reviews requests in Cockpit, **My tasks & approvals**, or **Workflows**.
  The My work inbox covers all years, including requests for next year.
- Everyone with a recognized HRMS role can see approved dates and employee
  names/departments in the work location calendar. This does not grant access
  to the restricted employee directory API. Pending requests, reasons and
  allowance details are only returned to the owner and authorized HR reviewers.

## Native records and states

- `HRMS.WorkFromHomePolicy`: one record per calendar year, annual_days,
  notice_days, revision. Initial `draft` → `activate` → `active` through the
  native transition API. Subsequent configuration updates retain the record
  with an optimistic revision check and application audit.
- `HRMS.WorkFromHomeRequest`: employee_id links `HRMS.Employee`, policy_id
  links that year's policy, year, dates (newline-separated ISO dates), reason.
  Initial `pending`; HR `approve` → `approved` or `reject` → `rejected`.
  Owner `cancel` → `cancelled` from pending or approved. Rejected/cancelled are
  terminal. Dates/reason are immutable after submission.
- The native form configuration supplies labels, required/read-only metadata;
  the server checks these constraints too. Enrolled workflow versions supply
  state/action labels; the platform executes transitions and guards.
- Semantic state/trigger keys are HRMS handler contracts. Labels/guards can be
  configured; arbitrary new operations require HRMS handlers, not core changes.

## Rules and consistency

Pending and approved requests reserve annual allowance. Used/upcoming approved
days and pending reservations are counted separately. Reject/cancel releases
allowance. Concurrent writes take the shared tenant advisory lock. Policy
reductions below any employee's existing reservations are rejected. Policy
notice changes apply only to new submissions. Requests cannot span years.

Only full weekdays are supported. Published holiday calendars are selected
through the existing cockpit feed, including version/effective-date filtering.
Holiday and leave conflicts are rechecked at HR approval. Leave creation also
rejects overlapping pending/approved WFH dates. No calendar entry claims that
an unmarked employee is physically in the office.

The application database contains only operation intent/retry state and audit;
policies and requests live in native records and workflow enrollments. Pending
write intent blocks competing WFH mutations and leave creation until the
originating operation is replayed. Retry reuses the original key. Never delete
an uncertain operation or submit with a new key to bypass this protection.
An outcome that cannot be reconciled requires administrator investigation.

Current scope: calendar-year allowance shared by eligible active employees,
full days, HR Full/Super Admin review. No proration, carry-forward, half days,
employee-specific exceptions, email notifications or past-date corrections are
included. Holiday/policy changes do not silently rewrite approved history.

## Installation and validation

Run the normal `python -m hrms_app.install` provisioning job on an existing
installation before serving this version. The production pipeline already
runs this installer. It creates types/forms/workflows, not example policies or
requests. HR enters the actual allowance in Cockpit after installation.

Tests: `applications/hrms_api/tests/test_wfh.py` and
`frontend/src/skins/hrms_native/pages/WorkFromHome.test.tsx`; also run the full
HRMS API suite, TypeScript build and `scripts/verify-platform-boundary.py`.
