# HRMS bug tracker

Started 2026-10-09. Reviewed against `main` at `6a7c474` on the local stack (`localhost:5182`, demo users). Production was not touched.

**How these were found.** Every HRMS workflow passed end-to-end on the local stack (projects, onboarding, leave, performance, HR Cockpit, WFH), so these are not crashes in the happy path. Each item below is a behaviour that is wrong, gets stuck, gives an error, or ignores Settings. Missing features and product decisions (job apply button, leave balance, half day, salary fields, mid-year check-in, rating scale and similar) are deliberately left out.

**Fix type.** *Settings* means an admin can do it in the app (Settings → Fields / Forms / Funnels / Roles / Integrations). *Code* means a code change in the HRMS layer (`applications/hrms_api`, `frontend/src/skins/hrms_native`). No fix touches platform code. Paths without a prefix are under `applications/hrms_api/hrms_app/`.

**Status.** Items marked *(reproduced)* were seen failing on the local stack. The others come from reading the code and local data, and must be reproduced before fixing.

---

## Fix first: these unblock many others

| ID | Sev | Bug | Fix | Where | Status |
|---|---|---|---|---|---|
| X-1 | High | Fields added or made required in Settings → Fields/Forms don't show up or save on the Leave, Employees, Performance and HR Cockpit screens. The forms and API contracts only know their built-in fields. | Code | `requests.py`, `performance_contracts.py`, `cockpit.py:41-73`, `frontend/.../pages/*Page.tsx` | ☐ Open |
| X-2 | High | Renaming or adding a step in Settings → Funnels breaks the Leave, Onboarding, Performance and HR Cockpit buttons. The action names are hard-coded, so renamed steps lose their button and new steps never get one. | Code | `service.py:111-168,369`, `performance.py:97-140`, `cockpit.py:106-160` | ☐ Open |
| X-3 | Low | Every HRMS page logs `403 /v1/api/workflow-state-machines` for everyone except admins. The skin loader fetches the workflow list, but the HRMS gateway only allows that call for Settings users. *(reproduced)* | Code | `settings_gateway.py` (allow the read), or stop the call in the HRMS skin | ☑ Fixed (branch `fix/hrms-bugs-batch-1`): the 403 came from the platform (no workflow read permission), not the gateway; the gateway now answers that one list read with the empty list the skin falls back on |

## HR Cockpit (Policies, L&D calendar, Holidays, Job descriptions, Open positions)

| ID | Sev | Bug | Fix | Where | Status |
|---|---|---|---|---|---|
| HC-1 | High | An open position is tied to one *version* of a JD. Once that JD is revised or closed, the opening can no longer be submitted or revised ("Choose a published job description"). | Code | `cockpit.py:293-303` | ☐ Open |
| HC-2 | High | Making year, event date or openings optional in Settings causes server errors (500). The code reads those fields directly. | Code | `cockpit.py:214-218,249-251,267-273,294` | ☑ Fixed (branch `fix/hrms-bugs-batch-1`): Settings can make fields required but not relax the ones a content type depends on; missing ones get a clear 422 |
| HC-3 | Med | A pending item can't be withdrawn and its approver can't be changed, so it's stuck if the approver is away. | Code | `cockpit.py:106-134` | ☐ Open |
| HC-4 | Med | "New revision" copies the old approver. It fails if you are that approver or the approver has left, and the screen gives no way to change it. | Code | `cockpit.py:288-292,368-374` | ☐ Open |
| HC-5 | Med | Everyone with cockpit view sees every draft of all five types (recruiters see unpublished policy drafts, HR Basic sees job drafts). | Code | `cockpit.py:136-172` | ☐ Open |
| HC-6 | Med | Holidays: one blank line in the holiday list rejects the whole calendar. | Code | `cockpit.py:272-287` | ☑ Fixed (branch `fix/hrms-bugs-batch-1`) |
| HC-7 | Med | Holidays: the calendar's location is ignored. Any published holiday blocks WFH for everyone, and two calendars for the same year and location can both be published. | Code | `wfh.py:88-106`, `cockpit.py` | ☐ Open |
| HC-8 | Low | After a new revision is published, the old version stays "Published". The board counts it twice, and its Pause/Close buttons don't affect the live page. Items whose "publish until" has passed also still show as Published. | Code | `cockpit.py:174-210,427-428` | ☐ Open |
| HC-9 | Low | L&D calendar, Holidays, Job descriptions and Open positions are pinned to form version 1, so edits in Settings → Forms don't reach them. Policy is pinned to the latest version. | Settings | Funnels → each of the 4 workflows → pin form to latest → publish | ☐ Open |
| HC-10 | Low | The server doesn't check that the hiring manager is an active user, that the application deadline is in the future, or that requisition codes are unique. | Code | `cockpit.py:252-257,293-303` | ☑ Fixed (branch `fix/hrms-bugs-batch-1`) |
| HC-11 | Med | The HR Cockpit board takes about 8 seconds to load. Building the approver list calls the roles API once per user. *(reproduced)* | Code | `cockpit.py:83-104` (`people()`) | ☑ Fixed (branch `fix/hrms-bugs-batch-1`): board 4.9s → 1.4s; My Tasks 7–14s → 2–5s |

## Leave requests

| ID | Sev | Bug | Fix | Where | Status |
|---|---|---|---|---|---|
| LV-1 | High | Only users with the Manager or Delivery Manager role can approve. If someone's manager has another role (admin, superadmin, HR, PM, finance), nobody can ever approve their leave. In local data: the Delivery Manager reports to Superadmin, who sees the request but gets no buttons. | Code | `role_capabilities.json:10,65`, `policy.py:17-23`, `service.py:369` | ☑ Fixed (branch `fix/hrms-bugs-batch-1`): approver is now the Project Manager of any project the employee is on over the leave dates, else the reporting manager |
| LV-2 | High | Weekends and holidays are counted as leave days. A Saturday–Sunday leave was accepted and approved (LVE-0001), and "Days approved" counts calendar days. | Code | `service.py:322-344`, `frontend/.../LeaveRequestsPage.tsx:104` | ☑ Fixed (branch `fix/hrms-bugs-batch-1`) |
| LV-3 | Med | Approved leave can't be cancelled. Cancel is only offered while pending, and the workflow has no approved → cancelled step. | Settings + Code | Funnels → Leave Request (add approved→cancelled), plus `service.py:369` | ☑ Fixed (branch `fix/hrms-bugs-batch-1`): the employee can cancel approved leave until it starts; the installer adds the step on deploy. Leave approved before that deploy keeps its old rules (no Cancel) |
| LV-4 | Med | Leave can be requested for past dates (for example last year), and requests whose dates have passed stay pending forever. | Code | `service.py:322-344,369`, `requests.py:18-24` | ☑ Fixed (branch `fix/hrms-bugs-batch-1`): see HR decisions below |
| LV-5 | Med | Employees with no reporting manager (for example the CEO) can't apply for leave at all. | Code | `service.py:330-332` | ◐ Partly (branch `fix/hrms-bugs-batch-1`): employees on a project can apply (their PM approves); with neither a project nor a manager they get a clear message |
| LV-6 | Med | Users without an employee profile still see the Leave menu and form, but get 403 on load and on submit. *(reproduced: admin)* | Code | `service.py:298-306`, `LeaveRequestsPage.tsx:107,128`, `workspace/Shell.tsx:229` | ☑ Fixed (branch `fix/hrms-bugs-batch-1`) |
| LV-7 | Med | Removing "annual" from leave types in Settings hides it in the dropdown, but the form still submits "annual" by default. | Code | `LeaveRequestsPage.tsx:71,113`, `forms/ConfiguredForm.tsx:40-51` | ☑ Fixed (branch `fix/hrms-bugs-batch-1`) |
| LV-8 | Low | A Reason made required in Settings is only checked in the browser, not by the server. | Code | `service.py:345-347` | ☑ Fixed (branch `fix/hrms-bugs-batch-1`) |

## My Work

| ID | Sev | Bug | Fix | Where | Status |
|---|---|---|---|---|---|
| MW-1 | Med | Performance tasks (goals to approve, self review, manager review, feedback, cycle approval) never appear in My Work or in the badge. | Code | `frontend/.../workspace/useWaitingActions.ts:36-42` | ☑ Fixed (branch `fix/hrms-bugs-batch-1`) |
| MW-2 | Med | Leave requests the person isn't allowed to decide still show as "Leave approvals". "Review request" then opens a page with no buttons. | Code | `useWaitingActions.ts:32,38`, `service.py:309-311` | ☑ Fixed (by LV-1) |
| MW-3 | Med | HR sees every new hire's ready onboarding steps as "waiting on you", including steps owned by IT or the new hire. This inflates the count. | Code | `service.py:124-126`, `useWaitingActions.ts:31` | ☑ Fixed (branch `fix/hrms-bugs-batch-1`) |
| MW-4 | Low | Counts can be wrong. Leave lists are cut at 100 rows (history included), and "Next time off" and "Days approved" use the same partial list. | Code | `service.py:316-320`, `useWaitingActions.ts:26,32` | ☑ Fixed (branch `fix/hrms-bugs-batch-1`) |
| MW-5 | Low | If the WFH inbox call fails, the "Waiting on you" summary shows "…" forever. | Code | `useWaitingActions.ts:37,47` | ☑ Fixed (branch `fix/hrms-bugs-batch-1`) |
| MW-6 | Low | One leave request without a workflow enrollment makes the whole Workflows board return 409 for everyone who can see it. | Code | `workflow_config.py:29-31`, `service.py:347-348` | ☑ Fixed (branch `fix/hrms-bugs-batch-1`) |
| MW-7 | Low | Due dates are shown as raw ISO text ("Due 2026-10-08T07:22:34…"). | Code | `frontend/.../pages/MyWorkPage.tsx:107` | ☑ Fixed (branch `fix/hrms-bugs-batch-1`) |

## Employees

| ID | Sev | Bug | Fix | Where | Status |
|---|---|---|---|---|---|
| EM-1 | High | An employee can't be edited after creation: no manager change, transfer, designation change or correction. | Code | `main.py:182-196`, `service.py` (add an update command) | ☑ Fixed (branch `fix/hrms-bugs-batch-1`): HR (HR Basic, HR Full, Admin) can edit name, department, designation, reporting manager, joining date, employment type, notice period, phone and location from the directory. Reporting loops and inactive managers are refused; a department no longer offered can be kept. Leavers' records are locked |
| EM-2 | High | An employee can't be deactivated or marked as left. Leavers stay "active" in the directory, still count as active managers, and the same email can never be re-hired. | Code | `service.py:209`, `catalog.py:93-96` | ☑ Fixed (branch `fix/hrms-bugs-batch-1`): Record exit (last working day, reason, note). A future day puts them on notice; on or after it they are offboarded, their sign-in suspended (a never-activated invite is rejected) and they drop out of manager and leave-approver choices. Notice can be withdrawn. Re-hiring the same email stays a Super Admin task |
| EM-3 | Med | HR can't create Office Admin or Finance staff, so onboarding steps 1, 2 and 6 (ID, payroll, laptop) always fall back to HR or the creator. | Code | `requests.py:33`, `service.py:85-89` | ☑ Fixed (branch `fix/hrms-bugs-batch-1`) |
| EM-4 | Med | The directory and onboarding routing use a stale copy of the role. Changing a user's role in Settings → Roles/Users isn't reflected. | Code | `service.py:59,261` | ☑ Fixed (branch `fix/hrms-bugs-batch-1`) |
| EM-5 | Med | The "viewer" role can see the whole directory (emails, everyone's access role, account status) and all onboarding cases. | Code | `role_capabilities.json:127-132`, `service.py:104` | ☑ Fixed (branch `fix/hrms-bugs-batch-1`): onboarding cases now need onboarding:view, so viewer no longer sees them; viewer keeps the read-only directory (standard for a company directory) ☑ |
| EM-6 | Low | The tenant "admin" role can create employees but can't activate their accounts. | Code | `role_capabilities.json:76-90` | ☑ Fixed (branch `fix/hrms-bugs-batch-1`) |
| EM-7 | Low | Small UI bugs: the "On leave"/"Offboarded" filters can never match (so "Other status" is always 0), the "Requesting…" text shows a broken character, and the Access role label doesn't follow Settings (key `role` vs `hrms_role`). | Code | `frontend/.../EmployeeDirectoryPage.tsx:80,133,149,169` | ☑ Fixed (branch `fix/hrms-bugs-batch-1`): broken "Requesting…" character and Access role label key fixed; the status filter is now Active / On notice / Offboarded and the stat shows On notice ☑ |

## Onboarding

| ID | Sev | Bug | Fix | Where | Status |
|---|---|---|---|---|---|
| ON-1 | High | A new hire's account can't be activated without an email provider, even though the org signs in with Google. HR creates a local account, and setup-access then needs SMTP/SES (409). | Code (workaround: Settings) | `service.py:224-226`, `employee_access.py:45-51`; workaround: Settings → Integrations → configure email | ◐ Code fixed (branch `fix/hrms-bugs-batch-1`): when Google sign-in is configured over HTTPS and the email is on the company domain, activation needs no email provider. Production still needs config: it runs on plain HTTP, so Google sign-in is off; configure an email provider in Settings → Integrations (this also fixes TL-2) |
| ON-2 | High | Steps 4–5 (personal details, documents) are assigned to the new hire while their account is still pending, so they can't do them. "Invite employee to HRMS" is just a checkbox, not the real activation. | Code | `service.py:259`, link step 3 to `employee_access.py` | ◐ Partly (branch `fix/hrms-bugs-batch-1`): "Invite employee to HRMS" now completes itself when HR activates the account (once the Newtuple ID step is done); manual ticking stays allowed so onboarding is never blocked where activation is not yet possible |
| ON-3 | Med | Steps go to the first person who matches the role, not the right person. In local data, 6 of 8 steps belong to a Super Admin with no employee profile, and the hire's own manager never gets a step. | Code | `service.py:259-266`, `onboarding_template.py:31-38` | ☐ Open |
| ON-4 | Med | A step or case can't be reassigned, re-dated or cancelled (no-show, withdrawn offer). | Code | `main.py:262-268`, `catalog.py:107-110` | ☐ Open |
| ON-5 | Med | Due dates count from the moment HR creates the case, not from the joining date, and nothing flags overdue steps. | Code | `service.py:271`, `frontend/.../OnboardingPage.tsx:116` | ☑ Fixed (branch `fix/hrms-bugs-batch-1`): see HR decisions below |
| ON-6 | Med | One bad case (unknown template, deleted employee, duplicate step) breaks the whole Onboarding page, My Work and Workflows for everyone. | Code | `service.py:39,106-110` | ☑ Fixed (branch `fix/hrms-bugs-batch-1`) |

## Performance

| ID | Sev | Bug | Fix | Where | Status |
|---|---|---|---|---|---|
| PF-1 | High | One employee who leaves blocks the whole cycle. Every stage waits for all reviews and there is no way to withdraw a participant. | Code | `performance.py:252-261,119-140`, `performance_catalog.py:27-39` | ☐ Open |
| PF-2 | High | A feedback request can't be cancelled or reassigned. If the reviewer never answers, the manager review and the whole cycle are stuck. | Code | `performance.py:308-309`, `performance_catalog.py:50` | ☐ Open |
| PF-3 | High | One unfinished or failed action by any user locks every performance action for the whole company, and only that user can resume it. | Code | `performance.py:49-50,344-346,362` | ☐ Open |
| PF-4 | High | HR can't close the cycle until every employee acknowledges, and there's no override. | Code | `performance.py:261`, `performance_catalog.py:39` | ☐ Open |
| PF-5 | High | Cycle dates and deadlines aren't enforced. The 2042 test cycle was fully run and closed today. | Code | `performance.py:120-139,251-262` | ☐ Open |
| PF-6 | Med | People who join after the cycle is approved can't be added. | Code | `performance.py:102-103,246-248` | ☐ Open |
| PF-7 | Med | A wrong goal can't be deleted. It stays forever and must keep at least 1% weight. | Code | `performance.py:263-271`, `performance_contracts.py:43` | ☐ Open |
| PF-8 | Med | A manager change during the cycle isn't picked up, and employees with no reporting manager (or a manager without an active login) can't be added. | Code | `performance.py:73-80,209-225,284-286` | ☐ Open |
| PF-9 | Med | A published rating can't be corrected; reviews and cycles can't be reopened. | Code | `performance_catalog.py:17-21,29,39` | ☐ Open |
| PF-10 | Med | Only the HR user who created a draft cycle can edit or submit it, and the approver can't be changed while the cycle waits for approval. If either person leaves, the cycle is stuck. | Code | `performance.py:102-106` | ☐ Open |
| PF-11 | Low | "Edit cycle" opens a blank form, so every field and participant must be re-entered. | Code | `frontend/.../PerformancePage.tsx:25-27,55-57` | ☑ Fixed (branch `fix/hrms-bugs-batch-1`) |

## Tooling and deploy

| ID | Sev | Bug | Fix | Where | Status |
|---|---|---|---|---|---|
| TL-1 | Med | `smoke_local.py` and `smoke_performance.py` fail before testing anything. They use `kavya.menon@newtuple.com`, who doesn't exist after the demo seed. With `demo.employee` / `demo.hr-full` swapped in, both pass. *(reproduced)* | Code | `applications/hrms_api/tools/smoke_local.py:52`, `smoke_performance.py:19` | ☑ Fixed (branch `fix/hrms-bugs-batch-1`) |
| TL-2 | Low | Every production deploy ends "failure" at the email configuration step, even though the app is updated and healthy. *(reproduced)* | Settings (GitHub) | Repository secrets: `EMAIL_*` / `SMTP_*` used by `.github/workflows/hrms-production.yml` | ☐ Open |

---

## HR decisions

Where a fix needed an HR rule, these standard-practice choices were made. Change any of them here first, then in code.

| Area | Decision |
|---|---|
| Leave approver | The Project Manager of any project the employee is allocated to over the leave dates decides; any one of them is enough. Without such a project, the reporting manager decides. Approvers decide whatever their role. Nobody approves their own leave. |
| Leave days | Leave counts working days: weekdays that are not published holidays. A request with no working day is refused. |
| Past-dated leave | Planned leave (annual, casual, unpaid, other) must start today or later. Sick leave can be recorded up to 7 days after it began. A pending request whose dates have passed stays with its approver, who can still approve or reject it. |
| Cancelling leave | The employee can cancel pending leave any time, and approved leave until the day it starts. |
| Onboarding due dates | Pre-boarding (Newtuple ID, payroll account, HRMS invite, laptop and badge) is due by day one. Personal and bank details and documents are due 3 days after joining, HR orientation 5 days after, project allocation 7 days after. A hire added after their joining date counts from the day they are added. |
| HRMS invite step | Completes itself when HR activates the hire's account, once the Newtuple ID exists. HR can still tick it by hand. |
| Account activation | Accounts on the company domain sign in with Google when Google sign-in is configured over HTTPS; otherwise activation sends a password-setup email, which needs an email provider. |
| Editing employees | HR Basic, HR Full and Admin correct job and personal details. Work email and employee code identify the account and don't change; access roles change through account access. A reporting manager must be active and can't be someone who reports to the employee. |
| Exits | Recording an exit (resignation, termination, contract end, retirement) is for HR Full, Admin and Super Admin; privileged accounts need Super Admin. A future last working day means notice: they keep working and signing in. On or after it, they are offboarded and signed out; the record is kept read-only. A resignation can be withdrawn during notice. |
| Settings vs code | Settings controls fields, labels, options and extra workflow steps. Business rules (who approves, date rules, limits) stay in code with tests. Settings can make a field required but cannot relax one a screen depends on. |

## Already fixed

| Bug | Fixed in |
|---|---|
| HRMS screens read the old Forms table instead of Fields → Forms → Workflow | PR #5 |
| Settings → Forms opened the old Form Configuration instead of the Method Library | PR #5 |
| HR Cockpit sent number fields (`year`, `openings`) as text | PR #5 |
| Project role list lost labels once a role was added to the picklist | PR #5 |
