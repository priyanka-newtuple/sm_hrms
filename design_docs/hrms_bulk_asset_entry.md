# Bulk asset entry

Office Admin and Super Admin can use Asset Management > Add assets, enter a quantity (1–50), shared inventory details, and individual serial numbers or existing sticker tags. Review, then create. Each unit is a separate native HRMS.Asset record and can be assigned independently. HR view-only access remains unchanged.

Identifiers use the native entity identifier template (currently AST-{{seq}}), backed by the platform's atomic tenant-scoped sequence. The UI never calculates the next number. Gaps are valid. Existing identifiers and sticker tags are retained.

Required fields, categories, conditions and custom fields come from native forms. Quantity is an entry command, not stored as stock on a single asset. Sticker/tag is optional; serial requirements remain configuration-driven. The installer migrates the native asset form and publishes a new workflow version while preserving the graph and field metadata. An existing draft, unpublished method edits, or a shared method requiring changes stops migration for review. Historical enrollments are not rewritten.

The application journal stores the batch and stable per-item request keys. Validation catches duplicate serials/tags before creation. A partial failure stops the batch; Retry unfinished items or Resume batch reuses completed items. Neither deployment nor retry clears inventory or database volumes.

Validation: asset-service tests cover creation, authorization, duplicate detection, quantity bounds and partial replay. Installer tests cover preservation of native metadata and refusing conflicting drafts/shared methods. Run the frontend build and platform boundary check before release.

Deployment: not yet performed for this feature. The production deployment invokes hrms_app.install_asset_bulk after configuration promotion; local installation invokes the same migration. Resolve any reported configuration conflict before retrying deployment rather than discarding a human draft.
