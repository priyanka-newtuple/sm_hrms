# Production configuration adoption review — 26 October 2026

Scope: Offers, Add Employee, employee offboarding and their native dependencies.
The user authorized reviewing and applying the configuration while preserving
existing functionality and data. Initial read-only comparison run: 40302690392.

The original local snapshot contained 147 definitions: 55 matched, 70 were
missing, and 22 differed. It is not safe to copy that snapshot unchanged.

## Resolutions

- Keep production's offboarding entity schema, including approver, coordinator,
  confirmed contact and employee handover fields. Keep existing datetime types;
  do not remove fields or reinterpret existing dates.
- Keep production's offboarding exit-detail and verification methods and workflow.
- Keep production's offboarding role grants, including read-only employee-authored
  handover fields. Do not broaden these permissions from the local snapshot.
- Retain all production departments/designations. Add local business picklist
  entries (Sales, Recruiter, Full Stack Developer) without removing existing options.
  Remove local test/role-name pollution from field dropdowns and align them with
  the merged native picklists. Keep department required.
- Retain the existing employment-type field definition; converting existing
  free text into a restricted dropdown needs a separate data compatibility check.
- Create a dedicated HRMS Employee Registration method for Add Employee rather
  than rewriting the general Employee form. Keep first/last name required.
- Add the missing Offers/Add Employee definitions and supporting fields/methods.
- Add the last-working-day information to existing offboarding email templates.
- Preserve role capabilities, unrelated grants, user memberships and runtime data.

`configuration/hrms/production-candidate.json` records this merge separately from
the captured local candidate. It is not yet the activated `release.json`.

## Execution controls

The manual adoption workflow requires a successful comparison artifact from the
same repository commit. It verifies the entire plan against a fresh snapshot,
runs migration preflight, and rejects drift or an already-managed package.
It shares deployment concurrency and the VM lock. Both databases are backed up
before adoption. Native definitions are written through public platform APIs;
the HRMS database stores only the adoption baseline and promotion journal.

The job verifies all resulting definitions and runs the normal native health
checks. It never restores a database, deletes volumes, reenrolls records, sends
email or changes employee records. Existing workflow instances remain pinned
to their existing workflow versions. Interrupted writes require reconciliation.

After successful adoption, the verified package can become `release.json` so
future deployments use the managed promoter instead of competing legacy seed
installers. Unsupported Settings categories remain outside this release scope.
