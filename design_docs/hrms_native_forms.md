# HRMS native forms

HRMS record editors render the ordered native field list using ConfiguredInputs. This covers employees (create/edit/exit), customers, projects, allocations, leave, performance cycles/goals/feedback, WFH requests/policies, HR publishing and asset inventory/issue. Specialized action controls use the same metadata through ConfiguredField. Relationship choices still come from authorized APIs; system identity, ownership, revision and generated names are never user-editable merely because they appear in a form.

Submissions include only current editable fields. Native additions, removals, labels, order, types, required/read-only flags and options are reloaded on form mount, focus and the native form-change event. Server validation also checks the current configuration; the client cannot bypass removed/read-only fields. Optional contract defaults must not resurrect removed fields. Record updates preserve historical values outside the form.

Business invariants remain enforced: account identity, approval independence, valid dates, capacity, ratings, and required operational relationships. Removing a field essential to a business action can make that action invalid; the application does not invent values to bypass it.

## Native versioning

Customer and Employee have no workflow and read current native method blocks immediately. Workflow-bound forms use the active published workflow schema, consistent with native version pinning. Editing a pinned method creates a new version: attach that version and publish the workflow to use it. An editor displays this requirement. Existing approvals must not be silently migrated to a different workflow version. There is no automatic republish or production migration in this change.

All changes stay inside the HRMS application and skin. The native platform source is unchanged. Local and production use the same installer and code; no tenant forms are replaced or reset by this change.
