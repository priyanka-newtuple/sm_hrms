# HRMS offboarding

Implementation date: 22 October 2026.

## Architecture

`HRMS.Offboarding` is a separate native entity linked by `employee_id` to the existing `HRMS.Employee` record. The seed key is `hrms_offboarding`; the native platform generates the persisted workflow identifier. Runtime lookup resolves the active workflow by entity type. Employee records, onboarding history, comments and audit history are retained. No employee deletion or recreation occurs.

Native fields, method-library forms, states, transitions and role permissions are installed through public platform APIs. Later tenant edits to the published workflow and human permission revocations are preserved on installer reruns. HRMS-specific departure effects and clearance verification live in the HRMS application layer; native core is unchanged.

## Workflow

| State | Action | Next state |
| --- | --- | --- |
| Draft | Submit for approval | Pending approval |
| Pending approval | Request changes | Changes requested |
| Changes requested | Resubmit | Pending approval |
| Pending approval | Approve exit | Notice & handover |
| Notice & handover | Confirm departure | Departure confirmed |
| Departure confirmed | Start final clearance | Final clearance |
| Final clearance | Complete offboarding | Completed |
| Draft / Pending approval / Changes requested | Cancel request | Cancelled |
| Notice & handover | Approve withdrawal | Cancelled |

Completed and Cancelled are terminal states. Native transition grants and guards are checked before application effects. System verification fields are editable only by the application service in the installed field permissions; they are not user-editable in the HRMS form.

## Forms and employee effects

- **Exit details:** employee, exit type, date notified, requested and confirmed last working day, reason, supporting documents, HR notes and change/cancellation reason.
- **Handover and clearances:** handover owner/contact, handover evidence, assets/exception approval, external access removal evidence, timezone-aware HRMS access cutoff, ownership/allocations/pending-approvals clearance.
- **Final HR review:** settlement confirmation and evidence, exit interview notes, final documents and final review notes.

Approving an exit records notice dates while keeping the employee active. Changing approved dates requires a reason. HR explicitly selects **Confirm departure** at or after the cutoff: HRMS verifies account suspension, updates the employee's existing internal employment status to `offboarded`, and the directory displays **Inactive**. The employee record remains available for history. The cutoff is a gate on this action, not a scheduled automatic suspension job.

Withdrawing an approved notice clears notice information without deleting history. A departed employee cannot be reactivated by withdrawing an exit. Final completion requires all clearance statuses and explanatory evidence, plus verified departure and HRMS access removal.

## Integration and access

- HR Cockpit → Offboarding: list, search, include closed, create and edit exits.
- Workflows: native offboarding stages and records; the HRMS editor handles the departure effects.
- My Tasks / waiting actions: actionable offboarding cases, filtered by native transition permissions.
- Record details reuse native Activity and Comments; documents attach to the exit record.
- Related-record summaries show issued assets, allocations and direct-report employee codes. Lookup failures are displayed as errors rather than empty success.
- Initial roles: HR Full and Super Admin. Existing employee-access rules remain: HR handles ordinary employee accounts; Super Admin handles privileged accounts.

For the HR-only rollout, HR records evidence of external email/VPN removal, asset return, ownership transfer and settlement. This feature does **not** automatically return assets, end allocations, reassign reports/approvals, execute payroll settlement, generate legal letters, or disable external-provider accounts. Final letters can be uploaded as documents. These integrations must not be inferred from a checked clearance field.

## Installation and activation

The standard HRMS installer now invokes `install_offboarding`. It creates missing configuration and additive initial role grants. The installer uses only public native APIs; its installation marker and operation journal are in the HRMS application's own database.

For the existing local Docker setup, after Docker Desktop's Linux engine is running:

```powershell
./scripts/hrms-local.ps1 native-up
docker compose --env-file .hrms.local.env -f docker-compose.hrms.yml --profile native run --rm platform-install python -m hrms_app.install_offboarding
```

The second command explicitly installs the feature even when an old completed installer container is retained. Refresh the browser after deployment. Do not run the local setup against production credentials; use the deployment environment's equivalent build/install process.

## Verification and UAT

Source validation: frontend production build; native boundary verification; regression tests for employee/workflow/lifecycle and offboarding permission checks, notice, withdrawal, cutoff dates, clearance evidence and interrupted transitions.

Local activation verified on 23 October 2026: fixed native date-engine validation, resolved the generated workflow identity, and excluded retired workflow references when updating grants. The full installer and Docker startup succeeded; localhost:5182 returned HTTP 200. Authenticated offboarding configuration, list, inbox and workflow gateway checks passed. All 73 targeted regression tests passed. Interactive browser UAT remains pending. Use a disposable employee for UAT:

1. Create and save an exit draft, upload supporting evidence; confirm it appears in Cockpit, Workflows and My Tasks.
2. Request changes, resubmit, approve notice; verify directory notice information and that the account stays active.
3. Attempt departure before the cutoff; verify it is blocked without access changes.
4. Confirm departure after cutoff; verify account suspension and **Inactive** in the directory, with history retained.
5. Verify completion fails with missing clearance evidence; complete all clearances and finish.
6. Verify a separate approved notice can be withdrawn, while a departed employee cannot be reactivated through this flow.
7. Verify employee-role denial and revoked native transition/field permissions; verify privileged-account exits require Super Admin.
8. Test upload/download, Activity and Comments with HR permissions and after the case is closed.

## Employee participation (23 October 2026)

New workflow versions add **Employee handover** between approval and **Notice & handover**. HR chooses an eligible exit approver and HR coordinator and records an employee-confirmed personal contact email. The employee must have an active linked platform account. Draft cancellation goes to a private **Discarded** terminal state.

- Native `entity.assign_user` state actions assign the draft/changes to its originator, approval to the selected approver, employee handover to the linked employee, and later work to the HR coordinator.
- Native `mail.send_email` actions and editable native email templates notify the agreed contact address on non-draft state entry. Delivery requires configured SMTP and the native action worker; these are queued emails, not a synchronous delivery guarantee. Local mail is captured at http://localhost:8025.
- Employees can follow their own formally submitted exit under **My Tasks → Your offboarding**. Their current assigned handover form includes work handover, asset-return arrangements, questions and confirmation. Submitting it advances the native workflow back to HR; HR can request an updated handover.
- The HRMS API enforces tenant, linked employee identity, current native assignment, configured state/form, allowed employee fields, concurrency and idempotency. Employees cannot approve exits, change dates/recipients or read HR notes, settlement evidence, internal Activity/Comments or other employees' exits.
- Employee submissions are recorded in the HRMS operation audit; native records, assignments, forms, transitions and emails remain the platform system of record. No native platform source was changed.
- Existing enrolled cases retain their pinned workflow version and history. The HR editor explains when a case predates participation. Do not force-migrate existing cases or assume new notifications were sent retroactively.
- After departure, the suspended HRMS account cannot open the form; stage emails continue to the agreed personal address. No external account deletion is implied.

Validation: 61 targeted unit/regression tests passed; frontend production build passed; platform boundary check passed. One broader existing route-integration test was excluded after it stalled in the local test environment. Browser UAT should cover HR and employee sessions, native email delivery/failure handling, returned handover, and legacy cases. The local API smoke helper `applications/hrms_api/tools/check_offboarding_participation.py` uses only public APIs, requires captured local SMTP, and archives its disposable records and suspends its test account afterward.

The HRMS Compose stacks now run the native `worker_main.py` in a separate `platform-worker` service. The API keeps its worker flag disabled to avoid duplicate in-process workers. Starting `platform-web` also starts the worker, after the native installer completes. Production deployment configuration is updated in source only; production was not deployed.

Live local verification passed: draft hidden from employee, submitted status visible, native assignment to employee, safe field projection, employee save and native handover submission, return to HR, and native SMTP delivery into Mailpit. Disposable tenant test records were archived and test accounts suspended. An initial registration using an out-of-tenant example.com address was rejected by tenant-scoped approval before any employee/exit record was created; the local test now uses the tenant registration domain. No real employee was transitioned during these checks.
