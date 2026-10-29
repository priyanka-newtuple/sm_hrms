# Five-stage native offboarding checklist

Implemented 29 October 2026. Not deployed to production.

## Native configuration

Stages: Not Started -> In Progress -> Submitted -> Pending Clearance -> Completed.
Six native form blocks contain employee information, handover, assets/access, HR administration, confidential feedback and declaration. Two administrative blocks contain routing, verified clearances and protected metadata. Fields, forms, transitions, assignments and email templates use public platform APIs. Native core is unchanged.

## Behavior and permissions

- HR creates the exit with an active linked employee, confirmed last working day/access cutoff, coordinator and confirmed notification email.
- Starting or saving the first draft enters In Progress. Subsequent draft saves do not send stage emails.
- Submission requires configured mandatory answers and explicit acknowledgment. No is accepted; N/A is allowed only for card/keys. Unanswered is distinct from No.
- Authenticated submitter, timestamp, revision and answer snapshots are recorded in protected native fields and linked to the operation journal. This is an electronic acknowledgment, not a cryptographic signature.
- Submitted answers are read-only. HR can reopen with a reason, clearing acknowledgment while retaining history. Deactivated employees cannot be assigned corrections.
- Employee answers do not return assets or verify clearance. Existing HR evidence checks and access-removal guards remain mandatory.
- HR can confirm departure at the cutoff before submission with a mandatory exception reason. This moves to Pending Clearance without inventing answers or acknowledgment. Confirming departure within Pending Clearance records a native transition and queues a refreshed status email.
- Stage entry, including creation and reopening, queues emails to the employee and HR coordinator. Confidential answers are excluded. Corrections are read inside the authenticated application.
- Employee access is restricted to their own record. Native field grants restrict feedback and submission history to HR Full, Super Admin and the application service.
- Office Admin records asset returns in Asset Management; HR verifies clearance evidence. No separate Office Admin offboarding task or new IT/manager role is added.
- Task links derive from HRMS_PUBLIC_URL, with GOOGLE_REDIRECT_URI origin as fallback. Templates use dynamic placeholders so local URLs are not promoted.

## Installation and promotion

Run `python -m hrms_app.install_offboarding_checklist` in the existing installer environment after base offboarding installation. It uses existing installer credentials and the HRMS app journal DSN.

The base installer also supports explicit opt-in `HRMS_OFFBOARDING_CHECKLIST_V2=true`. Do not enable this on every production startup. Install into a test tenant, verify, export/review using the existing configuration release process, and promote the reviewed package without bypassing drift protection.

The migration uses a tenant-scoped advisory lock and one-time marker. It refuses outstanding drafts and unrecognized custom stages, fields, transitions or SLA rules. It publishes a new version of the same workflow. Existing enrollments remain pinned to their previous versions; old transition grants and human workflow revocations are preserved. Retry after publication completes permissions without republishing. Subsequent Settings edits remain authoritative. No records, accounts or assets are deleted.

Before promotion verify real HR/employee access, confidential fields through native views, Mailpit stage emails, and a complete new exit. Existing cases require a separately reviewed migration to adopt the new stages.

## Verification

57 targeted backend tests and 3 employee-form UI tests passed, along with TypeScript and the platform-boundary check. Local native validation accepted the proposed graph with expanded fields (can_publish=true). It warned about service-populated verification fields because HRMS supplies them rather than user forms; these must remain protected. Installed native method references and rapid stage delivery have also been verified locally.

## Deployment-managed UAT email transport

Verified GitHub environment hrms-production on 29 October 2026: HRMS_EMAIL_MODE=capture and HRMS_UAT_INBOX_ENABLED=true. The existing release workflow passes these variables to the email configurator, which selects private Mailpit as the native default SMTP integration. Offboarding email actions specify recipients and template data only, never a transport override.

Testers use HR Cockpit > UAT email inbox. Switching the existing GitHub variable to live requires real SMTP secrets and disables the UAT inbox through existing deployment logic. No new email switch is introduced. The transport/configuration regression suite passed 39 tests. Production deployment is separate from these local checks.

## Local rollout finding (29 October 2026)

The local installer published the full native method-backed workflow successfully. An unchanged draft differed only by native from/from_state serialization; it is now reused after semantic comparison. Actual edited drafts still block. New field-library names are namespaced to prevent collisions with existing labels.

The first rapid-transition test exposed a native limitation: moving a case on can stop its remaining stage actions. Native core remains unchanged. HRMS now reconciles committed native enrollment and transition audit events into private HRMS.OffboardingNotice records. Each notification has one native mail action and moves to Delivered after the native executor reports success. The original exit can move on independently.

The application journal records each event/recipient pair and recovers a lost create response. Repeated reconciliation does not intentionally resend completed pairs. Native mail retries and SMTP delivery semantics still apply; this is not an exactly-once SMTP guarantee. Reconciliation depends on retained native audit events and runs every 30 seconds. Failures are logged and leave the cursor unchanged for retry. Notification records contain routing and stage information, never checklist answers.

The second local rapid-transition test captured all ten expected Mailpit messages (employee and coordinator at each of five stages). Repeating reconciliation produced no duplicates. Synthetic exit records were archived, with notification history retained. No employee account or access was changed.

Production requires the reviewed native configuration package, service audit/template read grants and the application worker. Existing enrollments are unchanged. Keep HRMS_EMAIL_MODE=capture and HRMS_UAT_INBOX_ENABLED=true during UAT.

## Participant progress visibility

My Tasks includes a View progress card for the employee and the case's native current, configured future, and historical individual assignees. Progress cards remain visible when another person owns the current step and do not increase pending-action counts. The native pinned workflow and native assignment audit events determine participation; no broad role-based record access is added. Historical audit entries must match the tenant and record.

The participant view contains only employee name/code, case identifier, confirmed last day and current stage. Employee answers, confidential feedback and HR evidence are excluded. Actual actions remain in the authorized task flow. Progress refreshes every 30 seconds while the page is visible; employee edits suspend detail refresh to preserve unsaved answers. Account deactivation still ends application access.
