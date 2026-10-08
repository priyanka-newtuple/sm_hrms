# Employee onboarding and account access

HR starts with Employees → Add Employee. This creates the native employee record,
links or provisions its native user account, and starts the onboarding workflow.
Employment, account access and onboarding progress are displayed separately.

New accounts stay pending until an authorized person selects **Activate & send
setup email** in the employee directory. HR Basic and HR Full can activate standard
employee accounts; Super Admin handles privileged accounts. Suspended/rejected
accounts and offboarded employees cannot be activated through this action.
The activation decision is explicit; joining dates do not automatically grant access.

Existing active/pending accounts in the tenant can be linked without resetting their
password or replacing their roles. Existing privileged accounts require Super Admin
and a matching selected role. An account already linked to another employee is rejected.
Designation never implicitly grants application permissions. Project Manager and
Delivery Manager access roles are available to Super Admin in Add Employee.

All platform operations use public APIs. HR receives a narrow, audited product action,
not native Settings administration. No platform database or core source is changed.
No new database migration is required.

## Email setup: Google Workspace

Super Admin configures **Settings → Integrations → SMTP**, using the existing native
integration. Supply:

| Setting | Value |
| --- | --- |
| SMTP host | `smtp.gmail.com` |
| Port | `587` |
| TLS | Enabled |
| Username | Full sender mailbox address |
| Password | Google app password for that mailbox |
| From address | The sender mailbox or an authorized sending alias |
| From name | `Newtuple HRMS` |
| Reply-to | HR mailbox that receives employee questions |

The sender needs 2-Step Verification and app-password availability under the
organization's Google Workspace policy. Use a dedicated sender mailbox and enter
the app password directly in the secure integration form. Do not store it in Git or
chat. If app passwords are disabled, the Workspace administrator must choose an
approved sending arrangement; the current native SMTP adapter requires username
and password authentication and does not implement Gmail OAuth or unauthenticated
IP-based relay.

Google documentation:
- https://support.google.com/a/answer/176600
- https://support.google.com/accounts/answer/185833

Set the platform backend `FRONTEND_URL` to the employee-facing HRMS origin so reset
links return to this HRMS, not localhost. Use the public HTTPS address for production
setup links and credential entry. The configured hostname must route `/reset-password`.
Use the native integration's test-email action before onboarding real employees.

### GitHub Secrets deployment

Production deployment reads `EMAIL_ENABLED`, `SMTP_HOST`, `SMTP_PORT`,
`SMTP_USERNAME`, `SMTP_PASSWORD`, and `EMAIL_FROM` from GitHub Actions secrets.
`EMAIL_FROM` accepts either an email address or `Newtuple HRMS <address@example.com>`.
The workflow streams the values over SSH into a one-off installer container;
credentials are not included in release artifacts or command arguments. The installer
validates SMTP authentication, then stores the tenant SMTP integration through the
native public API. This does not send a test email or any employee email.

With `EMAIL_ENABLED=true`, missing or invalid values fail the email configuration
step. False or unset skips synchronization and preserves existing integration
settings; it is not a global email kill switch. While synchronization is enabled,
GitHub secrets are the deployment source of truth and replace SMTP settings on
each release. The platform's existing `HRMS_PUBLIC_URL` supplies `FRONTEND_URL`.
Email synchronization runs after application deployment; an email configuration
failure does not roll back the deployed application.

## Password setup and delivery limits

The native invitation API rejects existing tenant members. HRMS therefore uses the
native forgot-password API to request a one-hour secure setup link for provisioned
password accounts. No password or reset token passes through the HRMS UI/service.
The native Password Reset email template remains editable in Settings → Email Templates.
It is also used for ordinary password recovery, so its wording should fit both cases.

Existing Google-authenticated accounts are activated for Google sign-in without a
password email. Selecting Google Workspace as an outbound email provider does not
by itself configure Google SSO.

Before activation, the HRMS action checks for a configured tenant email provider.
That check does not validate credentials or guarantee delivery. The native reset API
returns a generic response and does not expose provider delivery failures; the UI
therefore says **requested**, never **delivered**. An email exception leaves the
account active and reports failure. Reusing the same operation key never sends a
second email after an uncertain outcome. A deliberate new setup request uses a new key.

Activation can add the native default viewer role. The action removes that automatic
addition if viewer was not previously assigned, preserving the approved role set.
Existing custom or elevated roles are always checked through native role APIs rather
than trusting the employee record's displayed role.

## Verification

Tests cover linking existing accounts, new provisioning, idempotency, permission
boundaries, tenant/email mismatch, suspended accounts, missing email configuration,
email timeout and Google sign-in behavior. Production email delivery still requires
the sender credential, correct public URL, and a successful test email.
