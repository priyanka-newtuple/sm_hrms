# Configurable Entity Identifier (STAT-353) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Per-entity-type identifier label rename + template-based auto-generation (`{{field}}`, reference fields, prefix-scoped `{{seq}}`) with collision suffixes, immutability, validation, and admin preview.

**Architecture:** Config lives in `entity_types.schema_definition` JSON (keys `identifier_label`, `identifier_template`). A pure render module (`backend/common/identifier_template.py`) is orchestrated by a DB-layer hook inside `create_entity_record`'s transaction (after relations link, before commit) so reference tokens resolve from the just-created links. Counters reuse `auto_number_counters`. One migration adds a partial unique index on `(org, type, data->>'identifier')`. Frontend mirrors the render for preview only.

**Tech Stack:** FastAPI + SQLAlchemy 1.4 + Pydantic (backend), React 19 + TS (frontend), Alembic, pytest.

**Spec:** `design_docs/configurable_entity_identifier_spec_15Jul2026.MD` — read it first, especially §3 (template language), §4 (generation), §12 (edge matrix).

## Global Constraints

- Git is handled by the user — this plan contains no branch/commit/push steps. Just edit files; the user commits when they choose.
- Backend tests: require the project Postgres (conftest default `postgresql://statemachine:statemachine@modular-db:5432/statemachine`, schema `modular_backend`). Local host Python is 3.11 and the backend needs 3.12 — run pytest inside the project's docker env if host runs fail on version/connection. Command form: `cd backend && python -m pytest tests/<file> -v`.
- Frontend gate: `cd frontend && npm run build` (tsc runs inside). No FE unit-test runner exists — do not add one.
- Identifier data key is `"identifier"` (`IDENTIFIER_FIELD_KEY`, defined backend `entities/models/interface.py:15`, frontend `shared/utils/entityForm.ts:4`).
- Reserved seq token: `{{seq}}`. Counter field_key prefix: `__idseq__:`. Pad width 4. Base identifier max 120 chars. Label max 64, template max 256.
- Wire key for entity type config is `schema_definition` (backend request/response). The frontend's existing `schema?: EntityTypeSchema` on `EntityTypeCreateRequest`/`EntityTypeUpdateRequest` is stale/ignored by the backend — Task 7 fixes the types; always send `schema_definition`.
- All new queries must filter `organization_id` (multi-tenancy).
- Slugify semantics (spec §3, must match FE/BE): str → NFKD + strip diacritics → lowercase → runs of `[^a-z0-9]` → single `-` → strip edge `-`.

---

### Task 1: Pure template engine

**Files:**
- Create: `backend/common/identifier_template.py`
- Test: `backend/tests/test_identifier_template.py`

**Interfaces:**
- Produces (later tasks import these from `common.identifier_template`):
  - `IDENTIFIER_MAX_BASE_LENGTH: int = 120`
  - `SEQ_COUNTER_KEY_PREFIX: str = "__idseq__:"`
  - `SEQ_PAD_WIDTH: int = 4`
  - `TOKEN_RE: re.Pattern` — matches `{{ token }}`
  - `parse_tokens(template: str) -> list[str]` — lowercased token ids, in order, duplicates preserved
  - `has_seq_token(template: str) -> bool`
  - `slugify_value(value: object) -> str`
  - `render_identifier(template: str, values: dict, seq_value: str | None = None) -> str` — full assembly, may return `""`
  - `prefix_context(template: str, values: dict) -> str` — render with seq slots removed (counter scope key)
  - `format_seq(counter: int) -> str` — zero-pad 4
  - `next_suffixed(base: str, existing: set[str]) -> str` — `base`, `base_2`, `base_3`, …

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_identifier_template.py`:

```python
"""Pure-function tests for common.identifier_template (spec §3, §12 rows 3-18, 32-33)."""

from __future__ import annotations

from common.identifier_template import (
    IDENTIFIER_MAX_BASE_LENGTH,
    format_seq,
    has_seq_token,
    next_suffixed,
    parse_tokens,
    prefix_context,
    render_identifier,
    slugify_value,
)


class TestSlugify:
    def test_lowercase_and_spaces(self):
        assert slugify_value("John Smith") == "john-smith"

    def test_unicode_diacritics_stripped(self):
        assert slugify_value("José Müller") == "jose-muller"

    def test_emoji_and_symbols_stripped(self):
        assert slugify_value("J@hn 😀") == "j-hn"

    def test_numbers_pass_through(self):
        assert slugify_value(42) == "42"
        assert slugify_value("2026-07-15") == "2026-07-15"

    def test_none_and_empty(self):
        assert slugify_value(None) == ""
        assert slugify_value("   ") == ""

    def test_lists_and_dicts_blank(self):
        assert slugify_value(["a", "b"]) == ""
        assert slugify_value({"a": 1}) == ""

    def test_underscore_becomes_dash(self):
        assert slugify_value("smith_2") == "smith-2"


class TestParseTokens:
    def test_basic(self):
        assert parse_tokens("{{first_name}}-{{last_name}}") == ["first_name", "last_name"]

    def test_whitespace_and_case_normalized(self):
        assert parse_tokens("{{ First_Name }}") == ["first_name"]

    def test_malformed_braces_not_tokens(self):
        assert parse_tokens("{{first_name}") == []

    def test_duplicates_preserved(self):
        assert parse_tokens("{{a}}-{{a}}") == ["a", "a"]

    def test_seq_detection(self):
        assert has_seq_token("INV-{{seq}}") is True
        assert has_seq_token("INV-{{ SEQ }}") is True
        assert has_seq_token("{{sequence}}") is False


class TestRender:
    def test_simple(self):
        assert render_identifier("{{first_name}}-{{last_name}}",
                                 {"first_name": "John", "last_name": "Smith"}) == "john-smith"

    def test_blank_segment_skipped_and_collapsed(self):
        assert render_identifier("{{first_name}}-{{employee_number}}",
                                 {"first_name": "John", "employee_number": ""}) == "john"

    def test_literals_pass_verbatim(self):
        assert render_identifier("PRJ-{{dept}}", {"dept": "Sales"}) == "PRJ-sales"

    def test_all_blank_with_literals(self):
        assert render_identifier("CAND-{{x}}", {"x": ""}) == "CAND"

    def test_all_blank_no_literals_empty(self):
        assert render_identifier("{{x}}-{{y}}", {}) == ""

    def test_seq_substitution_all_occurrences_same(self):
        assert render_identifier("{{seq}}-x-{{seq}}", {}, seq_value="0007") == "0007-x-0007"

    def test_value_containing_token_syntax_not_reinterpreted(self):
        out = render_identifier("{{name}}-{{seq}}", {"name": "a{{seq}}b"}, seq_value="0001")
        assert out == "a-seq-b-0001"

    def test_missing_field_blank(self):
        assert render_identifier("{{ghost}}-{{name}}", {"name": "Ann"}) == "ann"

    def test_truncation_at_120(self):
        out = render_identifier("{{a}}", {"a": "x" * 300})
        assert len(out) == IDENTIFIER_MAX_BASE_LENGTH

    def test_malformed_braces_kept_literal(self):
        assert render_identifier("{{first_name}", {"first_name": "John"}) == "{{first_name}"


class TestPrefixContext:
    def test_seq_slot_removed(self):
        assert prefix_context("{{client_name}}-{{seq}}", {"client_name": "Acme"}) == "acme"

    def test_constant_prefix(self):
        assert prefix_context("INV-{{seq}}", {}) == "INV"

    def test_no_seq_equals_render(self):
        assert prefix_context("{{a}}-{{b}}", {"a": "x", "b": "y"}) == "x-y"


class TestSeqAndSuffix:
    def test_format_seq_pads_and_overflows(self):
        assert format_seq(7) == "0007"
        assert format_seq(10000) == "10000"

    def test_no_collision_returns_base(self):
        assert next_suffixed("john-smith", set()) == "john-smith"

    def test_collision_suffixes(self):
        assert next_suffixed("john-smith", {"john-smith"}) == "john-smith_2"
        assert next_suffixed("john-smith", {"john-smith", "john-smith_2"}) == "john-smith_3"

    def test_manual_gap_skips_to_max_plus_one(self):
        assert next_suffixed("j", {"j", "j_2", "j_7"}) == "j_8"

    def test_unrelated_suffixes_ignored(self):
        assert next_suffixed("j", {"j", "jx_2", "j_x"}) == "j_2"
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd backend && python -m pytest tests/test_identifier_template.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'common.identifier_template'`

- [ ] **Step 3: Implement the module**

Create `backend/common/identifier_template.py`:

```python
"""Identifier-template rendering (spec: design_docs/configurable_entity_identifier_spec_15Jul2026.MD §3).

Pure functions only — no DB, no I/O. The DB-side orchestration lives in
entities/db_models.py.
"""

from __future__ import annotations

import re
import unicodedata

IDENTIFIER_MAX_BASE_LENGTH = 120
SEQ_TOKEN = "seq"
SEQ_COUNTER_KEY_PREFIX = "__idseq__:"
SEQ_PAD_WIDTH = 4

TOKEN_RE = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}")
_SEPARATOR_RUN_RE = re.compile(r"[-_]{2,}")
_SUFFIX_RE_TEMPLATE = r"_(\d+)$"


def parse_tokens(template: str) -> list[str]:
    """Lowercased token ids in template order, duplicates preserved."""
    return [m.group(1).lower() for m in TOKEN_RE.finditer(template or "")]


def has_seq_token(template: str) -> bool:
    return SEQ_TOKEN in parse_tokens(template)


def slugify_value(value: object) -> str:
    """NFKD → strip diacritics → lowercase → non-[a-z0-9] runs → '-' → trim."""
    if value is None or isinstance(value, (list, dict, set, tuple)):
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def _substitute(template: str, values: dict, seq_value: str | None) -> str:
    def _one(match: re.Match) -> str:
        token = match.group(1).lower()
        if token == SEQ_TOKEN:
            return seq_value if seq_value is not None else ""
        return slugify_value(values.get(token))

    return TOKEN_RE.sub(_one, template or "")


def _collapse(rendered: str) -> str:
    collapsed = _SEPARATOR_RUN_RE.sub(lambda m: m.group(0)[0], rendered)
    return collapsed.strip("-_")


def render_identifier(template: str, values: dict, seq_value: str | None = None) -> str:
    """Full assembly: substitute → collapse separators → trim → truncate.

    Returns "" when everything renders blank — the DB layer applies the
    counter fallback (spec §3 assembly step 5)."""
    base = _collapse(_substitute(template, values, seq_value))
    return base[:IDENTIFIER_MAX_BASE_LENGTH]


def prefix_context(template: str, values: dict) -> str:
    """Rendered base with seq slots removed — the counter scope key (spec §3)."""
    return render_identifier(template, values, seq_value="")


def format_seq(counter: int) -> str:
    return str(counter).zfill(SEQ_PAD_WIDTH)


def next_suffixed(base: str, existing: set[str]) -> str:
    """Smallest free `base`/`base_<n>` given the set of taken identifiers."""
    if base not in existing:
        return base
    suffix_re = re.compile(re.escape(base) + _SUFFIX_RE_TEMPLATE)
    taken = [int(m.group(1)) for value in existing for m in [suffix_re.fullmatch(value)] if m]
    return f"{base}_{max(taken, default=1) + 1}"
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `cd backend && python -m pytest tests/test_identifier_template.py -v`
Expected: PASS (all).

---

### Task 2: DB-layer generation inside create transaction

**Files:**
- Modify: `backend/entities/db_models.py` (create_entity_record at ~1085; resolve_inherited_fields at ~1666)
- Test: `backend/tests/test_identifier_generation.py` (new)

**Interfaces:**
- Consumes: everything from Task 1; existing `_get_next_auto_number(session, org, type_id, field_key)` (db_models ~305); existing `_active_declarations_by_to_type` / `_find_link_for_declaration` session helpers.
- Produces (used by Tasks 3, 4):
  - `EntitiesModelService.get_identifier_template(organization_id: str, entity_type_id: str) -> str | None` (opens own session)
  - module-level `apply_identifier_template(service, session, *, organization_id: str, entity_type: EntityTypeModel, entity_id: str | None, data: dict) -> dict` — returns data with `identifier` set when the type has a template; unchanged data otherwise. `entity_id=None` skips reference-token resolution (public-form paths).
  - `EntitiesModelService._resolve_inherited_fields_with_session(session, *, organization_id, entity_type_id, entity_id) -> dict[str, object]`

- [ ] **Step 1: Extract session-scoped inherited resolver**

In `backend/entities/db_models.py`, `resolve_inherited_fields` (~line 1666) currently wraps its whole body in `with self._db_session() as session:`. Mechanical extract — the body must be reusable inside an open transaction so uncommitted link rows are visible:

```python
def resolve_inherited_fields(
    self,
    *,
    organization_id: str,
    entity_type_id: str,
    entity_id: str,
) -> dict[str, object]:
    """Resolve inherited field values at read time. (docstring unchanged)"""
    try:
        with self._db_session() as session:
            return self._resolve_inherited_fields_with_session(
                session,
                organization_id=organization_id,
                entity_type_id=entity_type_id,
                entity_id=entity_id,
            )
    except Exception as exc:
        logger.debug("resolve_inherited_fields failed: %s", exc)
        return {}

def _resolve_inherited_fields_with_session(
    self,
    session: Session,
    *,
    organization_id: str,
    entity_type_id: str,
    entity_id: str,
) -> dict[str, object]:
    # <<< the ENTIRE former body that lived inside the `with` block,
    #     dedented one level, using the passed-in `session` >>>
```

Move the existing body verbatim (declarations loop, mapping, `_find_link_for_declaration`, REFERENCE/SNAPSHOT resolution, `<parent>_id` auto-expose). Do not change its logic. Keep any interior try/excepts as they are.

- [ ] **Step 2: Add template getter + generation orchestrator**

Add to `backend/entities/db_models.py` (near `_get_next_auto_number`, module level for the free function; the method inside `EntitiesModelService`):

```python
from common.identifier_template import (
    IDENTIFIER_MAX_BASE_LENGTH,
    SEQ_COUNTER_KEY_PREFIX,
    format_seq,
    has_seq_token,
    next_suffixed,
    parse_tokens,
    prefix_context,
    render_identifier,
)
from entities.models.interface import IDENTIFIER_FIELD_KEY
```

(Adjust to the file's existing import style/sections. `IDENTIFIER_FIELD_KEY` may already be imported — check first.)

```python
def _identifier_template_from_schema(schema_definition: dict | None) -> str | None:
    """Non-empty identifier_template string from an entity type schema, else None."""
    raw = (schema_definition or {}).get("identifier_template")
    template = str(raw).strip() if raw is not None else ""
    return template or None


def _existing_identifiers_for_base(
    session: "Session", organization_id: str, entity_type_id: str, base: str
) -> set[str]:
    """Identifiers equal to `base` or `base_<suffix>` for the type — archived included
    (spec §4 step 3: restore-safe uniqueness scope)."""
    ident = EntityRecordModel.data.op("->>")(IDENTIFIER_FIELD_KEY)
    escaped = base.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    rows = (
        session.query(ident)
        .filter(
            EntityRecordModel.organization_id == organization_id,
            EntityRecordModel.entity_type_id == entity_type_id,
            sa.or_(ident == base, ident.like(f"{escaped}\\_%", escape="\\")),
        )
        .all()
    )
    return {row[0] for row in rows if row[0]}


def apply_identifier_template(
    service: "EntitiesModelService",
    session: "Session",
    *,
    organization_id: str,
    entity_type: EntityTypeModel,
    entity_id: str | None,
    data: dict,
) -> dict:
    """Generate and set data['identifier'] when the type has a template (spec §4).

    `entity_id=None` → skip reference-token resolution (paths with no relations,
    e.g. public forms). Client-supplied identifier is always overwritten."""
    template = _identifier_template_from_schema(entity_type.schema)
    if template is None:
        return data

    values = dict(data or {})
    if entity_id is not None and parse_tokens(template):
        overlay = service._resolve_inherited_fields_with_session(
            session,
            organization_id=organization_id,
            entity_type_id=entity_type.entity_type_id,
            entity_id=entity_id,
        )
        values.update(overlay or {})

    seq_value = None
    scope = prefix_context(template, values)
    if has_seq_token(template):
        counter_key = (SEQ_COUNTER_KEY_PREFIX + scope)[:100]
        seq_value = format_seq(
            _get_next_auto_number(
                session, organization_id, entity_type.entity_type_id, counter_key
            )
        )

    base = render_identifier(template, values, seq_value=seq_value)
    if not base:
        # Empty render: counter fallback keyed by the (empty) prefix context (spec §3.5).
        counter_key = (SEQ_COUNTER_KEY_PREFIX + scope)[:100]
        base = format_seq(
            _get_next_auto_number(
                session, organization_id, entity_type.entity_type_id, counter_key
            )
        )

    existing = _existing_identifiers_for_base(
        session, organization_id, entity_type.entity_type_id, base
    )
    out = dict(data or {})
    out[IDENTIFIER_FIELD_KEY] = next_suffixed(base, existing)
    return out
```

And the service method:

```python
def get_identifier_template(
    self, organization_id: str, entity_type_id: str
) -> str | None:
    """Active identifier_template for the type, or None (manual mode)."""
    try:
        with self._db_session() as session:
            model = (
                session.query(EntityTypeModel)
                .filter_by(
                    organization_id=organization_id, entity_type_id=entity_type_id
                )
                .first()
            )
            if model is None:
                return None
            return _identifier_template_from_schema(model.schema)
    except Exception as exc:
        logger.debug("get_identifier_template failed: %s", exc)
        return None
```

- [ ] **Step 3: Hook into `create_entity_record`**

In `create_entity_record` (~1121), after the `_link_sources_to_new_entity` block and **before** `session.commit()`, insert:

```python
                type_model = (
                    session.query(EntityTypeModel)
                    .filter_by(
                        organization_id=request.organization_id,
                        entity_type_id=request.entity_type_id,
                    )
                    .first()
                )
                if type_model is not None and _identifier_template_from_schema(
                    type_model.schema
                ):
                    model.data = apply_identifier_template(
                        self,
                        session,
                        organization_id=request.organization_id,
                        entity_type=type_model,
                        entity_id=entity_id,
                        data=dict(model.data or {}),
                    )
                    session.flush()
```

Note: `session.flush()` after reassigning `model.data` — JSONB column, reassignment (not mutation) so change tracking works.

- [ ] **Step 4: Write failing integration tests**

Create `backend/tests/test_identifier_generation.py`. Copy the fixture/header pattern from `backend/tests/test_entity_records.py` (same `client` fixture usage, same org header conventions — read its first ~80 lines and mirror the setup helpers). Tests to write (each creates its own entity type via `POST /entity-types` with `schema_definition` containing an `identifier_template`, plus form schemas via the forms API where field tokens are used):

```python
def test_template_generates_identifier_and_ignores_client_value(client):
    # type with template "{{first_name}}-{{last_name}}", form schema having those text fields
    # POST /entity-records with data first_name=John, last_name=Smith, identifier="HACKED"
    # → response data["identifier"] == "john-smith"
    ...

def test_collision_appends_suffix(client):
    # create two records with same names → "john-smith", "john-smith_2"
    ...

def test_seq_scoped_per_prefix(client):
    # template "{{client_name}}-{{seq}}" with client_name a plain text field here
    # acme → acme-0001; globex → globex-0001; acme again → acme-0002
    ...

def test_blank_fields_skip_segments(client):
    # template "{{first_name}}-{{employee_number}}", employee_number omitted → "john"
    ...

def test_all_blank_falls_back_to_counter(client):
    # template "{{ghost}}" with no such field value → identifier == "0001"
    ...

def test_reference_token_resolves_from_source_link(client):
    # Arrange: client type (manual), filing type with template "{{client_name}}-{{seq}}",
    # relation declaration client→filing with relation_metadata {"name": "client_name"},
    # a client record data {"name": "Acme", "identifier": "acme"}.
    # Act: POST /entity-records for filing with source_entity_ids=[client_id].
    # Assert: identifier == "acme-0001".
    ...

def test_reference_token_without_link_blank_prefix(client):
    # same filing type, no source_entity_ids → identifier == "0001" (blank-prefix counter)
    ...

def test_manual_mode_unchanged(client):
    # type without template still requires identifier and rejects duplicates (existing behavior)
    ...
```

Fill in the `...` with real request payloads following `test_entity_records.py`'s exact call style — these are complete tests, the `...` above is only to keep this plan readable; the executor writes full bodies. Model the relation-declaration setup on `backend/tests/test_entity_relations.py` (it exercises `entity-type-relations` + `source_entity_ids`).

- [ ] **Step 5: Run tests, verify they fail**

Run: `cd backend && python -m pytest tests/test_identifier_generation.py -v`
Expected: FAIL on assertions (identifier equals client-sent/manual values — hook not yet effective) or 400s from manual-mode validation (fixed in Task 3; `test_template_generates_identifier_and_ignores_client_value` will 400 with "Identifier is required" absent a sent identifier — send one, the test asserts it gets overwritten, which passes only after Task 3 removes template-mode manual validation. Keep both tasks on this test file.)

- [ ] **Step 6: Run tests again after implementation, fix until green** (expect a subset green now; the rest go green at end of Task 3 — mark which)

---

### Task 3: Manager wiring — skip manual validation, immutability on update, patch lock

**Files:**
- Modify: `backend/entities/manager.py` (`create_entity_record_for_actor` ~1066, `_validate_unique_identifier` ~1042, `update_entity_record_for_actor` ~1207)
- Modify: `backend/forms/db_models.py` (`patch_entity_data` locked-keys ~565)
- Test: `backend/tests/test_identifier_generation.py` (extend)

**Interfaces:**
- Consumes: `self.db_model_service.get_identifier_template(org, type_id)` (Task 2).
- Produces: template-mode behavior relied on by FE tasks — create accepts payloads without identifier; update silently keeps stored identifier.

- [ ] **Step 1: Extend failing tests**

Add to `backend/tests/test_identifier_generation.py`:

```python
def test_create_without_identifier_allowed_in_template_mode(client):
    # POST /entity-records with NO identifier key in data → 200/201, identifier generated
    ...

def test_update_cannot_change_generated_identifier(client):
    # create templated record → PUT /entity-records/{id} with data {"identifier": "evil", "first_name": "Jon"}
    # → 200, re-fetch: identifier unchanged, first_name updated
    ...

def test_manual_mode_update_still_allows_identifier_edit(client):
    # type without template: PUT changing identifier succeeds (today's behavior)
    ...
```

Run: `cd backend && python -m pytest tests/test_identifier_generation.py -v` → new tests FAIL (400 "Identifier is required" / identifier overwritten).

- [ ] **Step 2: Manager create branch**

In `create_entity_record_for_actor` (~1083), replace the unconditional `self._validate_unique_identifier(...)` call with:

```python
        template = self.db_model_service.get_identifier_template(
            organization_id, request.entity_type_id
        )
        if template is None:
            self._validate_unique_identifier(
                organization_id=organization_id,
                entity_type_id=request.entity_type_id,
                data=request.data,
            )
```

(Template mode needs no pre-validation — generation + unique index own correctness.)

- [ ] **Step 3: Manager update strip**

In `update_entity_record_for_actor`, right after `requested_changes: dict = dict(request.data or {})` (~1222), add:

```python
        if existing := self.db_model_service.get_entity_record_by_id(
            organization_id=organization_id, entity_id=entity_id
        ):
            pass
```

Careful — `existing` is already fetched two lines below in the current code. Do NOT fetch twice: move the template check to just after the existing `existing = self.db_model_service.get_entity_record_by_id(...)` line (~1218) instead:

```python
        if existing is not None and IDENTIFIER_FIELD_KEY in requested_changes:
            if self.db_model_service.get_identifier_template(
                organization_id, existing.entity_type_id
            ):
                requested_changes.pop(IDENTIFIER_FIELD_KEY, None)
```

`IDENTIFIER_FIELD_KEY` import already exists in manager.py (used at ~996).

- [ ] **Step 4: Forms patch lock**

In `backend/forms/db_models.py` (~567), the patch path builds `locked` from `_auto_number_ids_for_type_id`. Extend:

```python
            locked = self._auto_number_ids_for_type_id(
                db, organization_id, entity.entity_type_id
            )
            type_model = (
                db.query(EntityTypeModel)
                .filter_by(
                    organization_id=organization_id,
                    entity_type_id=entity.entity_type_id,
                )
                .first()
            )
            if type_model is not None and _identifier_template_from_schema(type_model.schema):
                locked = set(locked) | {IDENTIFIER_FIELD_KEY}
```

Import at top of forms/db_models.py (extend the existing `from entities.db_models import ...` line): `_identifier_template_from_schema`; and `IDENTIFIER_FIELD_KEY` from `entities.models.interface`.

- [ ] **Step 5: Run full new test file**

Run: `cd backend && python -m pytest tests/test_identifier_generation.py tests/test_entity_records.py -v`
Expected: ALL PASS (including Task 2 leftovers and the pre-existing entity-records suite — no regressions).

---

### Task 4: Public-form create paths

**Files:**
- Modify: `backend/forms/db_models.py` (`save_deferred_fields_to_entity` ~704, `submit_public_form` ~783)
- Test: `backend/tests/test_forms_module.py` (extend, mirror its existing public-form test setup)

**Interfaces:**
- Consumes: `apply_identifier_template` (Task 2) — imported from `entities.db_models`. `service` param: `FormsModelService` holds no `EntitiesModelService`; pass the resolver differently — see Step 2.

- [ ] **Step 1: Failing test**

In `backend/tests/test_forms_module.py`, locate the existing test that drives `submit_public_form` creating a cross-type entity (search for `form_entity_type` / `created_entity_id`), clone it as:

```python
def test_public_form_create_generates_templated_identifier(...):
    # target type has identifier_template "PF-{{seq}}"
    # submit public form for a different-type entity → created entity's data["identifier"] == "PF-0001"
```

Run: `cd backend && python -m pytest tests/test_forms_module.py -k templated_identifier -v` → FAIL (no identifier key).

- [ ] **Step 2: Implement**

`apply_identifier_template` needs `_resolve_inherited_fields_with_session` only when `entity_id` is not None; these paths pass `entity_id=None`, so the `service` argument is unused. Loosen Task 2's signature: make `service` optional —

```python
def apply_identifier_template(
    service: "EntitiesModelService | None",
    session: "Session",
    *, organization_id, entity_type, entity_id, data,
) -> dict:
    ...
    if entity_id is not None and service is not None and parse_tokens(template):
        ...
```

(If Task 2 is already merged, apply this as an edit here.) Then in **both** new-entity branches of forms/db_models.py, wrap the existing `_with_auto_numbers` result:

```python
                    new_data = self._with_auto_numbers(
                        db, organization_id, target_type, dict(fields or {})
                    )
                    new_data = apply_identifier_template(
                        None,
                        db,
                        organization_id=organization_id,
                        entity_type=target_type,
                        entity_id=None,
                        data=new_data,
                    )
```

Extend the existing `from entities.db_models import ...` import with `apply_identifier_template`.

- [ ] **Step 3: Run, verify pass; run whole forms suite**

Run: `cd backend && python -m pytest tests/test_forms_module.py -v`
Expected: PASS, no regressions.

---

### Task 5: Entity-type config validation + rename cascade

**Files:**
- Modify: `backend/entities/manager.py` (`create_entity_type` ~182, `update_entity_type` ~250 area where `schema_definition` is handled, `_cascade_field_renames` ~275)
- Test: `backend/tests/test_entity_types_registry.py` (extend)

**Interfaces:**
- Consumes: `parse_tokens`, `has_seq_token`, `TOKEN_RE` from `common.identifier_template`; `active_schema_fields` from `forms.db_models` (manager already has access to forms data via db services — check how `_cascade_field_renames` reads old fields and mirror the access pattern).
- Produces: 400 `ValidationError` on bad templates; allowed-type set `IDENTIFIER_ALLOWED_FIELD_TYPES`.

- [ ] **Step 1: Failing tests**

Add to `backend/tests/test_entity_types_registry.py`:

```python
def test_identifier_template_unknown_token_rejected(client):
    # PUT /entity-types/{name} schema_definition identifier_template "{{ghost}}" → 400, message lists "ghost"

def test_identifier_template_literal_only_rejected(client):
    # "NOTOKENS-" → 400

def test_identifier_template_seq_only_valid_without_forms(client):
    # "INV-{{seq}}" on a type with no linked forms → 200

def test_identifier_label_length_capped(client):
    # 65-char label → 400

def test_identifier_template_unsupported_field_type_rejected(client):
    # token pointing at a `table`-type field on the type's schema_definition.fields → 400

def test_field_rename_rewrites_template(client):
    # type with fields [{"field": "first_name", ...}] and template "{{first_name}}-{{seq}}"
    # PUT schema_definition renaming field to "given_name" (same position — mirror how
    # _cascade_field_renames detects renames) → template becomes "{{given_name}}-{{seq}}"
```

Run: `cd backend && python -m pytest tests/test_entity_types_registry.py -k identifier -v` → FAIL.

- [ ] **Step 2: Implement validation**

Add to `backend/entities/manager.py`:

```python
IDENTIFIER_ALLOWED_FIELD_TYPES = {
    "text", "textarea", "string", "email", "phone", "url", "select", "enum",
    "integer", "number", "int", "date", "datetime", "auto_number", "reference",
}
IDENTIFIER_LABEL_MAX = 64
IDENTIFIER_TEMPLATE_MAX = 256


def _validate_identifier_config(
    self, organization_id: str, entity_type_name: str, schema_definition: dict | None
) -> None:
    """Spec §7: label/template caps, ≥1 token, tokens resolve to allowed-type fields."""
    if not schema_definition:
        return
    label = schema_definition.get("identifier_label")
    if label is not None and len(str(label).strip()) > IDENTIFIER_LABEL_MAX:
        raise ValidationError(
            f"identifier_label must be at most {IDENTIFIER_LABEL_MAX} characters"
        )
    raw = schema_definition.get("identifier_template")
    template = str(raw).strip() if raw is not None else ""
    if not template:
        return
    if len(template) > IDENTIFIER_TEMPLATE_MAX:
        raise ValidationError(
            f"identifier_template must be at most {IDENTIFIER_TEMPLATE_MAX} characters"
        )
    tokens = parse_tokens(template)
    if not tokens:
        raise ValidationError(
            "identifier_template must contain at least one {{field}} or {{seq}} token"
        )
    field_tokens = [t for t in tokens if t != "seq"]
    if not field_tokens:
        return
    known: dict[str, str] = {}
    for field in (schema_definition.get("fields") or []):
        fid = field.get("field") or field.get("name")
        if fid:
            known[str(fid).lower()] = str(field.get("type", "")).lower()
    for field in self.db_model_service.active_schema_fields_for_type_name(
        organization_id, entity_type_name
    ):
        fid = field.get("field") or field.get("name")
        if fid:
            known.setdefault(str(fid).lower(), str(field.get("type", "")).lower())
    bad = [
        t for t in field_tokens
        if t not in known or known[t] not in IDENTIFIER_ALLOWED_FIELD_TYPES
    ]
    if bad:
        raise ValidationError(
            "identifier_template references unknown or unsupported fields: "
            + ", ".join(sorted(set(bad)))
        )
```

If `active_schema_fields_for_type_name` doesn't exist on the entities db service, add a thin delegate that opens a session and calls `forms.db_models.active_schema_fields(session, organization_id, entity_type_name)` (import inside the method to avoid a module cycle — forms already imports from entities). Call `self._validate_identifier_config(...)` in `create_entity_type_for_actor` and `update_entity_type_for_actor` wherever `schema_definition` is present on the request, before delegating to the db layer.

- [ ] **Step 3: Implement rename cascade**

In `_cascade_field_renames` (~275): it computes old→new field-id pairs. After the existing permissions rewrite, add:

```python
        template = str((schema_definition or {}).get("identifier_template") or "")
        if template and renames:
            for old_id, new_id in renames.items():
                template = re.sub(
                    r"\{\{\s*" + re.escape(old_id) + r"\s*\}\}",
                    "{{" + new_id + "}}",
                    template,
                    flags=re.IGNORECASE,
                )
            schema_definition["identifier_template"] = template
```

Adapt variable names to the method's actual locals (read the method body first; `renames` here means whatever mapping it derives — reuse it, do not recompute).

- [ ] **Step 4: Run, verify pass**

Run: `cd backend && python -m pytest tests/test_entity_types_registry.py -v`
Expected: PASS, no regressions.

---

### Task 6: Uniqueness migration + indexed manual validation + insert retry

**Files:**
- Create: `backend/alembic/versions/2026_07_15_0001_identifier_unique_index.py`
- Modify: `backend/entities/db_models.py` (identifier existence lookup; retry in create), `backend/entities/manager.py` (`_validate_unique_identifier`)
- Test: `backend/tests/test_identifier_generation.py` (extend)

**Interfaces:**
- Produces: `EntitiesModelService.identifier_exists(organization_id, entity_type_id, identifier) -> bool`.

- [ ] **Step 1: Migration**

Create `backend/alembic/versions/2026_07_15_0001_identifier_unique_index.py` (revision ids follow the digits-only convention — parent is `202607140001`):

```python
"""Dedupe entity identifiers and add a partial unique index.

Revision ID: 202607150001
Revises: 202607140001
Create Date: 2026-07-15 00:01:00
"""

from __future__ import annotations

import os

from alembic import op

revision = "202607150001"
down_revision = "202607140001"
branch_labels = None
depends_on = None


def _runtime_schema() -> str:
    return f"{os.environ.get('POSTGRES_APP_SCHEMA', 'public')}_runtime"


def upgrade() -> None:
    schema = _runtime_schema()
    # Dedupe: keep the oldest row per (org, type, identifier); suffix the rest _2, _3, ...
    op.execute(
        f"""
        WITH ranked AS (
            SELECT entity_id,
                   ROW_NUMBER() OVER (
                       PARTITION BY organization_id, entity_type_id, data->>'identifier'
                       ORDER BY created_at, entity_id
                   ) AS rn
            FROM {schema}.entities
            WHERE data->>'identifier' IS NOT NULL AND data->>'identifier' <> ''
        )
        UPDATE {schema}.entities e
        SET data = jsonb_set(
            e.data, '{{identifier}}',
            to_jsonb((e.data->>'identifier') || '_' || ranked.rn::text)
        )
        FROM ranked
        WHERE e.entity_id = ranked.entity_id AND ranked.rn > 1
        """
    )
    op.execute(
        f"""
        CREATE UNIQUE INDEX uq_runtime_entities_org_type_identifier
        ON {schema}.entities (organization_id, entity_type_id, (data->>'identifier'))
        WHERE data->>'identifier' IS NOT NULL AND data->>'identifier' <> ''
        """
    )


def downgrade() -> None:
    op.execute(
        f"DROP INDEX IF EXISTS {_runtime_schema()}.uq_runtime_entities_org_type_identifier"
    )
```

Note the doubled `{{identifier}}` inside the f-string — required to emit the literal jsonb path `{identifier}`.

- [ ] **Step 2: Run migration**

Run: `cd backend && alembic upgrade head`
Expected: applies cleanly. If it fails on dupes/locks in your env, capture output and stop for review — do not force.

- [ ] **Step 3: Indexed manual-mode validation**

Add to `EntitiesModelService`:

```python
def identifier_exists(
    self, organization_id: str, entity_type_id: str, identifier: str
) -> bool:
    """Point lookup on the partial unique index — archived rows included."""
    with self._db_session() as session:
        ident = EntityRecordModel.data.op("->>")(IDENTIFIER_FIELD_KEY)
        return session.query(
            session.query(EntityRecordModel)
            .filter(
                EntityRecordModel.organization_id == organization_id,
                EntityRecordModel.entity_type_id == entity_type_id,
                ident == identifier,
            )
            .exists()
        ).scalar()
```

Rewrite `_validate_unique_identifier` in manager.py — replace the `list_entity_records` loop (everything after the empty-check) with:

```python
        if self.db_model_service.identifier_exists(
            organization_id, entity_type_id, identifier
        ):
            raise ValidationError(
                f"An entity with identifier '{identifier}' already exists"
            )
```

- [ ] **Step 4: Insert retry**

In `create_entity_record` (db layer), the template-mode flush from Task 2 Step 3 can now raise `IntegrityError` on the new index under a race. Wrap that block:

```python
                    try:
                        model.data = apply_identifier_template(...)  # as Task 2
                        session.flush()
                    except IntegrityError:
                        # ponytail: single retry; move to counter-keyed identifiers
                        # if contention ever shows up in logs
                        session.rollback()
                        raise
```

Careful: a plain nested retry inside one SQLAlchemy transaction needs a SAVEPOINT. Use `session.begin_nested()`:

```python
                if type_model is not None and _identifier_template_from_schema(type_model.schema):
                    for attempt in (1, 2):
                        try:
                            with session.begin_nested():
                                model.data = apply_identifier_template(
                                    self, session,
                                    organization_id=request.organization_id,
                                    entity_type=type_model,
                                    entity_id=entity_id,
                                    data=dict(model.data or {}),
                                )
                                session.flush()
                            break
                        except IntegrityError:
                            if attempt == 2:
                                raise
```

(This replaces Task 2 Step 3's plain call — implement it in this final form if executing tasks in order aware of both.)

- [ ] **Step 5: Tests**

Extend `backend/tests/test_identifier_generation.py`:

```python
def test_manual_mode_duplicate_still_rejected_via_index_lookup(client):
    # manual type: create identifier "dup-1" twice → second returns 400
```

Run: `cd backend && python -m pytest tests/test_identifier_generation.py tests/test_entity_records.py tests/test_entities_module.py -v`
Expected: PASS.

---

### Task 7: Frontend types + identifier helpers

**Files:**
- Modify: `frontend/src/core/types/index.ts` (EntityType ~952, EntityTypeCreateRequest ~1008, EntityTypeUpdateRequest ~1020)
- Modify: `frontend/src/shared/utils/entityForm.ts`

**Interfaces:**
- Produces (consumed by Tasks 8–10):
  - type `IdentifierConfig = { identifier_label?: string | null; identifier_template?: string | null }`
  - `EntityType.schema_definition?: EntityTypeSchemaDefinition` where `EntityTypeSchemaDefinition = IdentifierConfig & { fields?: FieldDefinition[] } & Record<string, unknown>`
  - `slugifyIdentifierValue(value: unknown): string`
  - `renderIdentifierPreview(template: string, values: Record<string, unknown>): string` — `{{seq}}` renders as `0001`
  - `templateTokens(template: string): string[]`
  - `hasIdentifierTemplate(schemaDefinition?: IdentifierConfig | null): boolean`
  - `resolveIdentifierLabel(schemaDefinition: IdentifierConfig | null | undefined, entityTypeName?: string | null): string` — precedence: config label → `getIdentifierLabel(entityTypeName)`

- [ ] **Step 1: Types**

In `core/types/index.ts` add near `EntityTypeSchema` (~942):

```ts
export interface IdentifierConfig {
  identifier_label?: string | null;
  identifier_template?: string | null;
}

export type EntityTypeSchemaDefinition = IdentifierConfig & {
  fields?: FieldDefinition[];
} & Record<string, unknown>;
```

Add `schema_definition?: EntityTypeSchemaDefinition;` to `EntityType`, `EntityTypeCreateRequest`, and `EntityTypeUpdateRequest` (the backend wire key — the legacy `schema` members stay untouched).

- [ ] **Step 2: Helpers in entityForm.ts**

Append to `frontend/src/shared/utils/entityForm.ts`:

```ts
import type { IdentifierConfig } from '../../core/types';

const IDENTIFIER_TOKEN_RE = /\{\{\s*([A-Za-z0-9_]+)\s*\}\}/g;

/** FE mirror of backend slugify — preview only, backend is authoritative. */
export function slugifyIdentifierValue(value: unknown): string {
  if (value === null || value === undefined || typeof value === 'object') return '';
  return String(value)
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

export function templateTokens(template: string): string[] {
  return [...(template ?? '').matchAll(IDENTIFIER_TOKEN_RE)].map((m) => m[1].toLowerCase());
}

/** Preview render — `{{seq}}` shows as a sample `0001`. */
export function renderIdentifierPreview(
  template: string,
  values: Record<string, unknown>,
): string {
  const substituted = (template ?? '').replace(IDENTIFIER_TOKEN_RE, (_, raw: string) => {
    const token = raw.toLowerCase();
    if (token === 'seq') return '0001';
    return slugifyIdentifierValue(values[token]);
  });
  return substituted
    .replace(/[-_]{2,}/g, (m) => m[0])
    .replace(/^[-_]+|[-_]+$/g, '')
    .slice(0, 120);
}

export function hasIdentifierTemplate(config?: IdentifierConfig | null): boolean {
  return Boolean(String(config?.identifier_template ?? '').trim());
}

export function resolveIdentifierLabel(
  config: IdentifierConfig | null | undefined,
  entityTypeName?: string | null,
): string {
  const label = String(config?.identifier_label ?? '').trim();
  return label || getIdentifierLabel(entityTypeName);
}
```

- [ ] **Step 3: Build gate**

Run: `cd frontend && npm run build`
Expected: clean.

---

### Task 8: Entity Type editor UI (label, template, chips, preview, badge)

**Files:**
- Modify: `frontend/src/pages/settings/components/entity-types/EntityTypesTab.tsx`

**Interfaces:**
- Consumes: Task 7 helpers; `formSchemas` API (`frontend/src/core/services/api/formSchemas.ts` — exported from `core/services/api/index.ts`); `entityTypesApi.update(name, { description, schema_definition })`.

- [ ] **Step 1: Extend EditorState + save payload**

In `EntityTypesTab.tsx`: `EditorState` gains `identifierLabel: string; identifierTemplate: string;` — seeded in `toEditor` from `entityType.schema_definition?.identifier_label / identifier_template` (empty string fallback) and blank in `blankEditor()`. In `handleSave`, both branches send:

```ts
const schema_definition = {
  ...(editor.original?.schema_definition ?? {}),
  identifier_label: editor.identifierLabel.trim() || undefined,
  identifier_template: editor.identifierTemplate.trim() || undefined,
};
```

added to the create/update payloads (`{ name, description, schema_definition }` / `{ description, schema_definition }`). Preserving `...original.schema_definition` keeps `fields` intact — mandatory, the backend cascade reads it.

- [ ] **Step 2: Editor modal fields**

Inside the editor modal (below the description `Textarea`), add:

```tsx
<Input
  label="Identifier label"
  value={editor.identifierLabel}
  onChange={(e) => setEditor({ ...editor, identifierLabel: e.target.value })}
  placeholder='e.g. "Candidate ID" — leave blank for default'
  maxLength={64}
/>
<Input
  label="Identifier template"
  value={editor.identifierTemplate}
  onChange={(e) => setEditor({ ...editor, identifierTemplate: e.target.value })}
  placeholder="e.g. {{first_name}}-{{last_name}} or INV-{{seq}}"
  maxLength={256}
/>
```

Below the template input, render insert-chips: load linked-form fields once per opened editor via `formSchemas` list filtered to `schema.entity_type === editor.original?.name` (skip for brand-new types — no linked forms yet), plus a fixed `{{seq}}` chip. Chip click appends `` `${sep}{{${fieldId}}}` `` (sep = `-` unless template empty/ends with `-_.`). Allowed chip field types: text, textarea, email, phone, url, select, integer, number, date, datetime, auto_number, reference.

Live preview line under the chips:

```tsx
{editor.identifierTemplate.trim() && (
  <p className="text-sm text-muted-foreground">
    Preview:{' '}
    <code className="rounded bg-muted px-2 py-0.5 font-mono text-xs">
      {renderIdentifierPreview(
        editor.identifierTemplate,
        Object.fromEntries(previewFields.map((f) => [f.id.toLowerCase(), f.label])),
      ) || '—'}
    </code>
  </p>
)}
```

(`previewFields` = the chip source fields; label-as-sample-value gives a readable slug preview. No editable sample inputs — YAGNI, revisit on feedback.)

- [ ] **Step 3: Missing-field warning badge**

In the types table row, when `hasIdentifierTemplate(entityType.schema_definition)` and some non-`seq` token is absent from that type's loaded form fields (compute from the same `formSchemas` list fetched once alongside `fetchTypes`), render next to the name:

```tsx
<span
  className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700"
  title={`Identifier template references missing fields: ${missing.join(', ')}`}
>
  <AlertCircle className="h-3 w-3" /> template
</span>
```

- [ ] **Step 4: Build gate + manual check**

Run: `cd frontend && npm run build` → clean. Then dev-run and verify: open Settings → Entity Types → edit a type → set label + template → preview updates → save → reopen shows persisted values (backend round-trip through `schema_definition`).

---

### Task 9: Create dialogs + record detail behavior

**Files:**
- Modify: `frontend/src/pages/Pipeline/components/AddEntityDialog.tsx` (identifier field ~52, canSubmit ~130, handleSubmit ~171/199)
- Modify: `frontend/src/pages/records/detail/components/CreateEntityModal.tsx` (identifier render ~151)
- Modify: `frontend/src/pages/records/detail/index.tsx` (create-modal validation ~266, update validation ~264 area, identifier edit field)
- Create: `frontend/src/shared/hooks/useIdentifierConfig.ts`

**Interfaces:**
- Produces: `useIdentifierConfig(entityTypeName?: string | null): { config: IdentifierConfig | null; templateMode: boolean; label: string }`

- [ ] **Step 1: Config hook**

```ts
import { useEffect, useState } from 'react';
import { entityTypes as entityTypesApi } from '@/core/services/api';
import type { IdentifierConfig } from '@/core/types';
import { hasIdentifierTemplate, resolveIdentifierLabel } from '@/shared/utils/entityForm';

const cache = new Map<string, IdentifierConfig | null>();

/** Identifier config for an entity type name; null while loading/unknown. */
export function useIdentifierConfig(entityTypeName?: string | null) {
  const [config, setConfig] = useState<IdentifierConfig | null>(
    entityTypeName ? cache.get(entityTypeName) ?? null : null,
  );

  useEffect(() => {
    if (!entityTypeName) return;
    if (cache.has(entityTypeName)) {
      setConfig(cache.get(entityTypeName) ?? null);
      return;
    }
    let cancelled = false;
    entityTypesApi
      .get(entityTypeName)
      .then((t) => {
        const cfg = (t.schema_definition ?? null) as IdentifierConfig | null;
        cache.set(entityTypeName, cfg);
        if (!cancelled) setConfig(cfg);
      })
      .catch(() => {
        if (!cancelled) setConfig(null);
      });
    return () => {
      cancelled = true;
    };
  }, [entityTypeName]);

  return {
    config,
    templateMode: hasIdentifierTemplate(config),
    label: resolveIdentifierLabel(config, entityTypeName),
  };
}
```

(Verify `entityTypesApi.get(name)` exists in `core/services/api/entityTypes.ts`; it does — GET `/entity-types/{name}`. `// ponytail: module-level cache, no invalidation — config changes need a reload; fine for admin-edited settings`.)

- [ ] **Step 2: AddEntityDialog**

- `const { templateMode, label: identifierLabel } = useIdentifierConfig(workflow.entity_type);`
- Identifier field memo (~52): use `identifierLabel` instead of `getIdentifierLabel(...)`; where the identifier field is rendered/included in tab-0 fields, exclude it when `templateMode`.
- `canSubmit` (~130): change the identifier check to `if (!templateMode && !String(formData[IDENTIFIER_FIELD_KEY] ?? '').trim()) return false;`
- `handleSubmit` (~171): wrap the required-identifier early-return in `if (!templateMode …)`; in the create payload (~197-200), spread identifier conditionally:

```ts
        data: {
          ...filterEditablePayload(schemas[0].entity_type, formData),
          ...(!templateMode
            ? { [IDENTIFIER_FIELD_KEY]: String(formData[IDENTIFIER_FIELD_KEY] ?? '').trim() }
            : {}),
        },
```

- [ ] **Step 3: CreateEntityModal + records/detail create**

Same pattern: hook on the modal's entity type name; hide the `IDENTIFIER_FIELD` input (~151) when `templateMode`; in `records/detail/index.tsx` create handler, guard the required check (~266) with `!templateMode` and omit identifier from the payload (~299) as in Step 2. Label: replace `getIdentifierLabel(routeEntityType)` uses in these two files with the hook's `label`.

- [ ] **Step 4: Record detail edit — read-only identifier**

In `records/detail/index.tsx` edit flow (identifier required check ~264 and wherever the identifier input renders in edit mode): when `templateMode`, render the identifier as read-only text (existing read-only display pattern used for reference fields in that file) and skip the required-validation branch. Backend strips writes anyway (Task 3) — this is UX truthfulness.

- [ ] **Step 5: Build gate + manual check**

`cd frontend && npm run build` → clean. Dev-run: type with template → create dialog shows no identifier input, record created with generated ID visible in list/detail; type without template → unchanged manual flow.

---

### Task 10: Form-config breaking-change warnings

**Files:**
- Modify: `frontend/src/pages/settings/components/form-config/hooks/useFormFields.ts` (`requestDeleteField` ~295)
- Modify: `frontend/src/pages/settings/components/form-config/FormConfigTab.tsx` (form unlink/deactivate handler — locate the archive/delete-form action in the tab; search `delete` / `archive` handlers)

**Interfaces:**
- Consumes: `entityTypesApi.list()` (`{ items: EntityType[] }`), `templateTokens`, `hasIdentifierTemplate` (Task 7).

- [ ] **Step 1: Shared check helper**

Add to `frontend/src/pages/settings/components/form-config/hooks/useFormFields.ts` (or a small `identifierTemplateGuards.ts` beside it if the hook file is crowded):

```ts
import { entityTypes as entityTypesApi } from '@/core/services/api';
import { hasIdentifierTemplate, templateTokens } from '@/shared/utils/entityForm';

/** Entity types whose identifier_template references `fieldId` (scoped to one type name when given). */
export async function typesUsingFieldInIdentifierTemplate(
  fieldId: string,
  entityTypeName?: string,
): Promise<string[]> {
  const res = await entityTypesApi.list();
  return (res.items ?? [])
    .filter((t) => (entityTypeName ? t.name === entityTypeName : true))
    .filter((t) => hasIdentifierTemplate(t.schema_definition))
    .filter((t) =>
      templateTokens(String(t.schema_definition?.identifier_template ?? '')).includes(
        fieldId.toLowerCase(),
      ),
    )
    .map((t) => t.name);
}
```

- [ ] **Step 2: Wire into field delete**

In `requestDeleteField` (~295), before executing the delete, resolve the form's entity type name (available in the hook's context/props) and:

```ts
const users = await typesUsingFieldInIdentifierTemplate(field.id, formEntityType);
if (users.length > 0) {
  const ok = window.confirm(
    `Field "${field.label}" is used in the identifier template of: ${users.join(', ')}. ` +
      'New records will skip it until the template is updated. Delete anyway?',
  );
  if (!ok) return;
}
```

(If `requestDeleteField` is currently synchronous, make the handler async — it's a click handler, safe.)

- [ ] **Step 3: Wire into form unlink/deactivate**

Same confirm in `FormConfigTab.tsx` where a whole form is deleted/deactivated: collect all allowed-type field ids of that form, call the helper per template-bearing type of that form's entity type, single confirm listing affected types.

- [ ] **Step 4: Build gate + manual check**

`cd frontend && npm run build` → clean. Dev-run: delete a template-referenced field → confirm dialog appears; cancel keeps field; Entity Types tab shows the amber `template` badge after a real delete.

---

### Task 11: Full verification sweep

**Files:** none new.

- [ ] **Step 1: Backend suite**

Run: `cd backend && python -m pytest tests/ -v` (docker env if host Python < 3.12)
Expected: PASS — zero regressions. Pay attention to `test_entity_records.py`, `test_entities_module.py`, `test_forms_module.py`, `test_entity_types_registry.py`, `test_architecture_constraints.py`.

- [ ] **Step 2: Frontend build**

Run: `cd frontend && npm run build`
Expected: clean tsc + build.

- [ ] **Step 3: End-to-end via API (against dev server)**

```bash
# 1. type with template
curl -s -X PUT localhost:8000/entity-types/<existing_type> -H 'content-type: application/json' \
  -d '{"schema_definition": {"identifier_label": "Filing ID", "identifier_template": "{{client_name}}-{{seq}}"}}'
# 2. create two records → expect acme-0001, acme-0002 in responses
# 3. PUT one record with {"data": {"identifier": "evil"}} → re-GET → identifier unchanged
# 4. PUT type with template "{{ghost}}" → expect 400 listing ghost
```

Use real org auth headers as the dev environment requires (mirror how the app's own requests authenticate).

- [ ] **Step 4: Update spec status**

Edit `design_docs/configurable_entity_identifier_spec_15Jul2026.MD` header: `**Status:** Implemented (STAT-353)` and strike resolved open items (§14: schema_definition exposure confirmed; migration dedupe log checked).

---

## Deviations from spec (deliberate, small)

- Spec §7 "field named `seq` → response includes a warning": response models are fixed shapes; the clash is instead surfaced client-side (the `{{seq}}` chip is always the counter; no backend response change). Backend still saves.
- Spec §4 preview "editable sample values": preview uses field labels as sample values (Task 8) — editable samples deferred until someone asks.

## Self-review checklist (run after writing, done)

- Spec coverage: §2 storage → T5/T8; §3 language → T1; §4 generation+paths → T2/T3/T4; §5 index → T6; §6 immutability → T3/T9; §7 validation/degrade/cascade/warnings → T5/T8/T10; §8 labels → T7/T9; §9/§10 files → T2–T10; §12 matrix → tests across T1/T2/T3/T4/T5/T6.
- No placeholders beyond explicitly-marked executor-fills-body test stubs in T2 Step 4 (bodies specified by behavior + reference files).
- Type consistency: `apply_identifier_template(service|None, session, ...)` consistent T2/T4/T6; helper names consistent T7→T8/T9/T10.
