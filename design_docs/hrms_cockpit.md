# HR Cockpit and publishing

Implementation lives in `applications/hrms_api/hrms_app/cockpit*` and the HRMS frontend skin. Core backend/frontend files remain unchanged. Native entity records and workflow enrollments are the source of truth; the application database stores only permission overrides, operation recovery and audit.

## Using the module

1. Sign in as HR Basic, HR Full, Recruiter or Super Admin and open HR Cockpit.
2. Choose Policies, L&D calendar, Holidays, Job descriptions or Open positions. Recruiters can author the last two categories.
3. Add content and choose an independent approver. Set audience to Employees or Public, preview the content and submit.
4. The designated approver sees pending approvals in Quick actions as well as the cockpit and Workflows. Quick actions opens the same review drawer to approve or request changes. Publishers also see approved content awaiting publication there. Completed decisions refresh the queue.
5. Public content appears below the login form and at `/public`. Employees can view both audiences under Published information. Pause withdraws content; Resume republishes the latest version; Close then Archive preserves history.

Defaults: HR Basic authors all types; Recruiters author jobs; HR Full and Super Admin author, approve and publish. Super Admin configures these permissions under Settings → Roles → HR Cockpit access. Approval is assigned and never self-approved. Role capabilities combine across multiple roles and are checked on every API request.

Native forms drive field labels, order, required/read-only settings and available enum options. Native workflow definitions supply stage/transition labels and execute state changes. HRMS command triggers remain semantic contracts (submit, approve, request_changes, publish, pause, resume, close, archive); introducing a new business operation requires an HRMS handler. Existing enrollments stay pinned to native workflow versions.

## Data and revision model

Native types: HRMS.Policy, HRMS.LearningEvent, HRMS.HolidayCalendar, HRMS.JobDescription, HRMS.JobOpening. The existing JobOpening definition is extended additively. An opening links a published job description. A holiday calendar is one versioned yearly record; enter one `YYYY-MM-DD | Holiday name` per line, so the whole calendar is approved together. L&D events carry event/end dates, trainer, location and an optional registration link.

Published records are immutable in the HRMS UI/API. New revision creates a new native record and enrollment sharing a publication identifier. The previous publication stays visible until the new approved version is published and its start date is reached. A withdrawn or expired newest version does not reveal an older publication. Concurrent actions use revision checks and a tenant lock. A durable operation journal supports retry after uncertain upstream responses, with record markers and native transition idempotency.

The anonymous endpoint `/v1/api/hrms/public/content` is bound to this deployment's configured organization. It accepts no tenant override and returns an explicit display-field allowlist only for public, published, effective versions. Internal identifiers, owners, approval metadata, drafts and employee-only content are excluded. Responses are not cached. Text renders as text, not raw HTML. Public links require HTTPS and no embedded credentials.

Documents currently use an explicitly supplied public HTTPS link; private file upload/storage and signed attachment delivery are not included. HR must supply a link intended for its selected audience. Holiday calendars are published as dated lists rather than a drag-and-drop calendar editor. Notification emails are not added by this module.

## Installation and validation

For existing installations run `python -m hrms_app.install_cockpit` with installer environment variables in the platform-install service. It preserves tenant edits while adding missing native fields/forms/workflows and service grants. Do not reset or replace configured workflows. Fresh installs include the cockpit packs in the normal installer.

Tests cover independent approval, draft privacy, employee-only content, date windows, publication revisions, withdrawal without resurrection, stale writes, retry and restricted author roles. Verify the native core with `python scripts/verify-platform-boundary.py`.
