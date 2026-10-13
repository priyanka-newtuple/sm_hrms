# Asset inventory and employee issuance

Scope: add/edit/search inventory, issue an available asset to an active employee, and show employees their own issued equipment. Returns, maintenance, retirement and receipt approval are not included in this version.

The native `HRMS.Asset` entity, Asset inventory method form, Field Library fields, category/condition picklists and Available → Issued workflow own the configuration and records. Installation uses public platform APIs and preserves existing forms/workflows. Fields added to the native form render in the inventory editor. Republish the workflow after changing its pinned form or select options, as with other native workflows.

Native permissions `asset:view` (own issued assets) and `asset:manage` (all inventory, add/edit/issue) appear in Settings → Roles & Permissions. The initial setup grants view to existing human roles and manage to Super Admin and Office Admin. The application-owned, tenant-scoped feature checkpoint prevents later deployments from re-granting revoked permissions. New roles receive permissions through native Settings. There is no HRMS permission editor or runtime role-name policy.

The HRMS API checks the human's effective native grants before using the restricted service adapter. Employee selections come from active employee records in the same tenant. Employees do not receive inventory notes, custom inventory fields, or other employees' assignments. Workflow state remains native; the issue command checks available native transitions and runs the platform transition.

Inventory tracks tag, name, category, serial, manufacturer/model, location, purchase date, warranty expiry, condition and notes. Issuance stores employee, issue date, issuing user and employee-visible note. Tags and nonempty serial numbers are unique ignoring case across HRMS commands. Issue date cannot be in the future. Issued assets cannot be issued again or have their employee changed through editing.

Commands use the existing tenant lock, durable operation journal, operation marker and native transition idempotency. Unknown upstream outcomes reserve mutations until the same operation is replayed; definite transition rejection restores the prior inventory data. Actions retain human attribution in the application audit. Native configuration administrators remain trusted to edit tenant configuration through the existing human-token gateway.

Local startup: `powershell -NoProfile -File scripts/hrms-local.ps1 native-up`. Open `/hrms/assets`. Production uses the same installer on deployment; no production changes are made merely by local startup.
