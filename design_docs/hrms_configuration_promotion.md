# HRMS configuration promotion

Status: tooling implemented; initial production comparison/adoption is still required.

## Implementation delivered (26 October 2026)

- Server-side export, schema validation, three-way plan, reviewed apply, reconciliation and status commands.
- Allowlisted native API adapters for entity definitions, named relationships and declarations, fields, methods, forms, picklists, tenant templates, workflows and scoped role grants.
- Tenant-scoped HRMS database journal and promotion lock; durable write intent and checkpoints; conflict, stale-plan and retirement protection.
- Verified local export, comparison and journal adoption: 147 objects match, with native writes explicitly disabled throughout adoption. Only the HRMS promotion journal was updated. A candidate snapshot is versioned in `configuration/hrms/candidate.json`; environment-specific method mappings are excluded.
- Deployment validates/bundles an activated `release.json`, checksums it with images, and uses the managed promoter instead of competing seed installers. Without an activated package it explicitly retains legacy behavior.
- Super Admin release information in Settings, including interface/application revisions and last recorded configuration status. This is not represented as a live drift check.
- Regression tests cover planning, data exclusions, tenant checks, unknown references, scoped grants, interrupted writes, reconciliation and deployment data-preservation behavior.

Remaining gates: production inventory and initial adoption, an isolated destination write exercise, and expanded adapters for global role capabilities, standalone automation schedules, services/categories and display/branding configuration. Exact historic method/field pins that cannot be faithfully resolved are rejected. New package coverage must be added explicitly; the current exporter is not a whole-tenant backup.

Interrupted partial promotions stop for reviewed forward repair; the current reconciliation command only completes a journal when every native value and pin already matches. It does not automatically replay ambiguous writes. Native Settings edits must be paused during promotion because public APIs do not offer conditional writes across objects.

## Outcome

Release approved HRMS code and native tenant configuration together, while preserving each environment's employee records, workflow history, files, users and secrets. Native Settings remains the configuration editor. Git holds the reviewed configuration to release, rather than becoming a second workflow engine.

The initial release scope is Offers, Add Employee and Employee Offboarding, with their actual dependencies. Asset and other module dependencies must be included or explicitly bound when these workflows reference them; selecting three workflows does not imply they are independent.

## Two separate causes of differences

1. **Application release:** missing Offers tabs, an Offboarding “Soon” screen, obsolete navigation and the favicon can reflect an old frontend bundle. Confirm the running frontend, HRMS API and native platform image revisions and the last successful deployment. A successful build or a commit on main does not prove deployment succeeded. Check browser caching only after checking the served build.
2. **Tenant configuration:** workflows, forms, fields, templates and role permissions edited in Settings are database state. A Git push does not export them. Compare configuration separately from application revisions.

Screenshots also show different users and roles. Verify equivalent roles and capabilities before treating differences in visible navigation as configuration drift.

## Ownership and exclusions

| Promote as reviewed configuration | Keep environment-specific |
| --- | --- |
| Entity definitions and relationship declarations | Employee, candidate, offer and exit records |
| Field definitions and referenced field versions | Workflow instances, tasks, approvals and audit history |
| Method/form blocks and exact referenced versions | User accounts, role assignments and assignee identities |
| Workflow definitions, states, transitions and guards | SMTP credentials, API keys, service credentials and tokens |
| Required picklists and declarative action definitions | SMTP mode, hostnames, callback URLs and integration connections |
| Offer/document and notification templates | Generated documents, uploaded files and email messages |
| Reviewed role definitions and scoped permission changes | Auto-number counters and other runtime state |
| Explicitly selected display/module settings | Environment organization identity and deployment paths |

Do not export an entire tenant database. Do not reset databases or replace volumes during deployment. Use bindings for environment-specific dependencies; never commit credentials, real recipient addresses or user IDs in configuration packages. Template content and defaults require review for personal data as well as secrets.

## Architecture

- Put exporter, planner and promotion orchestration under `applications/hrms_api/hrms_app/`; use public native APIs exclusively.
- Store package definitions under `configuration/hrms/`, with a schema version, release identifier, selected modules, objects, dependency references and checksum.
- Store deployment baseline, resolved object/version IDs and operation checkpoints in HRMS-owned persistence, scoped by organization and package. Never query or modify native database tables.
- Keep release diagnostics in the HRMS skin and behind explicit configuration administration permission.
- Leave native platform source and native Settings behavior unchanged.
- Use a dedicated authorized installer identity on the server. Interactive configuration actions retain the human token through the existing gateway. Never expose the installer token to the browser.

## Package and identity rules

Every object needs a unique stable package key. Entity type names and field keys are suitable native keys. Workflow families need an explicit mapping to a package key; generated machine identifiers can differ between environments. Method names alone are insufficient because they may be renamed or duplicated. Templates, methods, categories, services and roles also need explicit mappings when native identifiers are environment-specific.

References must identify both the object and, where applicable, the exact version/content checksum. Resolve references to destination IDs during promotion. Preserve the source-to-package mapping outside runtime records. Reject ambiguous matches, unresolved references, foreign-tenant objects and unsupported configuration rather than guessing or silently omitting them.

The export must be deterministic: exclude timestamps and generated IDs from semantic content, sort unordered collections, and preserve order where it affects forms, states or behavior. Keep version pins meaningful rather than replacing them with “latest.”

## Native API findings and verification gates

The following capabilities exist in the inspected repository. Complete contract and runtime tests before implementing each write adapter.

| Configuration | Native interface | Promotion consideration |
| --- | --- | --- |
| Entity types | `/entity-types`, `/entity-types/{name}` | PATCH mutable fields; inspect existing installer use of PUT rather than copying it into the new adapter. |
| Relationships | Entity relation and relation-declaration endpoints | Map both entity type references; preserve cardinality and source intent. |
| Fields | `/field-library/fields`, `/{id}/versions` | Field keys are stable; field type/settings are versioned. Export the pinned version. |
| Method blocks | `/method-library/methods`, `/{id}/fields`, `/{id}/versions` | Latest detail returns fields; verify how historical pinned field lists can be obtained. Version metadata alone is insufficient. |
| Forms | `/forms/config` | Preserve field library links, schema keys and any active legacy forms still used. |
| Workflows | `/workflow-state-machines`, `/validate`, family `/draft`, draft `/{id}/publish` | Validate with resolved dependencies; protect unpublished human drafts and publish a new version. |
| Templates | `/email-templates` | Promote template definitions, never sent messages or generated offer PDFs. |
| Roles | `/roles` and role update endpoints | Workflow access must exist before related transition permissions. Preserve unrelated grants and explicit revocations. |

Audit picklists, actions, automation rules, connectors, guards, services and display settings for complete public API support. Native action configuration may contain recipients or connection IDs: treat these as environment bindings, not portable values.

If the public API cannot return an exact historical method version with its fields, mark that workflow export as blocked. Do not substitute the latest method, reconstruct history from a database, or change native core within this HRMS task. Resolve the capability gap explicitly before claiming full export coverage.

The existing `install_offer_documents.py` expects an existing `hrms_offer` workflow. Merely running this installer is not a substitute for capturing the configured Offers workflow. The deployment entry point also needs an explicit, tested integration for approved offer configuration.

## Implementation sequence

### 1. Establish the baseline and inventory

- Check Git revision, build metadata and deployed image revisions separately for all services.
- Inventory selected local workflows and their complete dependency graph through native APIs.
- Inventory production through an authorized read-only process.
- Produce a coverage report listing supported objects, environment bindings, ambiguous matches and unsupported dependencies.
- Establish explicit package keys and source/destination mappings.
- Review the initial package for secrets and personal data before committing it.

Do not automatically declare an existing production object to be managed merely because its display name matches.

### 2. Build export and validation

- Add a versioned, strict package schema and deterministic serialization.
- Export selected active workflows plus every referenced definition/version, including dependencies shared with other modules.
- Validate organization scope, uniqueness, schema compatibility, dependency completeness and allowed object kinds.
- Reject raw user IDs, connection credentials and unbound environment references.
- Generate a human-readable inventory and checksum alongside the package.
- Test export against the running local platform without writing to it.

### 3. Build a three-way comparison

Compare the previous successfully deployed configuration baseline, desired release package and current destination configuration. Comparison happens at each managed object's semantic content, with precise changed paths reported for review.

| Situation | Decision |
| --- | --- |
| Destination already equals desired | No write; verify and retain mapping. |
| Destination equals baseline; desired changed | Plan an update. |
| Destination and baseline absent; desired present | Plan creation. |
| Destination changed since baseline | Stop for review, including when the desired package is unchanged. |
| Existing destination differs and no baseline exists | Stop for explicit initial adoption/mapping. |
| Previously managed object missing in destination | Report drift; do not silently recreate. |
| Object removed from package | Report retirement request; do not delete or deactivate automatically. |

Bind a reviewed plan to organization, destination snapshot, desired checksum and baseline checksum. Re-read before applying; reject stale plans. Never provide a broad force-overwrite switch as the standard release path.

### 4. Implement safe promotion

- Acquire a per-organization promotion lock and verify baseline/plan freshness.
- Check all bindings and dependencies before the first write.
- Apply in dependency order: entity definitions and required catalogs; relationship declarations; field versions; method/form versions; templates and action dependencies; workflow validation/publication; reviewed permission changes.
- Grant required workflow access before granting transition permissions, using scoped merges rather than replacing entire human roles.
- Do not take over an existing human draft. Detect and report it as a conflict.
- Resolve exact destination version pins and publish a new workflow version; never re-enroll or migrate existing instances automatically.
- Verify native responses and read back each result before checkpointing.
- Resume from verified checkpoints after interruption, reconciling writes that may have succeeded before a timeout. Do not blindly repeat creates or publications.
- Mark the release applied only after every managed object verifies against the desired package.

Native API calls are not a cross-object transaction. A failed promotion can leave some configuration written. Record a partial/failed status, block activation of incompatible application code, and provide a forward-repair plan. Do not represent a frontend image rollback as a configuration rollback.

Reconcile existing seed installers with this ownership model first. They must not overwrite managed configuration or re-grant revoked permissions before or after the comparison step. Keep one responsible writer per managed object.

### 5. Integrate deployment

- Build the application images and approved configuration package from the same commit; record both checksums in release metadata.
- Validate the package in CI and run adapter/contract tests.
- Run production comparison before applying configuration changes. Fail clearly on drift or unsupported dependencies.
- Take normal database backups before configuration writes; backups are for explicit recovery, not routine deployment replacement.
- Promote, verify and activate the compatible application release in a documented order. Plan maintenance or backward compatibility for configurations that cannot safely coexist with the previous code.
- Verify Offers, Onboarding and Offboarding with the intended UAT roles.
- Keep Mailpit/live SMTP selection environment-specific.
- Keep deployment archive cleanup separate from database and uploaded-file retention.

Automatic application should remain disabled until initial production comparison/adoption is reviewed and retry/drift tests pass. This prevents a first deployment from silently treating local Settings as authoritative over production edits.

### 6. Add administrator visibility

Show application revision, expected configuration release, actual applied release/checksum, last verification time, failed or partial promotion status and drift summary. Label stale or failed checks honestly; do not show “in sync” based only on the last successful application.

Provide a documented process for production-only emergency Settings edits: capture and review them into the package before the next promotion. Production edits must remain visible as drift until reconciled.

## Tests and acceptance criteria

- Exact pinned method/field versions survive export and import even when a newer version exists.
- Different environment IDs resolve to equivalent configuration; duplicate names fail safely.
- Cross-tenant responses, incomplete pagination and unsupported dependencies fail the operation.
- Secrets, users, records, assignments, uploaded/generated documents and auto-number counters are excluded.
- First deployment cannot overwrite differing existing configuration without explicit reviewed adoption.
- Unchanged deployments create no duplicate fields, methods, roles or workflow versions.
- Production-only edits, deletions and human drafts are reported and preserved.
- Interrupted operations reconcile successful writes before retrying; checkpoints are organization-scoped.
- Permission updates preserve unrelated grants and respect workflow-before-transition ordering.
- Existing workflow instances retain their enrolled versions and full audit history.
- Backup recovery is never performed automatically during deployment or rollback.
- Local and UAT expose equivalent approved configuration under equivalent roles; employee data remains different by design.
- Deployment reports application and configuration revisions separately.
- Run the platform boundary verifier and existing HRMS regression suites.

## Completion gates

1. Approved local package and full dependency coverage report.
2. Read-only production comparison and reviewed initial mappings/baseline.
3. Successful promotion in an isolated test tenant with realistic existing configuration.
4. Retry, drift, permissions and version-pinning regression tests passing.
5. First UAT promotion verified under HR Full and Super Admin, with no runtime records removed or replaced.

Only then enable routine promotion on deployment. Production access and the current deployed revision still need verification; this document does not imply that production has been synchronized.
