# Onboarding and Razorpay Payroll registration

The native Add Employee configuration now routes Employee Registration → Email Setup Google → Account Approval → Profile Completion Pending → Onboarding Verification → IT & Workspace Provisioning → Payroll Registration → Final HR Sign-off → Onboarding Completed.

HR Full and Super Admin can cancel any unfinished stage into Onboarding Cancelled. Cancellation does not change login access, delete the employee, or undo an already-created Payroll record. Final sign-off remains assigned to the originating HR user; profile completion remains assigned to the employee. The HRMS eligibility picker derives other candidates from native transition grants, excluding cancellation-only grants. Native Roles remains the source of transition authorization. Account Approval and Payroll Registration default to Super Admin.

## Configuration

GitHub Actions variable `HRMS_RAZORPAY_MODE` accepts `mock`, `live`, or `disabled`. The production deployment workflow defaults to `mock` for current UAT. Local Compose defaults to `mock`; a standalone runtime defaults to `disabled`. No provider request is made in mock mode. Mock and live use the same registration orchestration, response fields, persistence and next transition.

Live requires GitHub secrets `HRMS_RAZORPAY_API_ID` (numeric) and `HRMS_RAZORPAY_API_KEY`, obtained from Razorpay Payroll Settings → API. Deployment transfers these over SSH into a private temporary Compose environment file, removes that file after deployment, and injects credentials only into the HRMS application container. Credentials are never stored in native forms or printed in deployment output. Changing the GitHub variable takes effect on the next deployment.

## Verified provider contract

The supplied sandbox guide https://razorpay.com/docs/api/sandbox-setup documents Payments test/live API keys. It does not establish a sandbox for Payroll employee creation. Do not use Payments test credentials as Payroll credentials or point an assumed sandbox at live Payroll.

Payroll API documentation: https://documenter.getpostman.com/view/11662503/Tzm5HckE

Create a person: POST https://payroll.razorpay.com/api/people

Request: `auth: {id, key}`, `request: {type: "people", "sub-type": "create"}`, `data: {email, name, type}`. Type is employee or contractor. Response: `status: "ok"`, `people-id`, `employee-id`.

HRMS preserves its employee ID and employee code. Native read-only fields store Razorpay Employee ID, Razorpay People ID and integration mode. The approval screen labels mock/live explicitly. This creates a person record only; salary, bank provisioning and payouts are outside scope.

A provider-hosted Payroll sandbox is not enabled because its availability and credentials have not been confirmed. Obtain written Payroll sandbox details from Razorpay before adding a sandbox mode. The live adapter is contract-tested with intercepted HTTP, not certified against a real Payroll account.

## Retry safety and reconciliation

A tenant-scoped application journal records the request fingerprint before creation and persists the provider IDs before native writeback. If writeback fails, retry reuses the receipt. If the provider response is lost or invalid, creation stops as uncertain: it will not blindly create another person. An administrator must inspect the provider account and reconcile the receipt against the actual employee. Never delete an uncertain receipt until the provider confirms no employee was created. No automated reconciliation command is provided in this release.

Changing details or switching an existing registration from mock to live blocks replay. Use a new UAT employee for mock tests; reconcile existing mocked registrations explicitly before live rollout. Cancelled onboarding does not remove an existing Payroll employee.

## Configuration promotion and existing records

The release package uses existing guarded three-way native configuration promotion. Production edits must be compared and adopted before applying conflicting changes; do not force the package over newer production Settings. The office-admin and onboarding-employee transition grants receive a one-time native migration. Subsequent tenant edits are preserved. HR Full grants are managed in the release package.

Existing enrollments may remain pinned to their earlier published workflow version. Review and migrate them through the established native configuration migration process before expecting Payroll Registration or Cancel Onboarding on those records. No production records are rewritten by these code changes.

## UAT checks

1. Set mode to mock and apply the native release through guarded promotion.
2. Test each stage as its actor. Confirm HR/Office Admin cannot approve Payroll and the employee cannot cancel.
3. Confirm eligible assignment lists, direct employee profile assignment, and original HR final sign-off.
4. Approve Payroll: verify separate IDs and mock mode, and progression to Final HR Sign-off.
5. Retry after a failed native writeback: verify the same IDs are retained.
6. Cancel at each unfinished stage: verify terminal status, no new Payroll call, and unchanged login access.
7. Verify mode disabled blocks Payroll approval. Before live, confirm Payroll credentials and real-account onboarding requirements with Razorpay.
