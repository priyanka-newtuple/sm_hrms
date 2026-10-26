# HRMS configuration releases

Native Settings edits are not automatically committed to Git. Use the server-side
`hrms_app.configuration_cli` to export and review a release through public native APIs.
No records, users, assignments, files, integrations or database dumps are exported.

## Supported release objects

Entity definitions, relationship declarations and named relationship definitions,
picklists, latest field versions, latest method blocks, legacy forms, tenant
email/document templates, active workflows and explicitly selected scoped role grants. Exact references are
remapped into destination IDs. Historic method/field pins that cannot be resolved
to the selected versions, connectors, external URLs, literal recipients and unknown
IDs block export. They are never silently changed to latest.

This initial adapter does not promote global role capabilities, user memberships,
services, categories, standalone automations, branding or arbitrary display settings.
These require explicitly reviewed native configuration before release. Do not treat
this package as a whole-tenant export. The export dependency checks must pass before
the package can be adopted. Permissions must be verified with the actual UAT roles.

## Commands

Run in the installer environment with `PLATFORM_API_URL`, `HRMS_ORGANIZATION_ID`,
`HRMS_INSTALL_EMAIL`, `HRMS_INSTALL_PASSWORD` and `HRMS_APP_DATABASE_URL` supplied
securely by the existing container environment. Never pass credentials as arguments.

```text
python -m hrms_app.configuration_cli export --entity hrms_offer --entity HRMS.Employee --entity HRMS.Offboarding --role superadmin --role hrms_hr_full --role hrms_application_service --output candidate.json --write-bindings source-bindings.json
python -m hrms_app.configuration_cli validate --package candidate.json
python -m hrms_app.configuration_cli plan --package candidate.json --output plan.json
python -m hrms_app.configuration_cli apply --package candidate.json --plan plan.json
python -m hrms_app.configuration_cli status
```

Export from local; plan/apply against the destination. `candidate.json` in this
directory is the reviewed-for-sensitive-content local snapshot from 26 October:
147 configuration objects, including the three workflows, scoped grants for the
three named roles, and their supporting definitions. It is **not activated** for
production. The production comparison and initial adoption have not been performed.

For duplicate method names, pass `--bindings destination-bindings.json` to plan and
apply, with package keys mapped to the intended destination method IDs. Never use
source IDs in another environment. Successful adoption saves destination bindings
in the tenant-scoped journal for subsequent deployments. `--write-bindings` writes
source mappings separately for verifying an export against its source; these are
not part of the portable package. Rename/remapping changes need explicit review.

Role promotion manages only entity, field, workflow and transition grants within
the package's explicit scope. It preserves unrelated grants, global capabilities
and memberships. Workflow access is granted before transition access. Existing
destination roles must already have been created through the native installer or
Settings. This tool never creates users or silently changes their roles.
Review the exported values for personal information before committing. A plan is
bound to the tenant, baseline, desired package and current snapshot. Plan output
contains checksums/decisions, not record data. Differing pre-existing configuration
is a conflict, not implicit approval to overwrite it. Reconcile it through Settings
or change the desired package and produce a new plan. Matching existing objects can
be adopted using a reviewed apply.

After successful initial adoption, save the approved package as
`configuration/hrms/release.json`. The build validates it and includes it in the
checksummed artifact. Deployment applies it instead of the legacy seed installer;
this prevents competing installers from overwriting managed definitions. The
existing tenant/service identity and foundational permissions must already exist.
Without this file, deployment continues using the existing installer and prints
that managed configuration promotion is not enabled. No empty placeholder package
is considered a successful configuration release.

## Recovery and concurrency

Use a configuration change window: the native API does not support conditional
updates across resources. This tool serializes promotions per tenant and rechecks
all objects before writes, but cannot lock native Settings. Do not edit Settings
while a release is applying.

The HRMS application database stores the baseline, checksummed plan, write intent,
completed object keys and any created draft ID. On interruption, status becomes
failed/applying and retries stop rather than duplicating writes. If every native
object already matches the release, recover the checkpoint with:

```text
python -m hrms_app.configuration_cli reconcile --package candidate.json
```

Partial releases require reviewed forward repair through native Settings before
reconciliation. Existing human drafts are never overwritten. Workflow publication
creates a new version and leaves enrolled instances on their previous versions.
No delete endpoint, database restore, record enrollment or email-send operation is
part of promotion. Removing a managed object from the package requires a separate
retirement decision and blocks deployment.

The full rollout and remaining adapter coverage are tracked in
`design_docs/hrms_configuration_promotion.md`.

Super Admin can inspect **Settings → Organization → Release information** for
frontend/application revisions and the last recorded configuration promotion.
The panel explicitly distinguishes this from a live drift check.
