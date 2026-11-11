# Onboarding and Razorpay Payroll registration

The native Add Employee configuration now routes Employee Registration → Email Setup Google → Account Approval → Profile Completion Pending → Onboarding Verification → IT & Workspace Provisioning → Payroll Registration → Final HR Sign-off → Onboarding Completed.

HR Full and Super Admin can cancel any unfinished stage into Onboarding Cancelled. Cancellation does not change login access, delete the employee, or undo an already-created Payroll record. Final sign-off remains assigned to the originating HR user; profile completion remains assigned to the employee. The HRMS eligibility picker derives other candidates from native transition grants, excluding cancellation-only grants. Native Roles remains the source of transition authorization. Account Approval and Payroll Registration default to Super Admin.

## Configuration

GitHub Actions variable `HRMS_RAZORPAY_MODE` accepts `mock`, `live`, or `disabled`. The production deployment workflow defaults to `mock` for current UAT. Local Compose defaults to `mock`; a standalone runtime defaults to `disabled`. No provider request is made in mock mode. Mock and live use the same registration orchestration, response fields, persistence and next transition. Keep `HRMS_RAZORPAY_MODE=mock` until live Payroll credentials are confirmed; credentials are ignored unless the mode is `live`.

Live requires GitHub secrets `HRMS_RAZORPAY_API_ID` (numeric) and `HRMS_RAZORPAY_API_KEY`, obtained from Razorpay Payroll Settings → API. Deployment transfers these over SSH into a private temporary Compose environment file, removes that file after deployment, and injects credentials only into the HRMS application container. Credentials are never stored in native forms or printed in deployment output. Changing the GitHub variable takes effect on the next deployment.

## Verified provider contract

Payroll API documentation (read 11 Nov 2026): https://documenter.getpostman.com/view/11662503/Tzm5HckE. All calls are `POST https://payroll.razorpay.com/api/people` with `auth: {id, key}`, `request: {type: "people", "sub-type": ...}` and `data`.

- `create`: `data: {email, name, type}` (`employee` or `contractor`) only. Response `status: "ok"`, `people-id`, `employee-id` (provider-assigned).
- `edit`: identifies the person by `email`; all other keys optional, including `employee-id` (the employer's employee number), `hiring-date`, `title`, `department`, `phone-number`, `pan`, `bank-account-number`, `bank-ifsc`, `manager-employee-id`, `manager-employee-type`, `state`, `pt-enabled` and previous-salary/tax keys.
- `view`: by `employee-id` only; there is no lookup by email.

No Payroll sandbox is documented (the Payments sandbox guide does not apply). Do not point an assumed sandbox at live Payroll. The live adapter is contract-tested with intercepted HTTP, not certified against a real Payroll account.

## Registration flow

1. The Payroll stage is the Employee workflow stage whose native form contains `razorpay_employee_id`, read from the published definition. Renaming the form in Settings or a restart cannot make HRMS skip registration.
2. On that stage, before registration, HRMS suggests the employee number: the digits of the HRMS employee code (EMP-0042 → 42) when unused, otherwise the next number after the highest one in use. HR approves to accept it, or changes and saves it first. Numbers must be positive whole numbers, unique in the tenant. People ID and mode are always read-only; after registration the number is read-only too. Field visibility and editing still follow native field permissions.
3. On approval HRMS calls `create` (name, work email, type), then `edit` with the employee number and, when present on the native record, `date_joined`, `designation`, `department`, `phone`, `bank_account_number`, `bank_ifsc`, `pan_number`, and the manager's Payroll number when the manager is registered. Empty or unconfigured fields are not sent. Add a native `pan_number` field (masked except for Payroll/HR) to send PAN; `pan_card` is a document and is not sent.
4. HRMS stores the employee number, People ID and mode on the employee and moves the workflow on. If the integration is disabled or the provider does not confirm, the transition is blocked with a clear message.

Mock mode makes no provider request. It answers like the provider (People ID `mock-<receipt>`) and keeps the requests it would have sent in the receipt, with bank and tax identifiers recorded only as `<provided>`. Live never stores request bodies.

## Retry safety and reconciliation

A tenant-scoped application journal records the request fingerprint (person details and employee number) before creation and persists progress before native writeback. A retry reuses the receipt and never creates twice:

- Write-back to HRMS failed: the stored result is written again.
- Profile `edit` failed: only the `edit` is repeated.
- `create` reply lost: the retry confirms the person with `edit` by email (which succeeds only for an existing person) and then applies the profile. If the person cannot be found, registration stays blocked for an administrator to check Razorpay Payroll; never delete that receipt until the provider confirms no person was created.

Receipts from the earlier create-only release keep their provider IDs and are not re-sent. Changing details, the employee number, or switching mock to live blocks replay. Use a new UAT employee for mock tests and reconcile mocked registrations before live rollout. Cancelled onboarding does not remove an existing Payroll employee.

## Configuration promotion and existing records

The release package uses existing guarded three-way native configuration promotion. Production edits must be compared and adopted before applying conflicting changes; do not force the package over newer production Settings. The office-admin and onboarding-employee transition grants receive a one-time native migration. Subsequent tenant edits are preserved. HR Full grants are managed in the release package.

Existing enrollments may remain pinned to their earlier published workflow version. Review and migrate them through the established native configuration migration process before expecting Payroll Registration or Cancel Onboarding on those records. No production records are rewritten by these code changes.

## UAT checks

1. Set mode to mock and apply the native release through guarded promotion.
2. Test each stage as its actor. Confirm HR/Office Admin cannot approve Payroll and the employee cannot cancel.
3. Confirm eligible assignment lists, direct employee profile assignment, and original HR final sign-off.
4. Open Payroll Registration: verify the suggested employee number (EMP-0042 → 42), that a duplicate or non-numeric number is rejected on save, and that HR can change it.
5. Approve Payroll: verify the chosen number, a `mock-` People ID and mock mode are saved, and progression to Final HR Sign-off.
6. Retry after a failed native writeback: verify the same IDs are retained.
7. Cancel at each unfinished stage: verify terminal status, no new Payroll call, and unchanged login access.
8. Verify mode disabled blocks Payroll approval. Before live, confirm Payroll credentials and real-account onboarding requirements with Razorpay.
