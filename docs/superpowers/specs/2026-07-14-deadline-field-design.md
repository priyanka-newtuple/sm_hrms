# Deadline field + Calendar view — design

**Date:** 2026-07-14
**Status:** Superseded by first-class Due date implementation
**Author:** grooming session (Claude)

> **Architecture correction (2026-07-14):** The schema-level `is_deadline`
> approach described below is not the implemented model. Entities now have one
> nullable, first-class `due_date` column in `runtime.entities`, matching Jira's
> built-in Due date. It is independent of schema fields and workflow SLA,
> persists through transitions, appears as the fixed **Due date** list column,
> and is the calendar's scheduling source. The remainder of this document is
> retained as the original grooming record and should not be used as the current
> implementation contract.

Two related features that share one piece of plumbing (deriving the schema's
date fields + which is the deadline):

- **Part 1 — Deadline field:** flag a `datetime`/`date` field as a deadline;
  render it in the pipeline **list** as a countdown/overdue pill.
- **Part 2 — Calendar view:** a third pipeline view (beside Kanban + List) that
  plots entities on a month calendar by a chosen date field, defaulting to the
  deadline field. Read-only.

## Problem

In the pipeline **list view**, users want a due date rendered with overdue /
countdown treatment (like the red "Overdue" pill in the reference screenshot),
instead of a raw date string. The value must be a **fixed, user-set,
entity-level deadline** that persists as the entity moves through workflow
stages — e.g. "offer must close by Mar 30".

Separately, users want a **calendar view** — a temporal lens on the same
entities, alongside the Kanban and List tabs — to see items landing on their
dates across a month.

## Why not SLA (deadline)

The platform already has an SLA concept (`sla_due_at`): each state defines
`sla_seconds`, and on every transition `sla_due_at = transition_time +
target_state.sla_seconds` (`backend/workflow/manager.py:1019`). That is a
**rolling per-stage timer** — it resets on each transition. A fixed deadline
cannot be represented by it because the date would jump every time the entity
advances. So the deadline is a separate concept, stored as an entity data field.

## Key realization — no migration needed

A `datetime`/`date` **schema field** already: is addable in form-config
(`FIELD_TYPES` offers `datetime`), is set via the form's date picker, and is
stored in entity `data` (entity-level, **persists across stages**). So a fixed
deadline is *already possible* as a datetime field. The gaps are only:

1. The list renders date fields as raw strings — no overdue pill.
2. Nothing marks *which* date field is the deadline (a red "Overdue" pill on a
   past-dated field like "Interview Date" would be wrong).

The entity-schema field model (`EntityField`,
`backend/workflow/models/interface.py:299`) is a Pydantic model **stored as
JSON** with many optional keys already (`col_span`, `placeholder`, `editable`…).
Adding one optional boolean is a **one-line change, no migration**.

---

## Shared plumbing — `is_deadline` flag + datetime-field descriptors

Both features need: (a) an `is_deadline` flag persisted on schema fields, and
(b) the list of the schema's date fields with that flag, sourced from the store
the toggle writes to.

### `is_deadline` flag

| Layer | File | Change |
|-------|------|--------|
| Backend | `backend/workflow/models/interface.py` (`EntityField`, ~line 299) | Add `is_deadline: bool \| None = None`. No migration — schema persists as JSON; passes through create/update (schema `fields` are typed `EntityField`, and forms' `EntityTypeSchemaContract.fields` too). |
| FE type | `frontend/src/core/types/index.ts` (`FormField`, ~line 479) | Add `is_deadline?: boolean`. |
| FE serialize | `frontend/src/core/services/api/formSchemas.ts` | `mapFormFieldToEntityField`: emit `is_deadline` for `datetime`/`date` fields. `mapEntityFieldToFormField`: read `raw.is_deadline` back. |

### Form-config UI

`.../settings/components/form-config/components/EditFieldModal.tsx`: add a
`<Switch>` **"Track as deadline"**, rendered only when `field.type` is
`datetime` or `date`. Toggles `is_deadline`.

### Datetime-field descriptors — sourced from the **forms** schema

Important: the pipeline list's `model.schemaFields` comes from the **workflow
record's embedded `entity_schema`** (`deriveViewModelFromRecord`), while the
"Track as deadline" toggle writes to the **forms module** schema
(`EntityTypeSchema`, edited in settings). These are two stores (a 2026-05
migration moved schemas into forms; the workflow embeds a validated copy).
**Source the flag from the forms schema** — the exact store the toggle writes —
not the workflow copy.

`entitySchemas = useEntitySchemasFor(workflow.entity_type)` is already returned
by `usePipelineBoardData` and destructured in `Pipeline/index.tsx:53`. Add a
small helper (e.g. `getDateFieldDescriptors(entitySchemas)`) returning:

```ts
{ id: string; label: string; isDeadline: boolean }[]
```

— one entry per `datetime`/`date` field across the active schemas. From it:

- `deadlineFieldIds = new Set(descriptors.filter(d => d.isDeadline).map(d => d.id))` → Part 1.
- full `descriptors` list → Part 2 (calendar field picker + default).

Marking is by **field id**, orthogonal to how a list column came to exist
(schema field or a key present in entity `data`).

---

## Part 1 — Deadline pill in the list

Cell style = **pill only** (chosen). Reuse `SlaTag`
(`.../EntityDetailSlideOver/SlaTag.tsx`) — already a pill: `Xd overdue` (rose) /
`Due today` (amber) / `Xd left`. Fits deadline semantics as-is.

| File | Change |
|------|--------|
| `frontend/src/pages/Pipeline/index.tsx` | Compute descriptors → `deadlineFieldIds`; pass as a new `deadlineFieldIds` prop to `PipelineListView`. |
| `.../PipelineListView/index.tsx` | Accept `deadlineFieldIds?: Set<string>` (default empty). In `visibleColumns.map` render: if `deadlineFieldIds.has(col.field)` and the value is a non-empty date → `<SlaTag slaDate={String(value)} />`; empty/invalid → existing `—`. Else unchanged `renderCellValue`. |

No change to `pipelineViewModel.ts` / `PipelineSchemaField` — flag does not
travel through the workflow view-model.

---

## Part 2 — Calendar view (read-only, month)

New third tab beside Kanban + List. Plots entities on a month grid by a chosen
date field (default = deadline). Click an entity → existing detail slide-over.

**Library:** none — build custom with the installed `date-fns` (v4). A month
grid is ~150 lines and matches the Tailwind design; FullCalendar / react-big-
calendar are heavy and fight the design system.

### Component — `PipelineCalendarView`

New folder `frontend/src/pages/Pipeline/components/PipelineCalendarView/`:

- `index.tsx` — month grid + toolbar.
- (optional) `DayPopover.tsx` — overflow list for a day.

Props: `{ model, entities: PipelineListEntity[], onEntityClick, dateFields: {id,label,isDeadline}[] }`.

**Grid:** `date-fns` — `startOfMonth`/`endOfMonth`, `startOfWeek`/`endOfWeek`
(weekStartsOn Sun), `eachDayOfInterval`, `isSameDay`, `isSameMonth`, `format`,
`addMonths`/`subMonths`. 6 rows × 7 cols. Sun–Sat header. Current month in view
held in local state; out-of-month days dimmed; today's cell marked.

**Toolbar:** `Today` button, `‹ ›` month nav, "MMMM yyyy" label, the **date-field
picker** dropdown, and a small `N unscheduled` chip (entities with no value in
the selected field). Month-only — no week/day, no view dropdown (v1).

**Field picker:** options = `dateFields`. Default = first `isDeadline`, else
first field. Persisted per machine via `usePersistentState`
(`pipeline-calendar:field:<machineName>`).

**Placement:** an entity appears on the day of `data[selectedFieldId]` (parsed
as a date). Within a day, sort by time. Pill = entity primary value
(`getEntityPrimaryValue`), colored by state accent
(`model.stateById.get(entity.current_state)?.accent`). Show the time prefix when
the value has a time component. Click pill → `onEntityClick(entity_id)`.

**Overflow:** cap 3 pills/day; `+N more` opens `DayPopover` (or a simple
anchored panel) listing all that day's entities, each click → `onEntityClick`.

**Empty states:** no date fields in schema → "No date fields to display";
none scheduled in view → empty grid (still navigable).

**No "New event" button** — the page header's Add Entity already covers
creation. Reuse.

### Wiring — `Pipeline/index.tsx`

- Import `CalendarDays` (lucide) + `PipelineCalendarView`.
- Add `<TabsTrigger value="calendar">` to `viewTabsList` (after List).
- Add `<TabsContent value="calendar">` rendering `PipelineCalendarView` with
  `model`, `listEntities`, `handleEntityClick`, and `dateFields` (the shared
  descriptors).
- Behind the same board filters (uses `listEntities` = `boardFilteredEntities`).

---

## Scope (YAGNI)

- **Main Pipeline page only** (`Pipeline/index.tsx`) for both features. The other
  `PipelineListView` call sites:
  - `PipelineBoardWidget.tsx` — has `entitySchemas` (same hook); wire the
    deadline prop if the dashboard board should show pills too (cheap, optional).
  - `WorkflowsListWidget.tsx` — aggregated cross-workflow (mixed entity types);
    `deadlineFieldIds` defaults empty → unchanged. Calendar not added there.
- Calendar: **read-only, month only.** No drag-reschedule, no click-to-create,
  no week/day views — all explicit follow-ons.
- Deadline pill: list only; kanban card + detail could reuse `SlaTag` later.
- Sorting (list) works already — ISO strings sort via `e.data[field]`.
- Multiple deadline fields allowed; each renders a pill. No "only one" rule.

## Known ceilings (mark with `ponytail:` comments)

- `date`-only values (`"2026-03-22"`) parse as UTC midnight in `SlaTag` and in
  the calendar day-bucketing; day can be off by one near midnight in non-UTC
  zones. Acceptable v1; parse as local date if it bites.
- `SlaTag`'s amber threshold is hardcoded (`daysLeft <= 2`). Reused as-is.
- Calendar `+N more` cap = 3 (constant); bump if cells feel cramped.

## Verification

- **Part 1:** one assert-based self-check for deadline detection + empty guard —
  past date → overdue pill, future → "left", empty/null/invalid → `—`.
- **Part 2:** one assert-based self-check for day-bucketing — an entity with a
  given date lands in the right day cell; entity with no value counts as
  unscheduled; month-boundary days bucket correctly.
- **Manual:** add a datetime field, toggle "Track as deadline"; set past/future
  values on two entities; confirm list pills + calendar placement; confirm a
  non-deadline date field still renders plain in the list and is selectable in
  the calendar picker.

## Diff size

- Shared + Part 1: ~1 backend line + ~5 small frontend edits, reuse `SlaTag`,
  no migration.
- Part 2: 1 new component (~180 lines) + ~15 lines wiring, no backend, no new
  dependency (`date-fns` already installed).
