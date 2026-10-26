# Multiple asset assignment

Asset Management > Assign assets selects one active employee, up to 50 available assets, one assignment date and an optional handover note. Existing holdings are shown. Search inventory by tag, serial/model; filter category/location. Review before assigning. The employee filter provides an employee asset view and preselects that employee when assigning more equipment. Onboarding provisioning opens the same panel with a fixed employee.

## Architecture

HRMS-only changes. Native HRMS.Asset records, native transition checks and employee relationships remain authoritative. The batch journal binds payload and actor to an idempotency key. Whole-selection preflight precedes writes; each individual assignment reuses AssetService._execute under the tenant lock. Per-asset journal keys permit safe replay. Completed child assignments are not repeated. Partial failures return item results; unfinished batches can be resumed by their initiating actor after closing/reloading the panel. Recovery listing filters both tenant and actor. Asset operations block conflicting changes to that asset, not unrelated existing inventory. Legacy/create operations without a resolved target retain conservative blocking.

Onboarding retains its native form/action checks and updates derived issued_asset_references with the human token. It does not complete the provisioning workflow step. Existing own-asset visibility and field privacy remain in place.

## UAT

1. Create two available assets, then assign both to one active employee. Verify native issued states, employee links, dates and activity; employee sees both in My assets.
2. Assign another asset to that same employee. Previously held equipment remains visible.
3. Use category/location searches, select across searches, review/remove items and verify no selection is lost.
4. Repeat from onboarding provisioning; verify evidence includes all assets and the workflow step remains unchanged.
5. Trigger a transient transition/relationship failure: successful items stay assigned, retry finishes only remaining operations. Close/reopen Assign assets and resume an unfinished batch.
6. Attempt assignment without asset:manage, using a foreign asset or employee, or an unavailable asset. Verify rejection without unauthorized changes.

## Remaining integration

Consolidated assignment email is not implemented in this change. Native workflow email actions are configured per asset transition; the public mail routes expose configuration/test mail rather than a general idempotent business-notification send API. Do not misuse test-mail or directly call SMTP. A tenant-configured batch notification integration is required before claiming one email per assignment. Existing configured native transition notifications remain unchanged.

Returns/reassignment, reservations, receipt acknowledgment, photo capture and bulk asset creation remain separate work.
