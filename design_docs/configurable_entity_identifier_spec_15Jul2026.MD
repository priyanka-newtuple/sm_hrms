# Configurable Entity Identifier — Spec

**Date:** 15 July 2026
**Status:** Implemented (STAT-353)
**Branch (planned):** `feat/STAT-353-configurable-identifier` (assign ticket number before starting)

---

## 1. Overview

Today every entity carries a required `identifier` key in `data` (`IDENTIFIER_FIELD_KEY = "identifier"`), typed manually by the user at create time and validated for uniqueness per entity type. This feature lets an admin, per entity type:

1. **Rename** the identifier label (e.g. "Candidate ID", "Project Code").
2. **Configure a template** that auto-generates the identifier from form field values and/or a per-type sequence counter, e.g. `{{first_name}}-{{last_name}}` or `INV-{{seq}}`.
3. **Preview** the generated identifier before saving the template.

When a template is configured, identifiers are backend-generated at create time, deduplicated with `_2`/`_3` suffixes, immutable thereafter, and never trusted from client payloads.

### Goals

- Zero-migration config storage (except one new uniqueness index migration).
- One shared generation function wired into **every** entity-create path.
- Types without a template behave exactly as today (manual entry).



### Non-goals (explicitly out of scope)

- Retroactive regeneration of identifiers for existing entities (identifiers are immutable; template changes apply to new creates only).
- Backfilling identifiers for legacy entities created without one (public-form-created entities may lack an identifier; they stay that way).
- Configurable slugify rules, separator characters, or `{{seq}}` pad width.
- Fixing the pre-existing gap where the **manual-mode** update path does not re-validate uniqueness (unchanged behavior; template mode sidesteps it via immutability).
- Per-form (rather than per-entity-type) identifier config.

---



## 2. Config storage

Two optional keys added to the existing `entity_types.schema_definition` JSON column — **no migration needed**:

```json
{
  "fields": [ ... existing ... ],
  "identifier_label": "Candidate ID",
  "identifier_template": "{{first_name}}-{{last_name}}-{{seq}}"
}
```

- Both keys optional and independent. Label without template is valid (rename only). Template without label is valid.
- Absent/empty `identifier_template` → **manual mode**, today's behavior exactly.
- Carried through the existing `EntityTypeCreateRequest` / `EntityTypeUpdateRequest` (`schema_definition: dict`) — no new endpoints.
- `identifier_label`: trimmed, max 64 chars, plain string (React escapes on render).
- `identifier_template`: trimmed, max 256 chars.



## 3. Template language



### Tokens

- Syntax: `{{field_id}}` matched by `\{\{\s*([A-Za-z0-9_]+)\s*\}\}` (whitespace inside braces tolerated, token normalized to lowercase).
- **Field tokens** resolve to `entity.data[field_id]` at create time. Allowed field types (validated at save): `text`, `textarea`, `email`, `phone`, `url`, `select`/`enum`, `integer`, `number`, `date`, `datetime`, `auto_number`, **`reference`** (see below). Excluded: `table`, `multi_select`, `picklist_multi`, `boolean`, `section`.
- **Reference (relationship) tokens**: a `reference` field id (a field inherited from a related entity, e.g. `client_name` on a Filing form pointing at the linked Client's name) is a valid token. Resolution: after the record **and its relations** are persisted (same transaction), the existing read-time resolver (`resolve_inherited_fields`) computes the inherited overlay, and the template renders against `data + overlay`. The identifier therefore matches exactly what the user sees in that reference field at creation time. No relation attached at create → token renders blank (blank-skip rule). Re-pointing or removing the relation later does **not** regenerate the identifier (immutability).
- **Reserved token** `{{seq}}`: **prefix-scoped** sequence counter. The counter is keyed by the rendered template with all `{{seq}}` slots removed (the "prefix context"), so `{{client_name}}-{{seq}}` numbers each client independently — `acme-0001`, `globex-0001`, `acme-0002` — while a constant-prefix template like `INV-{{seq}}` behaves as one global per-type sequence (`INV-0001`, `INV-0002`, …). Always the counter, even if a form field with id `seq` exists — the save-time validator flags that clash as a warning.
- Anything not matching the token regex (including malformed braces like `{{first_name}`) is a **literal** and passes through verbatim.
- Duplicate field tokens allowed (render twice). Multiple `{{seq}}` occurrences consume **one** counter value, substituted into all occurrences (the prefix context excludes every seq slot).



### Value normalization (slugify)

Applied to **field token values only** — literals and the `{{seq}}` value pass through untouched:

1. Coerce to `str()`. `None`, empty string, lists/dicts (shouldn't occur given type restrictions, but runtime data is untyped JSONB) → empty string.
2. Unicode NFKD-normalize and strip diacritics (`José` → `Jose`) — stdlib `unicodedata`.
3. Lowercase.
4. Replace every run of characters outside `[a-z0-9]` with a single `-`.
5. Strip leading/trailing `-`.



### Assembly

1. Substitute all tokens in one pass (values are inserted post-slugify; a value literally containing `{{seq}}` cannot inject — braces are stripped by slugify, and there is no re-scan).
2. Collapse runs of separators (`-` and `_`) left by blank values to a single character (`john--smith` → `john-smith`).
3. Strip leading/trailing separators (`-john-` → `john`).
4. Truncate the result to **120 chars** (before collision suffix).
5. **Empty-result fallback:** if the rendered base is empty (all tokens blank, no literals), use the counter value alone (`0007`, empty prefix context), consuming one counter increment. Guarantees a non-empty identifier without failing the create.

### Worked example — Client → Filing

Client type: template `{{client_name}}` (or manual). Filing type: template `{{client_name}}-{{seq}}` where `client_name` is a **reference field** on the Filing form, inherited from the linked Client.

| Action | Result |
|---|---|
| Create filing linked to client Acme | `acme-0001` |
| Create filing linked to client Globex | `globex-0001` (own counter) |
| Second filing for Acme | `acme-0002` |
| Filing created with no client link | `0003`-style seq-only? No — blank prefix has its **own** counter: `0001` |
| Client Acme renamed to AcmeCorp | Existing filings keep `acme-*`; next filing renders `acmecorp-0001` (new prefix context, fresh counter). Collision suffix still guards any overlap. |

User never types the filing identifier — input hidden, value generated server-side at create.



## 4. Generation algorithm

One shared helper, new module `backend/common/identifier_template.py`:

```
generate_identifier(db, organization_id, entity_type, data) -> str | None
```

Returns `None` when the type has no template (manual mode — caller falls through to existing behavior). Otherwise, **inside the create transaction, after the record and its relations are inserted**:

1. Resolve the inherited-field overlay via the existing `resolve_inherited_fields` (only when the template contains reference tokens; skipped otherwise). Merge over `data` for rendering.
2. Render template (section 3). `{{seq}}` pulls `_get_next_auto_number(db, org, entity_type_id, field_key)` with `field_key = "__idseq__:" + <prefix context, truncated to 100 chars>` — the dunder prefix cannot collide with real `auto_number` field ids (`field_key` column is `String(128)`; truncation may merge counters for near-identical 100+-char prefixes, harmless — the collision suffix still guarantees uniqueness). Zero-padded to 4 digits, natural overflow (`9999` → `10000`), same as existing auto_number formatting.
3. Collision check against **all** entities of that type in the org, **including archived** (prevents restore-time duplicates — note: the current manual-mode validator excludes archived; template mode deliberately widens scope). Query on `data->>'identifier'`, exact match (case-sensitive).
4. On collision: find smallest free suffix — fetch identifiers matching `base` or `base_<n>` pattern, next = max(n) + 1, starting at `_2`. A pre-existing manually typed `john-smith_2` is skipped naturally (query covers it). The `_` suffix delimiter is deliberately a character slugify never emits from values (it maps `_` → `-`), so suffixes are only ambiguous against template *literals* containing `_<digits>` — accepted, the full-string match keeps this safe.
5. Write generated value into `data["identifier"]`, **overwriting** any client-supplied value (never trust payloads — same rule as auto_number fields). Since generation runs after insert, this is an in-transaction `UPDATE` of the row's `data`; the unique index validates it atomically with the commit.



### Wired into every create path


| Path                             | Hook point                                                                                                                                                           |
| -------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| API / agent tools                | `EntitiesServiceManager.create_entity_record_for_actor` — replaces the `_validate_unique_identifier` call when template mode (manual mode keeps existing validation) |
| Public form, new-entity branch   | `forms/db_models.py submit_public_form` — beside the existing `_with_auto_numbers` call                                                                              |
| Deferred form, new-entity branch | `forms/db_models.py save_deferred_fields_to_entity` — same                                                                                                           |


The audit event payload (`identifier` in `CREATED` payload) picks up the generated value automatically since it reads `record.data` post-create.

Public-form and deferred-form creates carry **no relations**, so reference tokens render blank on those paths (blank-skip). Field and `{{seq}}` tokens work everywhere.

### Concurrency

`{{seq}}` counter increment is atomic (existing `auto_number_counters` row lock). The collision-check → insert window is protected by the new unique index (section 5): an `IntegrityError` on insert triggers **one retry** with a re-computed suffix; second failure surfaces as a 409-style validation error. `// ponytail: single retry; move to counter-keyed identifiers if contention ever shows up in logs`.

## 5. Uniqueness index (the one migration)

New Alembic migration `2026_07_15_0001_identifier_unique_index`:

1. **Dedupe pre-step:** scan for duplicate `(organization_id, entity_type_id, data->>'identifier')` groups (identifier non-null, non-empty); keep the oldest row, append `_2`, `_3`, … to the rest. Logged count.
2. Partial unique functional index on `entities`: `(organization_id, entity_type_id, (data->>'identifier'))` `WHERE data->>'identifier' IS NOT NULL AND data->>'identifier' <> ''`.

This closes the pre-existing check-then-insert race for manual mode too, and lets the O(n) `_validate_unique_identifier` scan become an indexed point lookup (included in this work).

Rows with no identifier (legacy public-form creates) are outside the index — unaffected.

## 6. Immutability

When the entity's type has a template:

- `update_entity_record_for_actor`: strip `identifier` from `requested_changes` **before** the merge with `before_data` (silent drop, matching the established auto_number lock pattern in `patch_entity_data`). Stored value always wins. No audit noise (dropped before changed-field diffing).
- `patch_entity_data` (forms path): add `identifier` to the locked-keys set when template mode.
- Source field edits later (`first_name` John → Jon) do **not** touch the identifier — generation happens exactly once, at create.
- Restore/unarchive keeps the stored identifier. Collision on restore is impossible going forward (uniqueness scope includes archived rows).
- Manual mode: identifier stays editable exactly as today.



## 7. Save-time validation & degradation



### On entity type create/update (backend, `EntitiesServiceManager`)

When `schema_definition.identifier_template` is present and non-empty:

- Must contain **at least one token** (field or `{{seq}}`) — literal-only templates rejected (every entity would collide into suffix soup). → 400.
- No stray `{`/`}` outside well-formed tokens — `{client_identifier}}` is a typo that would render literally. → 400, plus a live warning in the editor.
- `{{<related_type>_identifier}}` tokens are valid whenever an active relation declaration targets the type — resolved from the linked source entity's identifier at create, no reference form field required.
- Every field token must resolve to an allowed-type field (section 3) on the **active linked forms** (`active_schema_fields` for the type name) or in the type's own `schema_definition.fields`. Unknown/wrong-type tokens → 400 listing the offending tokens: `"identifier_template references unknown or unsupported fields: employee_num, dept"`.
- Reference-field tokens: valid when the id belongs to a `reference` field on a linked form (legacy dotted ids like `client.name` are not tokens — the token regex already can't match `.`).
- No linked forms at all → only `{{seq}}` and literals are valid.
- A linked form field with id `seq` → template still saves, response includes a warning (`{{seq}}` is reserved and will always mean the counter).
- `identifier_label` > 64 chars or `identifier_template` > 256 chars → 400.



### Degradation at runtime (decided: warn, degrade — never block creates)

A field token that no longer resolves (field deleted, form unlinked/deactivated after template save) renders as **blank** → skipped segment via separator collapse. Entity creation never fails because of a stale template. All-tokens-blank → counter fallback (section 3).

### Admin warnings (frontend, client-side — no new endpoints)

- **Entity Type screen:** warning badge on a type whose template references fields missing from currently linked active forms (computed from already-loaded schemas).
- **Form editor (form-config):** deleting a field or unlinking/deactivating a form that an identifier template references → confirm dialog naming the field(s) and entity type(s): "Field `first_name` is used in the identifier template of Candidate. Identifiers will skip it until the template is updated." Proceed allowed.



### Field rename cascade

`_cascade_field_renames` (entities manager) already rewrites `field_permissions` when a field id changes in `schema_definition`. Extend it to also rewrite matching tokens inside `identifier_template` — a rename then never breaks a template.

## 8. Label resolution (frontend)

Precedence, per context where the identifier label is shown:

1. Entity type's `schema_definition.identifier_label` (new, type-scoped).
2. Existing `getIdentifierLabel(entityType)` derivation (`"jsi_client"` → "Client Unique Name").
3. Org-wide `columnLabels.identifier` override / `"Unique Name"` default — stays as-is for mixed-type contexts (generic list column headers).

Surfaces: AddEntityDialog, CreateEntityModal, record detail, pipeline list column (type-scoped views), settings preview.

## 9. Backend changes


| File                                            | Change                                                                                                                                                                                                                                          |
| ----------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `backend/common/identifier_template.py`         | **NEW** — token parse, slugify, render, suffix helpers (pure functions, no DB)                                                                                                                                                                  |
| `backend/entities/manager.py`                   | Template-mode branch in `create_entity_record_for_actor`; strip identifier in `update_entity_record_for_actor`; template validation in entity type create/update; extend `_cascade_field_renames`; indexed uniqueness lookup replaces O(n) scan |
| `backend/entities/db_models.py`                 | Collision-query helper (`data->>'identifier'` lookups incl. archived); insert retry on `IntegrityError`                                                                                                                                         |
| `backend/forms/db_models.py`                    | Call generation in the two new-entity branches; add identifier to `patch_entity_data` locked keys when template mode                                                                                                                            |
| `backend/alembic/versions/2026_07_15_0001_*.py` | **NEW** — dedupe + partial unique index                                                                                                                                                                                                         |
| `backend/tests/`                                | New test module (see section 12)                                                                                                                                                                                                                |




## 10. Frontend changes


| File                                                        | Change                                                                                                                                                                  |
| ----------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `pages/settings/components/entity-types/EntityTypesTab.tsx` | Editor modal: label input, template input, insert-field chips (fields fetched from linked forms), live preview with editable sample values, missing-field warning badge |
| `shared/utils/entityForm.ts`                                | FE slugify+render mirror (~20 lines, preview only — `{{seq}}` previews as `0001` sample); label precedence helper                                                       |
| `pages/Pipeline/components/AddEntityDialog.tsx`             | Template mode → hide identifier input                                                                                                                                   |
| `pages/records/detail/components/CreateEntityModal.tsx`     | Same                                                                                                                                                                    |
| `pages/records/detail/index.tsx`                            | Template mode → identifier read-only                                                                                                                                    |
| `pages/settings/components/form-config/*` (form editor)     | Breaking-change confirm dialogs on field delete / form unlink                                                                                                           |
| `core/types/index.ts`                                       | `EntityType.schema_definition` typing incl. new keys (verify it's exposed; add if missing)                                                                              |




## 11. Security

- Multi-tenancy: every query org-scoped (existing patterns); template lives on the org's entity type row.
- Client-supplied `identifier` ignored on create (template mode) and on update (template mode) — server-generated only. Public-form (anonymous) path included.
- Template stored/validated server-side; token allow-list prevents referencing arbitrary keys outside linked-form fields (no leakage of unexpected `data` keys into visible identifiers beyond what forms define).
- Entity type config changes gated by the existing entity-type write authorization.
- Label/template length caps; no HTML rendering (React text nodes).



## 12. Edge case matrix


| #   | Case                                                        | Behavior                                                                |
| --- | ----------------------------------------------------------- | ----------------------------------------------------------------------- |
| 1   | No template configured                                      | Manual mode — today's behavior, identifier required + editable          |
| 2   | Template + client sends identifier on create                | Client value overwritten by generated value                             |
| 3   | Blank field value (`{{employee_number}}` empty)             | Segment skipped, separators collapsed (`john` not `john-`)              |
| 4   | All tokens blank, no literals                               | Counter fallback (`0007`), one seq increment consumed                   |
| 5   | All tokens blank, literals present (`CAND-{{x}}`)           | `CAND` (literals survive, separators trimmed)                           |
| 6   | Duplicate render (`john-smith` exists)                      | `john-smith_2`, then `_3`, …                                            |
| 7   | Manual-era `john-smith_2` already exists                    | Suffix search skips to `_3`                                             |
| 8   | Unicode value `José Müller`                                 | NFKD + diacritic strip → `jose-muller`                                  |
| 9   | Value with emoji/symbols `J@hn 😀`                          | Stripped → `j-hn`                                                       |
| 10  | Value containing `{{seq}}` as literal text                  | Braces slug-stripped; single-pass substitution, no injection            |
| 11  | Integer/number/date values                                  | Stringified then slugified (`42`, `2026-07-15`)                         |
| 12  | Unknown token at save                                       | 400 listing tokens                                                      |
| 13  | Literal-only template at save                               | 400 (must contain ≥1 token)                                             |
| 14  | Malformed braces `{{first_name}`                            | **Rejected at save (400)** — stray `{`/`}` outside well-formed tokens is always a typo. Editor shows a live warning. (Pre-existing saved templates with stray braces still render them literally at create time.) |
| 15  | `{{ first_name }}` with spaces                              | Trimmed, works                                                          |
| 16  | Uppercase token `{{First_Name}}`                            | Normalized to lowercase id                                              |
| 17  | Same token twice                                            | Substituted twice                                                       |
| 18  | `{{seq}}` twice in one template                             | One counter value, both occurrences identical                           |
| 19  | Form field literally named `seq`                            | Reserved token wins; save returns warning                               |
| 20  | Field deleted after template saved                          | Runtime: blank-skip. Admin: badge + confirm dialog at delete time       |
| 21  | Form unlinked/deactivated after save                        | Same as 20                                                              |
| 22  | Field renamed in form editor                                | `_cascade_field_renames` rewrites template token — no breakage          |
| 23  | Template added after entities exist                         | Old identifiers untouched; new creates generated                        |
| 24  | Template edited                                             | Applies to new creates only. Unchanged prefix context → counter continues; changed prefix → fresh counter (suffix guards overlap). Counters never reset in place |
| 25  | Template removed (cleared)                                  | Type reverts to manual mode; existing identifiers untouched             |
| 26  | Source field edited post-create                             | Identifier unchanged (immutable)                                        |
| 27  | Update payload tries to change identifier (template mode)   | Silently stripped pre-merge, stored value wins                          |
| 28  | Archived entity holds `john-smith`, new create renders same | Suffix applied (`_2`) — uniqueness scope includes archived              |
| 29  | Restore of archived entity                                  | Keeps identifier; no collision possible (28)                            |
| 30  | Concurrent creates, same base                               | Unique index + one insert retry with recomputed suffix                  |
| 31  | Concurrent creates with `{{seq}}`, same prefix              | Atomic counter (existing row lock) — distinct values                    |
| 32  | Seq overflow past 9999                                      | `10000` — natural widening, same as auto_number                         |
| 33  | Very long values                                            | Base truncated at 120 chars before suffix                               |
| 34  | Public-form entity creation (anonymous)                     | Generation runs server-side; same rules                                 |
| 35  | Deferred-form entity creation                               | Same                                                                    |
| 36  | Cross-type create (form targets different type)             | Target type's template applies                                          |
| 37  | Entity types with shared form (two types link one form)     | Each type has own template/counter; same field tokens fine              |
| 38  | No linked forms                                             | Only `{{seq}}` + literals validate                                      |
| 39  | Empty template string saved                                 | Treated as manual mode (key ignored/cleared)                            |
| 40  | Label set, no template                                      | Rename-only: label shows everywhere, manual entry keeps working         |
| 41  | Label cleared                                               | Falls back to derivation → org columnLabels chain                       |
| 42  | Migration finds existing duplicate identifiers              | Dedupe pre-step: oldest keeps value, rest get `_2`, `_3`; count logged  |
| 43  | Legacy entities with no identifier at all                   | Outside partial index; untouched, stay identifier-less                  |
| 44  | Reference token, relation attached at create (Filing→Client) | Renders linked entity's field via inherited resolver: `acme-0001`      |
| 45  | Reference token, no relation at create                      | Blank-skip; blank prefix gets its own counter (`0001`)                  |
| 46  | Relation re-pointed/removed after create                    | Identifier unchanged (immutable, same as field edits)                   |
| 47  | Linked client renamed after filings exist                   | Old filings keep old prefix; new filings use new prefix + fresh counter |
| 48  | Two prefixes, independent numbering                         | `acme-0001`, `globex-0001`, `acme-0002` — counter per prefix context    |
| 49  | Prefix context > 100 chars                                  | Counter key truncated; near-identical long prefixes may share a counter — suffix still guarantees uniqueness |
| 50  | Multiple relations/links resolve the same reference field   | Same semantics as read-time inherited resolution (first matching link per declaration) — identifier equals what the user sees |




## 13. Testing (backend pytest — CI only, local Python is 3.11)

- **Pure render tests** (`identifier_template.py`, no DB): slugify (unicode, emoji, case, numbers), blank-skip + collapse, literal passthrough, malformed braces, duplicate tokens, single-pass injection safety, truncation, empty fallback signal.
- **Generation integration**: template mode create (API path) — overwrite client value, collision `_2`/`_3`, manual `_2` pre-existing, archived-inclusive uniqueness, seq increment + multi-occurrence, seq/field mix, cross-type public-form create, counter fallback.
- **Reference + scoped seq**: filing-with-client-link renders `acme-0001`; per-prefix independence (`globex-0001`, `acme-0002`); no-link create → blank prefix counter; relation re-point → identifier stable; prefix-change → fresh counter with suffix guard.
- **Immutability**: update strips identifier (template mode), manual mode still editable, patch path lock.
- **Validation**: unknown token 400, literal-only 400, wrong-type token 400, `seq`-field-name warning, length caps, empty template = manual.
- **Cascade**: field rename rewrites template.
- **Migration**: dedupe logic unit-tested against seeded duplicates.
- Frontend: preview render mirror unit test (vitest if present, else skip — preview is non-authoritative).



## 14. Open items

- Ticket: STAT-353 (assigned).
- ~~Confirm `EntityType` API response exposes `schema_definition` to the frontend list endpoint.~~ Confirmed and represented by `EntityTypeSchemaDefinition` in the frontend types.
- Prod data check before migration: count of existing duplicate identifiers (dedupe step handles it, but worth eyeballing the log on staging first).
