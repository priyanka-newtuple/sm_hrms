# Picklist Multi — Extended (Conditional) Fields

**Spec — 10 Sep 2026**
Status: draft, awaiting approval
Scope: frontend only (no backend change, no migration)
Related: `design_docs/state_machine.MD`, `backend/README.md`

---

## 1. Problem

`picklist_multi` ("Picklist Multi (Dropdown Add)") lets an admin pair two picklists — a
primary list rendered as a multi-select of *rows*, and a secondary list whose options are
toggled per row. The stored value is flat: which options are on, per row. Nothing more can
be captured about an option.

Real onboarding flows need per-option detail. In the reference prototype
(`authority_type_certificate_prototype_v4`), a client is onboarded against jurisdictions
(primary) × services/authority types (secondary), and *some* services require certificate
details — certificate id, issuing authority, effective/expiry dates, status, supporting
document — captured **per jurisdiction, per service**. Services that need no certificate
show "No certificate required" and ask for nothing.

Today an admin can only model that by adding certificate fields to the form for every
service, always visible, unrelated to what was selected.

## 2. Goal

Add an optional **Extend Field** capability to `picklist_multi`:

- Off by default. Off = today's behaviour, byte-for-byte.
- On → per secondary-picklist option, the admin picks one or more **existing Field Library
  fields** that appear when an end user selects that option.
- At runtime, extended fields for every selected option render together and react
  immediately to selection changes.
- Generic: any picklist, any Field Library field. No hardcoded option names or field keys.

## 3. Current state (verified in code)

### 3.1 Type and catalogue

`backend/alembic/versions/2026_08_18_0001_add_field_type_catalogue.py:34`

```
("picklist_multi", "Picklist Multi (Dropdown Add)", "multi_select", "picklist", True, 90)
```

Catalogue code `picklist_multi`, engine type `multi_select`, config kind `picklist`. The
backend `EntityField` model (`backend/workflow/models/interface.py:840`) knows neither the
`picklist_multi` type nor the keys `picklist_id_2` / `enum_values_2`.

### 3.2 Configuration surfaces

| Surface | File | Notes |
|---|---|---|
| Settings → Forms | `frontend/src/pages/settings/components/form-config/components/FieldRow.tsx:401-455` | two `<select>`s: "Dropdown picklist", "Multi-select picklist" |
| Settings → Fields (Field Library) | `frontend/src/pages/settings/components/fields/LibraryFieldEditor.tsx:247-280` | same two selects |
| Shared save resolver | `form-config/fieldSaveValidation.ts:31-46,82-86` | re-reads both picklists, snapshots `enum_values`/`enum_labels` + `enum_values_2`/`enum_labels_2` from `option.value`/`option.label`; refuses save unless both picklists chosen |

Picklists: `modular_backend.picklists`, org-scoped, `options` JSONB of `{value,label}`
(`backend/forms/db_models.py:56`).

### 3.3 Persistence of the field definition

1. **Form schema** — `<app>_definitions.entity_type_schema.fields_json`. `EntityField` now
   carries `picklist_id_2`, `enum_values_2`, `enum_labels_2` and `extensions` as ordinary
   keys (§17.4), so the field is stored as `multi_select` with those alongside and the label
   in `description` like any other field. The `__plm__:` blob is still *read*
   (`core/services/api/formSchemas.ts`) for rows written before that change; nothing writes
   it any more.
2. **Field Library** — `library_field_versions.settings` (JSONB, free-form). Type is stored
   natively as `picklist_multi`; `picklist_id_2` / `enum_values_2` are ordinary settings
   keys. `extractSettings()` (`fields/fieldLibraryUtils.ts:144`) forwards every non-identity
   key, so new keys need no plumbing.
3. **Method-block pin → workflow entity schema** — `_entity_field_from_method_field`
   (`backend/workflow/manager.py`) copies all four keys for config kind `picklist`, so a
   pinned `picklist_multi` keeps its second picklist and its extensions. Before §17.4 it
   copied only `picklist_id` + `enum_values` and the field rendered as a flat multi-select
   of the first picklist.

### 3.4 Stored value

`entity_records.data[<field_id>]` (JSONB, no server-side shape validation):

```json
[
  { "dropdown": "AZ-Arizona", "toggles": ["voip", "broadband"] },
  { "dropdown": "CA-California", "toggles": ["voip"] }
]
```

Parsed/emitted by `core/components/PicklistMultiWizard.tsx` (`parseRows`, `:17-28`).
Default `[]` (`shared/utils/entityForm.ts:86`). Required check is `value.length === 0`
(`entityForm.ts:250`).

### 3.5 Runtime rendering

`FieldInput.tsx:485` dispatches to `PicklistMultiWizard`, a three-step wizard:

1. multi-select the primary options (`enum_values`) → one row each
2. check secondary options (`enum_values_2`) and "Apply selected items to all"
3. dual panel — rows on the left with counts, item grid on the right, plus All / Clear /
   "Copy from <row>" / filter

The prototype's certificate block sits exactly here: inside step 3's right panel, under the
item grid, one card per selected item of the active row.

### 3.6 Read paths

| Surface | File |
|---|---|
| Record detail form | `pages/records/detail/components/EntityFormFields.tsx:290-293` |
| Slide-over display | `pages/Pipeline/components/EntityDetailSlideOver/EntityDataSection.tsx:337` |
| CSV/PDF export | `lib/export/serialize.ts:11-27` |
| Pipeline card | suppressed by design (`Pipeline/utils/cardFieldValue.ts:61`) |
| Filter bar | `Pipeline/hooks/buildCustomFilterOptions.ts:25` (already ineffective — see §12) |

### 3.7 Reusable pieces (no new equivalents will be written)

| Piece | File | Used for |
|---|---|---|
| `FieldLibraryPanel` | `settings/components/methods/components/FieldLibraryPanel.tsx` | browse/search/paginate/select library fields; `onAdd(libraryFieldIds)` |
| `toFormField(entry)` | `fields/fieldLibraryUtils.ts:126` | `FieldWithVersion` → `FormField` |
| `fetchAllLibraryFieldPages` | `fields/fieldLibraryUtils.ts:55` | full catalogue in one helper |
| `FieldInput` | `core/components/FieldInput.tsx` | renders any `FormField` |
| `isMissingRequiredFieldValue`, `validateFieldValue` | `shared/utils/entityForm.ts` | per-field validation |
| `resolveFieldForSave` | `form-config/fieldSaveValidation.ts` | shared pre-save snapshot/validation |

## 4. Decisions taken

| # | Decision | Rationale |
|---|---|---|
| D1 | Values scoped **per primary row × secondary option** | Matches the prototype (a certificate belongs to one jurisdiction *and* one service). Values nest inside the row, so no second top-level shape. |
| D2 | Extension fields are **snapshots taken at config time**, carrying `library_field_id` | Zero extra fetches at render; mirrors how a Method version pins a field shape. Later Field Library edits do not silently rewrite saved forms. |
| D3 | Toggle on **both** configurators (Forms + Field Library) | They already share `resolveFieldForSave`; the new editor is one component mounted twice. |
| D4 | `picklist_multi` **only** | Plain `multi_select` stores a flat string array; extending it would add a second value shape and touch its display/export/filter paths. Not asked for. |
| D5 | `extensions` presence **is** the on/off flag — no separate `extendable` boolean | One key instead of two, survives every JSON round-trip. `{}` = on but unconfigured; absent = off. |

## 5. Configuration model

New optional key on `FormField` (`core/types/index.ts`):

```ts
/** One Field Library field revealed by a picklist_multi option. A snapshot of the
 *  library field as it was when the admin added it, plus the id it came from. */
export interface ExtensionField extends FormField {
  library_field_id: string;
}

export interface FormField {
  // …existing keys…
  /** picklist_multi only. Keyed by a value from `enum_values_2`. Present (even
   *  empty) means Extend Field is ON; absent means OFF. */
  extensions?: Record<string, { fields: ExtensionField[] }>;
}
```

Rules:

- **Keys are option *values*** from `enum_values_2` (what `resolveFieldForSave` snapshots
  from `option.value`), never labels. Display uses the parallel `enum_labels_2`.
- Snapshot content is exactly `toFormField(entry)` plus `library_field_id`, so an extension
  field carries its own `type`, `required`, `picklist_id`, `enum_values`, `table_config`,
  `document_config`, `placeholder`, … and renders through `FieldInput` unchanged.
- Snapshot `id` is the library field's `field_key`; it is the key extension values are
  stored under. `FieldLibraryPanel` de-duplicates by `library_field_id`
  (`FieldLibraryPanel.tsx:112,128`), so the editor adds one further guard: an add whose
  `field_key` already exists on that option is skipped with an inline message, because two
  library fields sharing a key would collide in the value map.
- Field types **not** allowed as extension fields: `section` (layout placeholder),
  `picklist_multi` (no nesting), `reference` and any `calc` field (resolved by the backend
  against top-level entity data), `auto_number` and `timer_duration` (backend-generated per
  record). `document` was excluded at first and is now **allowed** — see §17.5. Everything
  else `FieldInput` renders is allowed, including `table`.

Example (generic, values elided):

```json
{
  "id": "services",
  "label": "Services",
  "type": "picklist_multi",
  "picklist_id": "<jurisdictions>",
  "enum_values": ["az", "ca"],
  "picklist_id_2": "<services>",
  "enum_values_2": ["broadband", "voip", "fiber"],
  "extensions": {
    "voip": { "fields": [
      { "library_field_id": "…", "id": "phone_number", "label": "Phone Number", "type": "phone", "required": true, "system": false },
      { "library_field_id": "…", "id": "number_of_lines", "label": "Number of Lines", "type": "integer", "required": false, "system": false }
    ]},
    "broadband": { "fields": [
      { "library_field_id": "…", "id": "bandwidth", "label": "Bandwidth", "type": "text", "required": false, "system": false }
    ]},
    "fiber": { "fields": [] }
  }
}
```

`"fiber": { "fields": [] }` and an absent `"fiber"` key mean the same thing at runtime: no
extended fields. The empty entry is not written by the configurator.

## 6. Persistence

### 6.1 Form schema (`entity_type_schema.fields_json`)

`extensions` joins the existing `__plm__:` blob — no new backend key, no migration:

```json
{
  "field": "services",
  "type": "multi_select",
  "required": true,
  "nullable": false,
  "picklist_id": "<jurisdictions>",
  "enum_values": ["az", "ca"],
  "description": "__plm__:{\"label\":\"Services\",\"picklist_id_2\":\"<services>\",\"enum_values_2\":[\"broadband\",\"voip\"],\"extensions\":{\"voip\":{\"fields\":[…]}}}"
}
```

- Write: `mapFormFieldToEntityField` (`formSchemas.ts:236-253`) adds `extensions` to the
  stringified meta when non-empty.
- Read: `mapEntityFieldToFormField` (`:94-116`) parses it back, tolerating absent or
  malformed values exactly as it already does for `enum_values_2` (bad JSON → field
  degrades to a labelled `multi_select`, no throw).
- `description` is a `Text` column; blob growth is acceptable. The snapshot is per option,
  so a field with many options × many extension fields produces a large blob — flagged in
  §13 as a watch item, not a blocker.

### 6.2 Field Library (`library_field_versions.settings`)

`extensions` is an ordinary settings key. `extractSettings()` already forwards it and
`toFormField()` already spreads settings back onto the `FormField`, so **no code change is
required** for storage on this path; only the editor UI is new. Editing extensions creates
a new field version, like any other settings change (`buildVersionRequest`).

### 6.3 Method-block pin

Unchanged by this spec. A `picklist_multi` pinned into a workflow via a Method block loses
`picklist_id_2` / `enum_values_2` today and will equally lose `extensions`. See §12.

## 7. Stored value

Extension values live inside the row that owns them (D1):

```json
[
  {
    "dropdown": "az",
    "toggles": ["broadband", "voip"],
    "extensions": {
      "voip": { "phone_number": "+1…", "number_of_lines": 4 },
      "broadband": { "bandwidth": "1G" }
    }
  },
  { "dropdown": "ca", "toggles": ["voip"], "extensions": { "voip": { "phone_number": "+1…" } } }
]
```

- A row with no `extensions` key is valid and is what every existing record looks like.
- Inner values are whatever the field's own type stores (string, number, array for
  `multi_select` / `document`, row array for `table`) — the same shapes `FieldInput`
  already produces elsewhere.
- Deselecting an option **prunes** `row.extensions[option]`, so the payload never carries
  values for options that are off. (Trade-off: an accidental uncheck loses typed input.)
- Unchecking an option in step 2, which already strips it from every row, prunes that
  option's extension values from every row too.

### 7.1 Worked example (approved shape)

Picklists — `pl_jurisdictions` = `az`/AZ-Arizona, `ca`/CA-California; `pl_services` =
`broadband`/Broadband, `voip`/VoIP, `fiber`/Fiber, `wireless`/Wireless. The field is
configured with extension fields on `broadband` (Bandwidth, Provider) and `voip` (Phone
Number *required*, Number of Lines, Service Start Date); `fiber` and `wireless` have none.

End user selects AZ and CA; in AZ toggles Broadband + VoIP; in CA toggles VoIP only:

```json
{
  "identifier": "CL-00042",
  "client_name": "Acme Telecom",
  "services": [
    {
      "dropdown": "az",
      "toggles": ["broadband", "voip"],
      "extensions": {
        "broadband": { "bandwidth": "1 Gbps", "provider": "att" },
        "voip": {
          "phone_number": "+1-602-555-0143",
          "number_of_lines": 8,
          "service_start_date": "2026-10-01T00:00:00"
        }
      }
    },
    {
      "dropdown": "ca",
      "toggles": ["voip"],
      "extensions": {
        "voip": { "phone_number": "+1-415-555-0199" }
      }
    }
  ]
}
```

Reading of the example, point by point:

- Path is `data[<field_id>][] -> row -> extensions[<option value>][<library field_key>]`.
- CA's `voip` omits `number_of_lines` and `service_start_date`: optional, never touched, so
  no key is written (not `null`). Typed then cleared writes `""`.
- `fiber` / `wireless` appear nowhere — never selected, and nothing configured for them.
- Inner values carry each extension field's own type shape: `phone`/`text`/`select` a
  string, `integer` a number, `datetime` an ISO string, `multi_select`/`document` an array,
  `table` an array of row objects.
- The same field with Extend Field off, or a record saved before this feature, stores rows
  with no `extensions` key at all.

## 8. Configurator UX

New component `form-config/components/PicklistExtensionsEditor.tsx`, mounted by both
`FieldRow.tsx` and `LibraryFieldEditor.tsx` directly under their existing two-picklist
block.

```
Field Type: Picklist Multi (Dropdown Add)
Dropdown picklist:      [ Jurisdictions ▾ ]
Multi-select picklist:  [ Services      ▾ ]

Extend Field                                    [ Toggle ]  ← default OFF
─────────────────────────────────────────────────────────────
Broadband        Bandwidth ✕   Provider ✕            [+ Add fields]
VoIP             Phone Number ✕  Number of Lines ✕   [+ Add fields]
Fiber            No extended fields                  [+ Add fields]
Wireless         No extended fields                  [+ Add fields]
```

- The toggle renders only when `type === 'picklist_multi'` **and** `picklist_id_2` is set;
  before that it shows a one-line hint to pick the second picklist first.
- Toggling on writes `extensions: {}`; toggling off deletes the key. Turning it off asks for
  confirmation when any option has fields, because the configuration is discarded.
- One row per option of the second picklist, labelled from `enum_labels_2` (falling back to
  the value), ordered as `enum_values_2` is.
- Chosen fields render as removable chips showing the library field's name and a type icon.
- **[+ Add fields]** opens a modal hosting the existing `FieldLibraryPanel` with
  `existingFieldIds` set to that option's already-chosen **library field ids**, so the
  panel's own search, type filter, pagination and multi-select are reused as-is.
  `onAdd(ids)` maps ids → `FieldWithVersion` → `toFormField()` + `library_field_id`,
  appending to that option and skipping `field_key` collisions (§5).
  `FieldLibraryPanel` gains one optional prop, `excludeTypes?: FieldType[]`, so the
  disallowed types in §5 never appear in its results; omitted by its existing Methods
  caller, which therefore behaves exactly as today.
- The library entries needed for the mapping come from one `fetchAllLibraryFieldPages` call
  owned by the editor (the same helper the Fields tab already uses for its formula/table
  pickers), cached for the lifetime of the modal.
- A "Manage Field Library" link (the panel's existing `onGoToFieldLibrary`) covers the case
  where the wanted field does not exist yet. Fields are never authored inline here.

At save, `resolveFieldForSave` (`fieldSaveValidation.ts`) additionally:

- drops `extensions` entirely for any type other than `picklist_multi`, alongside the
  existing `picklist_id_2` / `enum_values_2` cleanup;
- drops extension keys that are no longer options of the second picklist (the picklist was
  edited or swapped), so stale configuration cannot linger;
- drops options whose `fields` array is empty;
- rejects the save when an extension field's type is one of the disallowed types (defensive;
  the picker already filters them).

## 9. Runtime behaviour

`PicklistMultiWizard` step 3, right panel, under the item grid — the prototype's layout:

```
Services                          (item grid, unchanged)
[x] Broadband   [x] VoIP   [ ] Fiber

Extended details
┌ Broadband ───────────────────────────────────┐
│ Bandwidth [        ]   Provider [         ]  │
└──────────────────────────────────────────────┘
┌ VoIP ────────────────────────────────────────┐
│ Phone Number [    ]   Number of Lines [    ] │
└──────────────────────────────────────────────┘
```

- One card per option **selected in the active row**, ordered by `enum_values_2`, each
  headed by the option's label, its field count, and a status badge — the prototype's
  "Certificate required" / "No certificate required" affordance, generalised to three
  states off the configured fields, using the semantic status tokens so both themes read
  correctly:

  | State | Badge | Style |
  |---|---|---|
  | no fields configured | `No details required` | `bg-success-subtle text-success` |
  | any field required | `Details required` | solid `bg-warning text-warning-foreground` |
  | fields, none required | `Optional details` | `bg-info-subtle text-info` |

  A card with no fields is header-only, so the reader can see every selection was accounted
  for. When the field has no `extensions` at all the whole block is absent and the wizard
  looks exactly as it does today.
- Fields are laid out two to a row (one on a narrow viewport), labels above in
  `text-xs font-semibold` with the required marker. `textarea`, `table` and `multi_select`
  take the full row. `placeholder` is left to the control itself, which already renders it.
- Controls are shrunk to card scale by a scoped `[&_input]/[&_select]/[&_textarea]` override
  on the grid rather than a `FieldInput` size prop: each field type renders its own control,
  so one override reaches all of them, and `FieldInput`'s own `px-4 py-3 text-base` sizing
  (tuned for a full-width form row) is left untouched for every other caller. The card is
  `bg-muted/20`, because the panel it sits in is already `bg-card`.
- Each card lays its fields out on the existing responsive grid used by the record form and
  renders each through `FieldInput`, so every field type behaves as it does anywhere else.
- `onChange` writes `rows[activeRow].extensions[option][field.id]` and emits the whole rows
  array, as the wizard already does for `toggles`.
- The block is per active row: switching rows in the left rail switches the values shown.
  The left-rail count badge keeps counting toggles only.
- `disabled` propagates to every extension input. `invalid` is per extension field (§10),
  not inherited from the parent.
- `PicklistMultiWizard` gains an optional `entityId` prop, forwarded from `FieldInput`, so
  `document` extension fields upload against the right record.

## 10. Validation

`shared/utils/entityForm.ts`:

- `isMissingRequiredFieldValue` for a `picklist_multi` field also reports missing when a
  **required** extension field of a **selected** option in any row is empty — reusing the
  same per-type emptiness rules by recursing with the extension field and its value.
- `validateFieldValue` likewise recurses, so an extension field's type-level message (bad
  integer, bad table row) surfaces, prefixed with the row and option:
  `"Services" — AZ-Arizona / VoIP: "Number of Lines" must be a whole number`.
- Extension fields of unselected options are never validated.
- Recursion is one level deep by construction: extension fields can never be
  `picklist_multi` (§5).

## 11. Read paths

- **Export** (`lib/export/serialize.ts:11-27`): each row appends its extension values after
  the toggles —
  `AZ-Arizona: Broadband, VoIP (VoIP — Phone Number: +1…; Number of Lines: 4) | CA-California: VoIP`.
- **Slide-over** (`EntityDataSection.tsx:337`): under a row's chips, a compact
  label/value list per option that has extension values, reusing the existing card styling.
- **Record form**: no change — it renders the wizard.
- **Pipeline card / filter bar**: unchanged. Extension values are not filterable or
  card-displayable in this iteration (§13).

## 12. Pre-existing gaps (documented, not fixed here)

1. ~~**Method-pinned `picklist_multi` loses picklist 2**~~ — **fixed**, see §17.4. This was
   the gap that made the feature invisible for an organization with no form configs, whose
   record forms are built entirely from the workflow's resolved `entity_schema`.
2. **Field filters never match `picklist_multi`** — `workflow/db_models.py:546` compares
   `data[f].astext == v OR data[f].contains(json.dumps(v))`; the value is an array of
   objects, so a string never matches. Pre-existing; extensions do not change it.
3. **`enum_labels_2` is not persisted** on the form-schema path (`formSchemas.ts:245-251`
   stashes only label / `picklist_id_2` / `enum_values_2`), so the wizard shows raw option
   values. Extension **cards** inherit that. Adding `enum_labels_2` to the blob is a
   two-line fix and is **included** in this work, since the extension cards make raw values
   much more visible.
4. **Grid forms** classify `picklist_multi` as a text cell
   (`backend/grid_forms/models/interface.py:44`) and their cell-config whitelist
   (`CELL_CONFIG_KEYS`, same file) has no `extensions` key, so a grid-form cell cannot
   carry this configuration. Out of scope; a one-line backend addition if wanted.
5. ~~**`document` cannot be an extension field**~~ — **fixed**, see §17.5. The backend
   walker now descends into a picklist_multi's extension values, so `document` is no longer
   in `EXTENSION_DISALLOWED_TYPES`. As originally written: `_validate_document_field_values`
   collected the schema's **top-level** `document` fields only, so a file uploaded against a
   nested document field before its record existed was never handed to
   `_attach_unowned_document_files` and stayed unowned and unvalidated.
6. **Field permissions are per top-level field** — `_validate_field_write_permissions`
   (`backend/entities/manager.py:2967`) compares the payload's top-level keys against the
   actor's editable list, and read masking works the same way. Extension values therefore
   inherit the permission of the picklist_multi field that owns them; an individual
   extension field cannot be permissioned or masked separately.

## 13. Out of scope

- Plain `multi_select` support (D4).
- Method-block propagation (§12.1).
- Live resolution of library fields / notifying forms when a library field changes (D2).
- Filtering, card display, dashboards or bulk import over extension values.
- Backend validation of the extension value shape (`data` stays free-form JSONB, as it is
  for every other field type today).
- Per-extension-field permissions (§12.6). (`document` extension fields were out of scope
  when this was written and have since been built — §17.5.)
- Blob-size enforcement on the `__plm__:` description; watch item only.
- Automated tests (vitest/Playwright). Verification is the manual pass in §15 plus the
  existing suites staying green.

## 14. File-by-file changes (as built)

| # | File | Change |
|---|---|---|
| 1 | `frontend/src/core/types/index.ts` | add `ExtensionField`, `FieldExtension`, `FormField.extensions` |
| 2 | `frontend/src/core/services/api/formSchemas.ts` | stash/read `extensions` + `enum_labels_2` in the `__plm__:` blob; defensive `parseExtensions` |
| 3 | `frontend/src/pages/settings/components/form-config/components/PicklistExtensionsEditor.tsx` | **new** — Extend Field toggle and per-option rows (185 lines) |
| 4 | `frontend/src/pages/settings/components/form-config/components/ExtensionFieldPickerModal.tsx` | **new** — hosts `FieldLibraryPanel` as the picker, snapshots each pick (106 lines) |
| 5 | `frontend/src/core/components/PicklistExtensionCards.tsx` | **new** — runtime cards for the selected options of a row (131 lines) |
| 6 | `frontend/src/pages/settings/components/form-config/constants.ts` | `EXTENSION_DISALLOWED_TYPES` |
| 7 | `frontend/src/pages/settings/components/form-config/components/FieldRow.tsx` | mount the editor |
| 8 | `frontend/src/pages/settings/components/fields/LibraryFieldEditor.tsx` | mount the editor |
| 9 | `frontend/src/pages/settings/components/form-config/fieldSaveValidation.ts` | prune stale/empty options, strip on type change, reject disallowed types |
| 10 | `frontend/src/pages/settings/components/methods/components/FieldLibraryPanel.tsx` | optional `excludeTypes` (no change for the Methods caller) |
| 11 | `frontend/src/core/components/PicklistMultiWizard.tsx` | `extensions` in the row shape, prune on deselect, render the cards, `entityId` passthrough, option labels in steps 2–3 |
| 12 | `frontend/src/core/components/FieldInput.tsx` | forward `entityId` to the wizard |
| 13 | `frontend/src/shared/utils/entityForm.ts` | `forEachExtensionValue` walker; required + type validation recursion |
| 14 | `frontend/src/lib/export/serialize.ts` | extension values in exports |
| 15 | `frontend/src/pages/Pipeline/components/EntityDetailSlideOver/EntityDataSection.tsx` | extension values in the slide-over |
| 16 | `frontend/src/pages/settings/components/fields/fieldLibraryUtils.ts` | `extensions: 'Extended fields'` settings label |

No backend file, no Alembic revision, no new npm dependency, no new API service.

Beyond the original plan: three new components rather than one (the picker modal and the
runtime cards were split out to keep each file focused), the disallowed-type constant, and
steps 2–3 of the wizard now show option *labels* rather than raw values — the persisted
`enum_labels_2` from §12.3 made that a two-line change, and leaving it would have shown
"voip" on a checkbox next to a card headed "VoIP".

## 15. Verification

No automated tests — explicitly out of scope at the user's request.

Manual pass:

1. Settings → Forms: create a `picklist_multi` field, pick both picklists, toggle **Extend
   Field** on, add library fields to two of the options, leave one option empty, save.
2. Reopen the field: toggle still on, chips still there, empty option still empty.
3. Repeat 1–2 in Settings → Fields (Field Library) to confirm the second surface and that a
   new field version is created.
4. Open a record using that form: select two options in a row → both cards appear; deselect
   one → its card and its values disappear; switch rows → values are per row.
5. Fill a required extension field's sibling only → save is blocked with the row/option
   prefixed message; fill it → save succeeds.
6. Reload the record: values persist. Check the slide-over and a CSV export show them.
7. Confirm a `picklist_multi` field with Extend Field **off** is unchanged end to end.
8. Edit the second picklist to remove a configured option, re-save the field: that option's
   extension config is dropped.
9. `cd frontend && npm run build` (type check) clean; existing Playwright suite green.

## 16. Risks

| Risk | Mitigation |
|---|---|
| `__plm__:` blob grows large with many options × fields | `description` is `Text`; watch, and revisit only if a real form hits a problem |
| Snapshot drift from the Field Library | Deliberate (D2). The chip shows the library field name; re-adding refreshes the snapshot |
| Pruning on deselect loses typed values | Accepted; documented in §7 |
| Two configurator surfaces diverging | Single shared component (3) + single shared resolver (6), as with today's picklist config |

---

## 17. Publish-blocking bugs found while validating (10 Sep 2026)

Publishing a funnel whose Method pins a `picklist_multi` field failed with
`orphaned_entity_schema_field` plus an `entity_schema_field_drifted` warning. Three
pre-existing defects, all fixed here; none of them are introduced by the Extend Field work.

1. **A pinned Method's field was reported as an orphan.**
   `_validate_entity_schema_against_active_forms`
   (`backend/workflow/services/entity_schema.py:462`) compared *every* embedded schema field
   against the active forms, but a field a pinned Method contributed
   (`EntityField.source_states` non-empty) is authored in the Method Library and merged in
   at publish time — no form ever owned it. Any Method field absent from a form therefore
   blocked publishing. The orphan set is now built from the workflow's own fields only; the
   "form has fields this workflow hasn't picked up" and retype checks are unchanged.

2. **The funnel builder recorded the wrong engine type for several form field types.**
   `mapFormFieldTypeToEntityType` (`frontend/src/lib/state-machine/entitySchema.ts:9`)
   mapped `multi_select` to `json`, `picklist_multi` to `string` (via its default), `textarea`
   to `text` and `select` to `enum` even with no options, while the drift check compares
   against the *persisted* form type run through the backend's `_normalize_form_field_type`
   — `multi_select` for both multi-value types, `string` for `text`/`textarea`/optionless
   `select`. Every multi-select, picklist and textarea field therefore reported permanent
   drift. The mapper now mirrors that pipeline and carries `enum_values` for `multi_select`
   as well as `enum` (an optionless picklist still travels as `json`, which is the one shape
   `EntityField` accepts without options).

3. **A record write declared a multi-value field's type as something that rejects its own
   value.** `mapFormFieldTypeToEntityType` in `frontend/src/shared/utils/entityForm.ts:427`
   feeds `schema_fields` on entity create/update, which the workflow type-checks with
   `matches_workflow_value` (`backend/workflow/models/interface.py:113`). It sent `enum` for
   a `multi_select` with options and `string` for a `picklist_multi` — and that matcher
   accepts a list only for `multi_select` and `json`, so the field's own array value failed
   validation. Both now map to `multi_select` (`json` when optionless), and
   `picklist_multi` carries its `enum_values` like the other two.

Verified: `tests/test_workflow_validation.py` 35 passed; a throwaway check confirmed a
Method-contributed field no longer orphans while a workflow-owned field missing from its
form still does; `tsc -b --force` clean; frontend unit suite 14 passed. The six unrelated
failures in `test_architecture_constraints.py` and the `stat414` benchmark, and the
`ruff` import-order finding in `entity_schema.py`, all reproduce on `HEAD`.

### 17.4 The Method-pin path had to become native after all (10 Sep 2026)

Reported symptom: a `picklist_multi` field with Extend Field configured rendered in the New
Entity dialog as a flat chip list of the *first* picklist's options — no items, no extended
fields.

Cause: that organization has **no** rows in `entity_type_schema` at all, so its record forms
are synthesised from the workflow's resolved `entity_schema` / `method_schemas`
(`buildFallbackFormSchemasFromEntitySchema`), i.e. entirely through the Method-pin path —
the one place §12.1 had documented as dropping the second picklist. The `__plm__:` blob
never entered the picture, and the field arrived as a bare `multi_select`.

Fixed end to end, which also retires the `__plm__:` write hack:

- `EntityField` (`backend/workflow/models/interface.py`) gains `picklist_id_2`,
  `enum_values_2`, `enum_labels_2` and `extensions`, accepted only on a `multi_select` field.
  `extensions` is validated as option → `{fields: [...]}`, and options that reveal nothing
  are dropped.
- `_entity_field_from_method_field` (`backend/workflow/manager.py`) copies all four out of
  the library field's `settings` for config kind `picklist`.
- `toEntityField` (`frontend/src/lib/state-machine/methodFields.ts`) mirrors that, and
  `EntityField` in `lib/state-machine/types.ts` carries the keys (typed with the same
  `FieldExtension` as the form side).
- `buildFallbackFormSchemaFromEntitySchema`
  (`frontend/src/lib/state-machine/entitySchema.ts`) treats `picklist_id_2`/`extensions` as
  the discriminator that restores `type: 'picklist_multi'`, exactly as `table_config`
  already restores a table, and passes the keys through.
- `mapEntityFieldToFormField` / `mapFormFieldToEntityField`
  (`frontend/src/core/services/api/formSchemas.ts`) read **and write** the native keys; the
  `__plm__:` branch remains read-only, for rows written earlier.
- `CELL_CONFIG_KEYS` (`backend/grid_forms/models/interface.py`) allows `extensions`, so a
  grid-form cell no longer silently drops it (it already allowed `picklist_id_2`).

Operational note: `_resolve_pinned_method_fields` states that a state's `method_refs` are
resolved "here and only here … Nothing re-resolves on its own", so an already-published
workflow keeps its old snapshot. The backend must be restarted onto this code **and the
workflow republished** before a pinned field shows its extensions.

Verified: 183 backend tests pass across the workflow, publish, pinning, inherited-fields,
forms and calc suites (only the pre-existing `stat414` benchmark fails, as it does on
`HEAD`); throwaway checks confirmed the pinned field keeps both picklists and its
extensions, that `extensions` is refused on a non-multi_select field, that an empty option
is dropped, and that the synthesised record form comes back as `picklist_multi` with every
key intact; `tsc -b --force` clean; frontend unit suite 14 passed; no new ruff or eslint
findings against `HEAD`.

### 17.5 Derived fields were compared against their own stale copy (10 Sep 2026)

Publishing then failed with `pinned_method_field_conflict`: *"state 'INITIAL' pins a method
that defines field 'test' differently from the workflow's own fields"* — for a workflow whose
only definition of `test` **is** that method.

Cause: `_resolve_pinned_method_fields` (`backend/workflow/manager.py`) seeded its merge from
every field in the incoming `definition.entity_schema.fields`, labelled "the workflow's own
fields". But a field carrying `source_states` was written there by an earlier run of that
same resolver, and the client echoes the whole definition back on the next publish. So this
pass compared its fresh resolution of the pinned field against the previous pass's snapshot
of it — and reported a clash the moment the pinned library field changed shape. Adding
`picklist_id_2` / `extensions` to the resolution (§17.4) was simply the first change big
enough to trigger it; nothing in the builder can edit those derived fields to reconcile them.

Fixed: only fields with **empty** `source_states` — the workflow's own authored fields —
seed the merge; a derived field is rebuilt by the resolution instead of being compared
against it. A genuine clash (an authored field and a pinned method both defining the same
key, or two methods disagreeing) still reports exactly as before. The no-pins early return
now also drops leftover derived fields, so a field whose method was unpinned leaves the
schema with the pin that produced it rather than lingering in every record form built from
it.

Verified: 186 tests pass across the pinning, publish, validation, inherited-fields,
source-intent, workflow and forms suites (only the pre-existing `stat414` benchmark fails);
a throwaway check confirmed a stale derived copy no longer clashes and is replaced by the
freshly resolved field (second picklist and extensions present), while an authored field of
the same key still raises `PINNED_METHOD_FIELD_CONFLICT`. `ruff` findings on
`workflow/manager.py` unchanged from `HEAD` (2, both pre-existing).

The organization's pinned field was confirmed in the database to carry
`picklist_id_2`, 42 `enum_values_2` and 2 configured extension options — the nulls in the
failing payload were the pre-restart snapshot, not missing configuration. Re-publishing
rebuilds them; no manual cleanup is needed.

### 17.5 `document` as an extension field (built after the original spec)

§12.5 excluded `document` because the backend only claimed unowned files for **top-level**
schema fields, so a file uploaded against a nested document field before its record existed
stayed unowned: invisible to the record's file list and never validated.

The walker now descends one level:

- `_validate_extension_document_values` (`backend/entities/manager.py:1199`) visits each
  `picklist_multi` field's `extensions`, then each row's `extensions`, for the options still
  present in the configuration. Values under an option since removed or renamed are left
  untouched rather than pruned — the specs that say which values are file ids are gone with
  the option, and dropping a user's answers because an administrator renamed something is
  worse than leaving them. Those files stay unclaimed.
- `_read_option_document_values` (`:1242`) picks the option's specs whose `type` is
  `document`, resolves the ids, and collects unowned ones under the nested key
  `<field>.<option>.<extension field id>`, which `_attach_unowned_document_files` then
  claims exactly as it does for a top-level document field.

So `document` is no longer in `EXTENSION_DISALLOWED_TYPES`
(`frontend/src/pages/settings/components/form-config/constants.ts`), whose comment now
records that support rather than the original exclusion. The remaining disallowed types are
`section`, `picklist_multi`, `reference`, `auto_number` and `timer_duration`.
