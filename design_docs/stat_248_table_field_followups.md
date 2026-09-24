# STAT-248 Table Field Follow-ups

## Refactor before extending table behavior further

The initial Table/Grid field implementation intentionally keeps the persisted
shape generic, but the frontend table UI is currently concentrated in large
components. Before adding related-entity cells, richer column types, or more
builder behavior, split the table-specific UI into focused shared components.

Recommended split:

- Extract a shared `TableFieldInput` used by both internal workflow forms and
  public forms.
- Move table row seeding, cell normalization, readonly checks, and display-mode
  helpers into shared table utilities.
- Split the form-builder table configuration out of `FieldRow.tsx` into focused
  components:
  - `TableConfigSection`
  - `TableColumnsEditor`
  - `TableFixedRowsEditor`
  - `TableConfigJsonModal`
  - `tableConfigUtils`
- Centralize schema metadata filtering for keys such as `rows`, `columns`,
  `table_config`, and `display_mode` so config-only metadata does not leak into
  entity detail or pipeline views.

Target outcome:

- `FieldRow.tsx` returns to being a field-row shell rather than owning table
  configuration internals.
- Internal and public `FieldInput` table behavior stays consistent through one
  shared implementation.
- Future table extensions can be added without duplicating behavior across
  workflow, public form, preview, and builder surfaces.
