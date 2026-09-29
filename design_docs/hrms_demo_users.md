# Local HRMS demo users

Open http://localhost:5182/login. Each account has exactly one role. Unique generated passwords are stored only in the ignored `.hrms-demo-local/users.json` file; they are not included in this guide. Existing accounts and onboarding assignments are preserved.

| Email | Role | Current HRMS access |
| --- | --- | --- |
| demo.employee@newtuple.com | Employee | Own leave requests, assigned onboarding steps, own performance reviews |
| demo.manager@newtuple.com | Reporting Manager | Employee access plus direct-report leave decisions and assigned performance manager reviews |
| demo.hr-basic@newtuple.com | HR Basic | Employee directory, add employees, own/assigned work |
| demo.hr-full@newtuple.com | HR Full | Directory, add employees and assign permitted HR roles, manage onboarding and performance cycles |
| demo.delivery-manager@newtuple.com | Delivery Manager | Own/assigned work, direct-report leave decisions, assigned performance reviews and organization-wide project/allocation management |
| demo.project-manager@newtuple.com | Project Manager | Own/assigned work; create and manage assigned projects, submit allocations for approval |
| demo.finance@newtuple.com | Finance | Own/assigned work, including assigned payroll onboarding step |
| demo.office-admin@newtuple.com | Office Admin | Own/assigned work, including assigned account/assets onboarding steps |
| demo.recruiter@newtuple.com | Recruiter | Own/assigned work; recruitment module permissions are not implemented yet |
| demo.performance-approver@newtuple.com | Performance Approver | Approve a performance cycle when selected as its approver, plus own/assigned work |
| demo.viewer@newtuple.com | Viewer | Read-only directory and permitted workflow observation; no Onboarding management menu, employee profile or review participation |
| demo.admin@newtuple.com | Admin | HR management and performance cycle approval when selected |
| demo.superadmin@newtuple.com | Super Admin | Admin access, project approvals, permission to assign HR Full, and native tenant Settings |

The Onboarding management menu and route are available only to HR Basic, HR Full, Admin and Super Admin. Other staff open their assigned steps from My Work or Workflows. The header shows current assigned roles from the HRMS capability API.

Role permissions do not bypass workflow state, prerequisites, record ownership, or designated approver checks. All browser accounts, including admins, remain blocked from direct native entity mutations through the HRMS gateway. The internal service role is not an interactive demo account.

## Copy a password

Run from the repository directory, changing the email for the account you want:

```powershell
$demoAccounts = (Get-Content -Raw .hrms-demo-local/users.json | ConvertFrom-Json).accounts
($demoAccounts | Where-Object email -eq 'demo.hr-full@newtuple.com').password | Set-Clipboard
```

Paste into the login form. Separate browser profiles/private windows can help compare roles.

## Test relationships

Most demo employees report to Demo Reporting Manager. That manager reports to Demo Delivery Manager, who reports to Demo Super Admin. Demo Super Admin has no reporting manager, so leave submission requiring a manager cannot succeed for that account until one is configured.

Use HR Full to create an employee/onboarding case. New cases can resolve the active Finance, Office Admin and Delivery Manager demo employees as step owners. Inspect the actual owner displayed on each step: existing eligible users may also be selected, and old cases are not reassigned by this setup. Only the assigned owner or an onboarding manager can complete a ready step.

For performance testing, use HR Full to create a cycle, select demo employees as participants and Demo Performance Approver as approver. Employee and manager actions follow the relationships captured in the review. Role membership alone does not make someone the approver of every cycle.

## Repeat setup

After starting the current native stack (`scripts/hrms-local.ps1 native-up`):

```powershell
./scripts/hrms-local.ps1 native-demo-users
```

The setup uses public platform APIs, creates missing demo identities, assigns one role per fixture, and verifies logins and HRMS permission boundaries. Rerunning preserves passwords and reuses the demo records. Keep the local manifest: if an account already exists without its manifest, the tool refuses to take it over. This command is restricted to this project's isolated local stack and fixed demo organization.

Product capabilities live in `applications/hrms_api/hrms_app/role_capabilities.json`; provisioning lives in `applications/hrms_api/tools/seed_demo_users.py`. No core platform source changes are required.

## Super Admin Settings

Sign in as `demo.superadmin@newtuple.com`, then choose **Settings** in the sidebar or open http://localhost:5182/settings.

- Workflows: `/settings?tab=funnels`; opens the existing native workflow editor.
- Entities: `/settings?tab=entities`; HRMS entity types and relationships.
- Forms: `/settings?tab=forms`; configured entity forms and fields.
- Users and Roles: `/settings?tab=users` and `/settings?tab=roles`.
- The native Settings navigation also exposes the available automation, integration, audit, branding and display editors.

To copy the Super Admin password from the repository directory:

```powershell
$demoAccounts = (Get-Content -Raw .hrms-demo-local/users.json | ConvertFrom-Json).accounts
($demoAccounts | Where-Object email -eq 'demo.superadmin@newtuple.com').password | Set-Clipboard
```

Only Super Admin receives `platform:configure`. Tenant Settings use the signed-in user's native token and permissions, never the application's service identity. Platform-wide organization administration is excluded. Generic entity-record writes and workflow actions remain blocked at the gateway and must use HRMS business APIs.

The Roles screen shows both native platform permissions and a read-only view of HRMS application capabilities. Changes to native roles do not automatically change the HRMS business capability mapping in `applications/hrms_api/hrms_app/role_capabilities.json`.
