# Native Employee onboarding

Employee onboarding uses the tenant's published, active HRMS.Employee workflow. FR-06 is the registration form in the local tenant. Fields, picklists, forms, states, required transition inputs, guards, workflow access and role grants are native configuration. The platform source is unchanged.

## Configured local journey

| State | Native form | Owner |
| --- | --- | --- |
| Employee Registration | FR-06 Employee form: identity and job details; no work email | HR Full / Superadmin |
| Email Setup | Employee Email Setup: work email | Superadmin |
| Account Approval | Employee Account Approval: system approval indicator | Superadmin approves the native Users account |
| Profile Completion Pending | Employee Profile Completion: addresses, career, skills, experience, bank details and documents | Onboarding Employee, own record only |
| IT & Workspace Provisioning | Employee IT and Workplace Provisioning: access confirmations and asset references | Office Admin |
| Onboarding Verification | Employee HR Verification: review notes, complete or request profile corrections | HR Full / Superadmin |
| Onboarding Completed | Employee Details: consolidated employee data | Intended native employee role is restored |

Every stage updates the same Employee entity. Previous values are presented read-only when permitted by native field permissions. Office Admin cannot see bank/address/document fields. Required fields are checked on transitions, so later-stage fields do not prevent initial registration. Documents reuse the native document field and file-handler APIs. Provisioning confirmations record work performed manually; they do not create external Google, GitHub, Slack or banking accounts.

## HRMS integration only

- Add employee resolves the active workflow's initial-state form and creates/enrols an Employee through public platform APIs. When that form omits work email, no account is created at registration.
- My Tasks projects native enrollments, permitted transitions and pinned state-form snapshots. Edits use the human token, are restricted to current-form editable fields, and preserve other values. Actions use native transition authorization/validation. The earlier custom onboarding case/checklist is not reinstated.
- A polling bridge (30 seconds) handles the cross-entity Users handoff. At startup it resolves the tenant's native Employee Account Approval, Employee Profile Completion, Employee Final HR Sign-off and Employee Details forms through public APIs. Explicit `HRMS_EMPLOYEE_*_FORM_ID` values override name lookup. Missing, archived or ambiguous forms fail closed and are logged and retried; local UUIDs are never copied into production. State matching uses the resolved form IDs, not state labels.
- At the approval form, the bridge creates a pending native user and links its ID. It never approves the user itself. After native approval it requests the native password-setup email, then records approval via the native transition API. The current native email subject is “Reset your password”. Local mail is captured at http://localhost:8025.
- The temporary native `hrms_onboarding_employee` role limits the portal to My Tasks. HRMS checks ownership and blocks other module APIs; native permissions still apply. Native row conditions currently support literal values, so own-employee enforcement belongs in this integration. The platform upstream must remain private, as required by the existing HRMS gateway architecture.
- At the configured completion form, the bridge assigns the intended native role stored in `hrms_role`. It does not maintain a second permissions catalog. Account operations are journaled; uncertain creation/email outcomes stop for administrator reconciliation instead of duplicating requests.

## Configuration and deployment

Edit fields in Settings → Fields, compose forms in Settings → Forms, and attach the required form versions to states in the Employee workflow. Publish the workflow after changing pinned form versions. Existing enrollments remain on their published version; they are not silently migrated.

Deployment validates the lifecycle forms against the active published Employee workflow. If the restricted Onboarding Employee role is absent, a dedicated public-API bootstrap creates it with only Employee view/edit, profile fields and profile transitions. Existing role configuration is preserved. The HRMS gateway enforces access to the linked employee's own record and blocks other modules. No installer overwrites tenant-authored forms or workflow definitions. Existing workflow enrollments remain pinned to their published version.

The native validator reports warnings about the older legacy Employee schema's field types and notice-period field, and the approval guard being supplied by the integration. The native dry run passes. These warnings do not require modifying the core platform.

## Employee-owned profile task and progress

`HRMS_EMPLOYEE_PROFILE_FORM_ID` identifies the native profile form for assignment. The bridge resolves `Employee.platform_user_id` and uses the native assignee API, which creates the native assignment notification and history. Native Assign User currently accepts a fixed user or the originator; choosing originator here would assign HR, not the employee. No core changes or hardcoded employee IDs are used.

At this configured step, My Tasks offers actions only to the linked employee; other authorized viewers see the profile as read-only through the HRMS form API. After leaving the step the bridge clears only its employee assignment, preserving any different assignee. Later work is surfaced using native transition grants for Office Admin/HR. The employee's own status stays visible independently of actionable task counts and refreshes every 30 seconds. Modules remain restricted until the configured completion bridge grants the intended native role.

Local verification uses Mailpit at http://localhost:8025; it does not deliver to external mailboxes. For real delivery, configure the native SMTP integration with host, port, TLS, username, password/app password, sender email/name and optional reply-to, and test it. The native auth email links use the deployment's `FRONTEND_URL`; production must use the externally reachable HTTPS HRMS address. Email Setup currently records an email address; an actual working mailbox must exist separately. The native setup/reset link expires after one hour and does not bypass login or onboarding permissions.

## Verification returns (local workflow version 4)

The native workflow now offers **Request employee corrections** and **Request Office Admin corrections** from Onboarding Verification. Both require the existing `hr_verification_notes` field and a native `field_present` guard. HRMS also rejects whitespace-only notes, which native presence checks do not reject. The field is labelled **Verification notes / correction reason** consistently in every form that contributes it; native publication requires shared field definitions to agree.

The profile and provisioning forms include the feedback field. Native Employee/Office Admin grants permit viewing but not editing feedback; HR Full can edit it and execute both return transitions. The existing Super Admin authorization is retained. Task rows and opened forms display feedback prominently, including records on older workflow versions. This is the latest saved verifier feedback; it is not a replacement for native record/audit history.

Employee corrections resolve to the linked user through the native assignment API and its assignment notification/audit. Provisioning corrections appear in the Office Admin role queue, using native transition permissions, rather than choosing an arbitrary named Office Admin. The HRMS task counter/bell reflects work available to the current user. Native core remains unchanged.

`scripts/configure-hrms-onboarding-returns.py` is an explicit configuration utility, not an installer. It requires a human Settings bearer token in `HRMS_SETTINGS_TOKEN`, the API base URL, tenant ID, machine name and a backup directory. It backs up definitions/forms/grants, updates the state forms, validates and publishes a new workflow version, then updates the native role grants. Do not run against production without separately reviewing and authorizing its configuration.

**Version limitation:** existing enrollments retain their pinned published definitions. Ira remains on version 2; her feedback display is fixed, but her workflow does not acquire the new Office Admin return transition. The available native public API has no in-place enrollment-version migration. No employee was restarted, re-enrolled, transitioned for testing or modified directly in the database. Newly enrolled employees use version 4.

Validation: 17 focused HRMS tests, production frontend build, browser render check for task/form feedback, and the native transition evaluator against both published return transitions (missing/empty reason blocked, supplied reason accepted). No live employee profile was submitted during testing.

## Current sequence (local version 5)

The active native workflow now uses Employee Registration → Email Setup → Account Approval → Profile Completion Pending → Onboarding Verification → IT & Workspace Provisioning → Onboarding Completed. Existing states/forms are reused. The employee's submit transition goes to HR verification; HR approval goes to IT; Office Admin completion goes to the terminal state. HR's required-reason return transition goes back to profile completion, whose next submission returns directly to HR. The older HR-to-IT correction transition is absent from this new definition because IT work now starts only after HR approval.

The current explicit configuration utility is `scripts/configure-hrms-onboarding-sequence.py`. The earlier returns utility documents the preceding sequence and supplies the shared native role-grant helper; do not rerun its old sequence configuration for this workflow. Transition keys for the three forward steps are version-specific so earlier enrolled versions retain their authorized actions. All new routes and required fields are configured on the native published definition.

Feedback presentation now follows the configured employee-profile form ID. A nonempty reason appears as an outstanding correction only while the record is in that step. After submission the banner disappears from My Tasks and the opened form; saved verifier notes remain available in previous details/native history. Read-only feedback is not repeated as an active provisioning form field. HR can still edit verification notes in the native verification form. Existing enrollments, including Ira's older version, receive this presentation fix but retain their pinned native transition graph.

Validation: 19 focused HRMS tests including suppression after submission and read-only feedback retention. The three native forward transitions and the correction loop are inspected against the published definition. Production is unchanged.

### Final HR sign-off (local version 6)

IT & Workspace Provisioning now leads to Final HR Sign-off, then Onboarding Completed. The prior steps are unchanged. The final state uses native FR-37 Employee Final HR Sign-off (a separate copy of the verification form); native role grants allow Office Admin to hand over and HR Full to complete. Super Admin remains authorized by native platform permissions.

The optional HRMS_EMPLOYEE_SIGNOFF_FORM_ID integration setting identifies this state by its native form, without hardcoding its name. Employee creation already stores the initiating HR user as owner_id. Since the native audit creator is the application service, the HRMS integration resolves owner_id and sets the native assignee through the public API. My Tasks and its action/form APIs restrict final sign-off to that owner, including when another Super Admin views the record. Native assignment validates the recipient and emits its normal notification/audit. No additional portal access is granted in this state: the existing completion-form bridge grants the intended native role only in Onboarding Completed.

Apply configuration explicitly with scripts/configure-hrms-onboarding-signoff.py using a human Settings token; its backup contains the resulting form ID to set in the environment. Existing enrollments retain their pinned workflow version. No production configuration is changed automatically.

### HR onboarding overview

HR Cockpit's Onboarding tab lists human-authorized native Employee enrollments through the read-only `/hrms/onboarding-tracker` endpoint, gated by the native `onboarding:view` capability. It includes work assigned to others, whereas My Tasks retains its existing actionable-item filter. Terminal tags drive the Completed filter; state labels/order come from the enrollment's pinned native definition. Creator/assignee names come from tenant user relationships. The current form reuses EmployeeWorkflowActions in read-only mode when the viewer has no available actions. This overview performs no enrollment, workflow publication or employee writes.

### Asset issuance during provisioning

The opt-in `HRMS_ASSET_EMPLOYEE_RELATION=ISSUED_TO` integration displays linked assets in place of the existing `issued_asset_references` input when that field is visible on the current native form. The field remains in native configuration and retains its existing transition requirements. GitHub, Slack, subscriptions, workflow states, transitions, role grants and enrolled workflow versions are unchanged.

An authorized actor with a current workflow action, editable asset-reference field and `asset:manage` can choose an available asset. The employee is fixed to the current onboarding record. The UI reuses the inventory issue form and the API reuses AssetService's validation, native issue transition and retry journal. Multiple assets can be issued to one employee. Each issued Asset records its employee and gains a native Asset → Employee `ISSUED_TO` relation through the public platform API; conflicting employee links are rejected. Inventory and onboarding read the same issued Asset records.

The custom HRMS adapter renders the selector and linked-assets summary, validates workflow authorization, and derives the existing transition evidence from issued assets. It does not independently advance onboarding. The Office Admin still explicitly submits the configured transition to Final HR Sign-off. Completed/read-only forms show assigned assets without an issue action. Previous text references remain available as collapsed saved evidence, but are not treated as proof of a real asset assignment when the transition requires issuance.

`scripts/configure-hrms-onboarding-assets.py` creates the native relation definition and updates only the provisioning form description using a human Settings token. It backs up definitions and asserts the form fields and published workflows are unchanged. It does not publish a workflow or alter existing enrollments. Production deployment now defaults HRMS_ASSET_EMPLOYEE_RELATION to ISSUED_TO and ensures the native relationship exists through the installer API before the application starts. Set HRMS_ASSET_EMPLOYEE_RELATION= (an explicitly empty value) in the VM production.env to disable the integration on the next deployment. The installer preserves existing definitions and does not change forms or workflows. Native generic form rendering is unchanged; the asset selector is an HRMS integration component.

### Resolved verification feedback

HRMS derives feedback presentation from the enrollment's pinned native transition graph. The required correction-reason return to the configured employee profile form identifies verification. In the correction destination feedback is requested; in verification it awaits review; forward states after verification show it as resolved. Traversal excludes correction returns. Unknown configurations do not claim resolution. No workflow publication, employee write, extra status field or enrollment migration is necessary.

Resolved notes are removed from the active form for all roles, including Super Admin, and shown only in collapsed Previous feedback with a Resolved by HR label. The original note and native audit remain intact. The form API also rejects attempts to edit the historical note in those later states. Native verification and return-transition requirements remain unchanged. This presentation adapter also works for already completed records on supported pinned definitions.
