# Auto-Number Sequential Counter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace nanoid-based auto_number generation with a sequential zero-padded counter (e.g. length=4 → "0001", "0002") with optional prefix/suffix affix support.

**Architecture:** A new `auto_number_counters` table in the `_runtime` schema stores one row per `(organization_id, entity_type_id, field_key)`. Each create atomically increments its counter using PostgreSQL's `INSERT ... ON CONFLICT DO UPDATE ... RETURNING` — no collision detection needed. The `length` config now means zero-pad digit width instead of nanoid character count.

**Tech Stack:** Python 3.12, SQLAlchemy 1.4, PostgreSQL (JSONB), Alembic, React 19 + TypeScript + Vite

## Global Constraints

- Never commit or push to git unless user explicitly asks
- All backend code targets Python 3.12
- SQLAlchemy 1.4 ORM patterns (not 2.0 style)
- `POSTGRES_APP_SCHEMA` env var controls schema prefix; default is `public`
- Runtime schema = `{POSTGRES_APP_SCHEMA}_runtime` (e.g. `public_runtime`)
- Tests run against `ats_test` database; activate venv with `source .venv/bin/activate` before backend commands
- New Alembic migration revision format: `YYYYMMDDNNNN` (e.g. `202606240001`); file name `YYYY_MM_DD_NNNN_description.py`
- Latest migration revision (chain from this): `202606200001`

---

## File Map

| File | Change |
|------|--------|
| `backend/common/auto_number.py` | Rewrite: remove nanoid, add `_format_value`, update `apply_auto_number_defaults` signature |
| `backend/entities/db_models.py` | Add `AutoNumberCounterModel` ORM model + `_get_next_auto_number` function; update callers; remove `_auto_number_exists_fn` |
| `backend/alembic/versions/2026_06_24_0001_add_auto_number_counters.py` | New migration: create `auto_number_counters` table |
| `backend/forms/db_models.py` | Update `_with_auto_numbers`; remove `auto_number_value_exists` |
| `backend/workflow/models/interface.py` | Length constants update (via import — just verify after Task 2) |
| `frontend/src/core/services/api/formSchemas.ts` | Update default length from 12 → 6 |
| `frontend/src/pages/settings/components/form-config/components/FieldRow.tsx` | Update slider range + label |
| `frontend/src/pages/settings/components/form-config/components/EditFieldModal.tsx` | Update slider range + label |

---

### Task 1: Counter ORM Model + Alembic Migration

**Files:**
- Modify: `backend/entities/db_models.py` — add `AutoNumberCounterModel` class and `_get_next_auto_number` function
- Create: `backend/alembic/versions/2026_06_24_0001_add_auto_number_counters.py`

**Interfaces:**
- Produces: `_get_next_auto_number(session: Session, organization_id: str, entity_type_id: str, field_key: str) -> int` — returns the next sequential counter value (1-indexed, atomic)

- [ ] **Step 1: Add `AutoNumberCounterModel` to `entities/db_models.py`**

Add this class after `EntityEventAuditModel` (around line 303, before `TransitionAttemptModel`). It needs `_runtime_schema` which is already defined at the top of the file:

```python
class AutoNumberCounterModel(Base):
    """Per-(org, entity_type, field) sequential counter for auto_number fields."""

    __tablename__ = "auto_number_counters"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "entity_type_id",
            "field_key",
            name="uq_auto_number_counters_org_type_field",
        ),
        Index("ix_auto_number_counters_org_type", "organization_id", "entity_type_id"),
        {"schema": _runtime_schema()},
    )

    counter_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), nullable=False)
    entity_type_id = Column(String(36), nullable=False)
    field_key = Column(String(128), nullable=False)
    current_value = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
```

- [ ] **Step 2: Add `_get_next_auto_number` module-level function to `entities/db_models.py`**

Add this function right after the `AutoNumberCounterModel` class definition:

```python
def _get_next_auto_number(
    session: "Session",
    organization_id: str,
    entity_type_id: str,
    field_key: str,
) -> int:
    """Atomically increment and return the next sequential value for a field counter.

    Uses PostgreSQL INSERT ... ON CONFLICT DO UPDATE ... RETURNING to guarantee
    each call returns a unique monotonically increasing integer with no gaps
    under concurrent load.
    """
    import os as _os
    _schema = f"{_os.environ.get('POSTGRES_APP_SCHEMA', 'public')}_runtime"
    sql = sa.text(
        f"INSERT INTO {_schema}.auto_number_counters "
        "(counter_id, organization_id, entity_type_id, field_key, current_value) "
        "VALUES (:counter_id, :organization_id, :entity_type_id, :field_key, 1) "
        "ON CONFLICT (organization_id, entity_type_id, field_key) "
        "DO UPDATE SET current_value = auto_number_counters.current_value + 1 "
        "RETURNING current_value"
    )
    result = session.execute(sql, {
        "counter_id": str(uuid.uuid4()),
        "organization_id": organization_id,
        "entity_type_id": entity_type_id,
        "field_key": field_key,
    })
    session.commit()
    return result.scalar()
```

- [ ] **Step 3: Write the failing test for `_get_next_auto_number`**

In `backend/tests/test_auto_number_counter.py` (create this file):

```python
"""Tests for sequential auto_number counter."""
import uuid
from tests.common import DatabaseTestCase
from entities.db_models import _get_next_auto_number, AutoNumberCounterModel


class TestGetNextAutoNumber(DatabaseTestCase):
    def test_first_call_returns_one(self):
        org = str(uuid.uuid4())
        type_id = str(uuid.uuid4())
        val = _get_next_auto_number(self.session, org, type_id, "ref_number")
        self.assertEqual(val, 1)

    def test_sequential_calls_increment(self):
        org = str(uuid.uuid4())
        type_id = str(uuid.uuid4())
        v1 = _get_next_auto_number(self.session, org, type_id, "ref_number")
        v2 = _get_next_auto_number(self.session, org, type_id, "ref_number")
        v3 = _get_next_auto_number(self.session, org, type_id, "ref_number")
        self.assertEqual([v1, v2, v3], [1, 2, 3])

    def test_different_fields_independent(self):
        org = str(uuid.uuid4())
        type_id = str(uuid.uuid4())
        a1 = _get_next_auto_number(self.session, org, type_id, "field_a")
        b1 = _get_next_auto_number(self.session, org, type_id, "field_b")
        a2 = _get_next_auto_number(self.session, org, type_id, "field_a")
        self.assertEqual(a1, 1)
        self.assertEqual(b1, 1)
        self.assertEqual(a2, 2)

    def test_different_entity_types_independent(self):
        org = str(uuid.uuid4())
        type_a = str(uuid.uuid4())
        type_b = str(uuid.uuid4())
        va = _get_next_auto_number(self.session, org, type_a, "ref")
        vb = _get_next_auto_number(self.session, org, type_b, "ref")
        self.assertEqual(va, 1)
        self.assertEqual(vb, 1)
```

- [ ] **Step 4: Run test to verify it fails (table doesn't exist yet)**

```bash
cd backend && source .venv/bin/activate && python -m pytest tests/test_auto_number_counter.py -v
```

Expected: FAIL with relation "auto_number_counters" does not exist

- [ ] **Step 5: Create the Alembic migration**

Create `backend/alembic/versions/2026_06_24_0001_add_auto_number_counters.py`:

```python
"""Add auto_number_counters table for sequential field ID generation.

Revision ID: 202606240001
Revises: 202606200001
Create Date: 2026-06-24
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op

revision = "202606240001"
down_revision = "202606200001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = f"{os.environ.get('POSTGRES_APP_SCHEMA', 'public')}_runtime"
    op.create_table(
        "auto_number_counters",
        sa.Column("counter_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("entity_type_id", sa.String(36), nullable=False),
        sa.Column("field_key", sa.String(128), nullable=False),
        sa.Column("current_value", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("counter_id", name="pk_auto_number_counters"),
        sa.UniqueConstraint(
            "organization_id",
            "entity_type_id",
            "field_key",
            name="uq_auto_number_counters_org_type_field",
        ),
        schema=schema,
    )
    op.create_index(
        "ix_auto_number_counters_org_type",
        "auto_number_counters",
        ["organization_id", "entity_type_id"],
        schema=schema,
    )


def downgrade() -> None:
    schema = f"{os.environ.get('POSTGRES_APP_SCHEMA', 'public')}_runtime"
    op.drop_index(
        "ix_auto_number_counters_org_type",
        table_name="auto_number_counters",
        schema=schema,
    )
    op.drop_table("auto_number_counters", schema=schema)
```

- [ ] **Step 6: Run the migration**

```bash
cd backend && source .venv/bin/activate && alembic upgrade head
```

Expected: Migration applies with no errors

- [ ] **Step 7: Run the test — verify it passes**

```bash
cd backend && source .venv/bin/activate && python -m pytest tests/test_auto_number_counter.py -v
```

Expected: 4 tests PASS

---

### Task 2: Rewrite `backend/common/auto_number.py`

**Files:**
- Modify: `backend/common/auto_number.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (pure logic module)
- Produces:
  - `AUTO_NUMBER_DEFAULT_LENGTH = 6`
  - `AUTO_NUMBER_MIN_LENGTH = 1`
  - `AUTO_NUMBER_MAX_LENGTH = 10`
  - `AUTO_NUMBER_MAX_AFFIX_LENGTH = 64` (unchanged)
  - `_format_value(counter: int, config: dict[str, Any]) -> str`
  - `apply_auto_number_defaults(schema_fields, data, get_next_counter: Callable[[str], int], overwrite=False) -> None`
  - `auto_number_field_ids(schema_fields) -> set[str]` (unchanged)

- [ ] **Step 1: Write failing tests for the new logic**

Create `backend/tests/test_auto_number_format.py`:

```python
"""Tests for sequential auto_number formatting."""
from common.auto_number import _format_value, apply_auto_number_defaults


class TestFormatValue:
    def test_no_affix_zero_pads(self):
        assert _format_value(1, {"length": 4}) == "0001"

    def test_no_affix_increments(self):
        assert _format_value(42, {"length": 4}) == "0042"

    def test_prefix(self):
        assert _format_value(1, {"length": 4, "affix_mode": "prefix", "affix": "JOB"}) == "JOB-0001"

    def test_suffix(self):
        assert _format_value(1, {"length": 4, "affix_mode": "suffix", "affix": "JOB"}) == "0001-JOB"

    def test_counter_exceeds_width_no_truncation(self):
        # Overflow — more digits than width — still works, just un-padded
        assert _format_value(10000, {"length": 4}) == "10000"

    def test_default_length(self):
        result = _format_value(1, {})
        assert result == "000001"  # length defaults to 6

    def test_empty_affix_mode_none_no_separator(self):
        assert _format_value(5, {"length": 3, "affix_mode": "none", "affix": ""}) == "005"


class TestApplyAutoNumberDefaults:
    def _make_counter(self, start=1):
        """Returns a callable that increments a counter starting at `start`."""
        state = [start - 1]
        def get_next(field_key: str) -> int:
            state[0] += 1
            return state[0]
        return get_next

    def test_fills_auto_number_field(self):
        fields = [{"field": "ref", "type": "auto_number", "auto_number_config": {"length": 4}}]
        data = {}
        apply_auto_number_defaults(fields, data, self._make_counter())
        assert data["ref"] == "0001"

    def test_does_not_overwrite_existing_by_default(self):
        fields = [{"field": "ref", "type": "auto_number", "auto_number_config": {"length": 4}}]
        data = {"ref": "existing"}
        apply_auto_number_defaults(fields, data, self._make_counter())
        assert data["ref"] == "existing"

    def test_overwrites_when_forced(self):
        fields = [{"field": "ref", "type": "auto_number", "auto_number_config": {"length": 4}}]
        data = {"ref": "existing"}
        apply_auto_number_defaults(fields, data, self._make_counter(), overwrite=True)
        assert data["ref"] == "0001"

    def test_skips_non_auto_number_fields(self):
        fields = [{"field": "name", "type": "text"}]
        data = {}
        apply_auto_number_defaults(fields, data, self._make_counter())
        assert "name" not in data
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd backend && source .venv/bin/activate && python -m pytest tests/test_auto_number_format.py -v
```

Expected: FAIL — `_format_value` does not exist yet

- [ ] **Step 3: Rewrite `backend/common/auto_number.py`**

Replace the entire file:

```python
"""Auto-number field value generation (sequential, zero-padded)."""

from __future__ import annotations

from typing import Any, Callable

AUTO_NUMBER_DEFAULT_LENGTH = 6
AUTO_NUMBER_MIN_LENGTH = 1
AUTO_NUMBER_MAX_LENGTH = 10
AUTO_NUMBER_MAX_AFFIX_LENGTH = 64


def _format_value(counter: int, config: dict[str, Any] | None) -> str:
    """Format a sequential counter as a zero-padded string with optional affix."""
    cfg = config or {}
    try:
        length = int(cfg.get("length", AUTO_NUMBER_DEFAULT_LENGTH))
    except (TypeError, ValueError):
        length = AUTO_NUMBER_DEFAULT_LENGTH
    length = max(AUTO_NUMBER_MIN_LENGTH, min(AUTO_NUMBER_MAX_LENGTH, length))
    core = str(counter).zfill(length)
    mode = str(cfg.get("affix_mode", "none")).strip().lower()
    affix = str(cfg.get("affix", "")).strip()
    if affix and mode == "prefix":
        return f"{affix}-{core}"
    if affix and mode == "suffix":
        return f"{core}-{affix}"
    return core


def apply_auto_number_defaults(
    schema_fields: list[dict[str, Any]] | None,
    data: dict[str, Any],
    get_next_counter: Callable[[str], int],
    overwrite: bool = False,
) -> None:
    """Fill auto_number values in ``data`` (in place).

    ``get_next_counter(field_key)`` returns the next sequential integer for
    that field — the caller owns the DB interaction (atomic increment).

    By default, existing (truthy) values are left untouched. Pass
    ``overwrite=True`` on create/backfill paths to always generate a fresh
    value, discarding any client-supplied value — auto_number identifiers are
    backend-generated and must never be trusted from request payloads.
    """
    for field in schema_fields or []:
        if str(field.get("type", "")).strip().lower() != "auto_number":
            continue
        field_id = field.get("field") or field.get("name")
        if not field_id:
            continue
        if not overwrite and data.get(field_id):
            continue
        cfg = field.get("auto_number_config") or {}
        counter = get_next_counter(str(field_id))
        data[field_id] = _format_value(counter, cfg)


def auto_number_field_ids(schema_fields: list[dict[str, Any]] | None) -> set[str]:
    """Return the field ids of every auto_number field in ``schema_fields``."""
    ids: set[str] = set()
    for field in schema_fields or []:
        if str(field.get("type", "")).strip().lower() != "auto_number":
            continue
        field_id = field.get("field") or field.get("name")
        if field_id:
            ids.add(str(field_id))
    return ids
```

- [ ] **Step 4: Run the format tests — verify they pass**

```bash
cd backend && source .venv/bin/activate && python -m pytest tests/test_auto_number_format.py -v
```

Expected: All tests PASS

---

### Task 3: Update callers in `backend/entities/db_models.py`

**Files:**
- Modify: `backend/entities/db_models.py`

**Interfaces:**
- Consumes: `_get_next_auto_number` (from Task 1), `apply_auto_number_defaults` (new signature from Task 2)
- Produces: no interface change for external callers — `create_entity_record` and `update_entity_record` still work the same

- [ ] **Step 1: Remove `_auto_number_exists_fn` and update `_apply_auto_number_defaults`**

Find `_auto_number_exists_fn` at line ~784. Delete the entire method (lines 784–793).

Find `_apply_auto_number_defaults` at line ~795. Replace its body:

```python
def _apply_auto_number_defaults(
    self,
    session,
    *,
    organization_id: str,
    entity_type_id: str,
    data: dict,
) -> dict:
    """Fill auto_number fields defined on the entity type's active schema(s)."""
    schema_fields = self._auto_number_schema_fields(
        session, organization_id, entity_type_id
    )
    if not any(
        str(f.get("type", "")).lower() == "auto_number" for f in schema_fields
    ):
        return data

    out = dict(data or {})
    apply_auto_number_defaults(
        schema_fields,
        out,
        lambda field_key: _get_next_auto_number(session, organization_id, entity_type_id, field_key),
        overwrite=True,
    )
    return out
```

- [ ] **Step 2: Update `_lock_auto_number_on_update`**

Find `_lock_auto_number_on_update` at line ~821. The backfill call to `apply_auto_number_defaults` at the end of the method still needs a `get_next_counter` instead of `exists`. Replace just the last call in that method:

Old:
```python
        apply_auto_number_defaults(
            schema_fields,
            out,
            self._auto_number_exists_fn(session, organization_id, entity_type_id),
        )
```

New:
```python
        apply_auto_number_defaults(
            schema_fields,
            out,
            lambda field_key: _get_next_auto_number(session, organization_id, entity_type_id, field_key),
        )
```

- [ ] **Step 3: Verify the import at the top of `entities/db_models.py` still works**

The existing import line is:
```python
from common.auto_number import apply_auto_number_defaults, auto_number_field_ids
```

This still works — both names are exported. No change needed.

- [ ] **Step 4: Run the entity-level tests**

```bash
cd backend && source .venv/bin/activate && python -m pytest tests/test_auto_number_counter.py tests/test_auto_number_format.py -v
```

Expected: All PASS

---

### Task 4: Update `backend/forms/db_models.py`

**Files:**
- Modify: `backend/forms/db_models.py`

**Interfaces:**
- Consumes: `_get_next_auto_number` from `entities.db_models` (Task 1), `apply_auto_number_defaults` (new signature from Task 2)

- [ ] **Step 1: Add import of `_get_next_auto_number` to `forms/db_models.py`**

Find the existing import of `auto_number_field_ids` in `forms/db_models.py` (line 29):
```python
from common.auto_number import apply_auto_number_defaults, auto_number_field_ids
```

Add an import after the existing entity imports (around line 29). Find where `EntityRecordModel` is imported from `entities.db_models` and add to that block:

```python
from entities.db_models import _get_next_auto_number
```

- [ ] **Step 2: Delete `auto_number_value_exists` function**

Find `auto_number_value_exists` at line ~146 and delete the entire function (lines 146–169). It is no longer called anywhere.

- [ ] **Step 3: Update `_with_auto_numbers`**

Find `_with_auto_numbers` at line ~615. Replace its body:

```python
def _with_auto_numbers(
    self, db: Session, organization_id: str, target_type: Any, data: dict
) -> dict:
    """Fill auto_number fields defined on the target type's active schema(s)."""
    schema_fields = active_schema_fields(db, organization_id, target_type.name)
    if not any(str(f.get("type", "")).lower() == "auto_number" for f in schema_fields):
        return data

    out = dict(data or {})
    apply_auto_number_defaults(
        schema_fields,
        out,
        lambda field_key: _get_next_auto_number(
            db, organization_id, target_type.entity_type_id, field_key
        ),
        overwrite=True,
    )
    return out
```

- [ ] **Step 4: Run all auto_number tests**

```bash
cd backend && source .venv/bin/activate && python -m pytest tests/test_auto_number_counter.py tests/test_auto_number_format.py -v
```

Expected: All PASS

- [ ] **Step 5: Run the full test suite to check nothing broke**

```bash
cd backend && source .venv/bin/activate && python -m pytest tests/ -v --tb=short 2>&1 | tail -30
```

Expected: same pass/fail ratio as before this change; no new failures

---

### Task 5: Update Schema Validation in `backend/workflow/models/interface.py`

**Files:**
- Modify: `backend/workflow/models/interface.py`

The constants `AUTO_NUMBER_MIN_LENGTH`, `AUTO_NUMBER_MAX_LENGTH`, `AUTO_NUMBER_DEFAULT_LENGTH` are imported from `common.auto_number` (line 12–15). Task 2 already updated those constants to MIN=1, MAX=10, DEFAULT=6. The validation at lines 331–361 uses those imported names, so it automatically picks up the new values.

The only thing to verify and fix is the error message string at line 357–359, which still reads correctly since it uses the variable names. No code change needed unless you find a hardcoded range.

- [ ] **Step 1: Verify the import and error message**

Read `backend/workflow/models/interface.py` lines 331–362 and confirm:
- Line 356: `if not AUTO_NUMBER_MIN_LENGTH <= length <= AUTO_NUMBER_MAX_LENGTH:` — uses variables, not literals ✓
- Line 358: error message uses `{AUTO_NUMBER_MIN_LENGTH}..{AUTO_NUMBER_MAX_LENGTH}` — will show `1..10` ✓

If any line contains hardcoded `4` or `21` as the old length bounds, replace with the variable names.

- [ ] **Step 2: Run a quick smoke test on schema validation**

```bash
cd backend && source .venv/bin/activate && python -c "
from workflow.models.interface import EntityField, EntityFieldType
# Should pass — length=4 valid under new range
f = EntityField(field='ref', label='Ref', type='auto_number', auto_number_config={'length': 4})
print('length=4 ok:', f.auto_number_config)

# Should pass — length=1 now valid (was invalid before)
f2 = EntityField(field='ref', label='Ref', type='auto_number', auto_number_config={'length': 1})
print('length=1 ok:', f2.auto_number_config)

# Should fail — length=11 exceeds new max
try:
    EntityField(field='ref', label='Ref', type='auto_number', auto_number_config={'length': 11})
    print('ERROR: should have raised')
except ValueError as e:
    print('length=11 correctly rejected:', e)
"
```

Expected output:
```
length=4 ok: {'affix_mode': 'none', 'affix': '', 'length': 4}
length=1 ok: {'affix_mode': 'none', 'affix': '', 'length': 1}
length=11 correctly rejected: entity field 'ref' auto_number_config length must be 1..10
```

---

### Task 6: Frontend Config UI Updates

**Files:**
- Modify: `frontend/src/core/services/api/formSchemas.ts` — default length 12 → 6
- Modify: `frontend/src/pages/settings/components/form-config/components/FieldRow.tsx` — slider range + label
- Modify: `frontend/src/pages/settings/components/form-config/components/EditFieldModal.tsx` — slider range + label

**Interfaces:**
- No type changes — `auto_number_config` shape `{affix_mode, affix, length}` is unchanged
- The `length` field now means digit-pad width; valid range 1–10; default 6

- [ ] **Step 1: Update default length in `formSchemas.ts`**

Find the auto_number default config in `frontend/src/core/services/api/formSchemas.ts`. The current default is `length: 12`. Change it to `length: 6`.

Search for: `length: 12` within the auto_number config block and change to `length: 6`.

- [ ] **Step 2: Update `FieldRow.tsx` slider**

In `frontend/src/pages/settings/components/form-config/components/FieldRow.tsx`, find the length slider for auto_number config. It currently has range 4–21. Update:
- `min` attribute: `4` → `1`
- `max` attribute: `21` → `10`
- Label text: change "Length" (or similar) to `"Digit width"`
- Add a helper text or placeholder showing e.g. `"e.g. 4 → 0001"` if space allows

- [ ] **Step 3: Update `EditFieldModal.tsx` slider**

Same changes as Step 2, applied to `frontend/src/pages/settings/components/form-config/components/EditFieldModal.tsx`.

- [ ] **Step 4: TypeScript build check**

```bash
cd frontend && npm run build 2>&1 | tail -20
```

Expected: Build succeeds with no TypeScript errors.

---

## Self-Review Checklist

- [x] **Spec coverage:** Sequential counter → Task 1+3+4. Zero-pad format → Task 2. Prefix/suffix preserved → Task 2. Length means digit width → Tasks 2+5+6. Frontend label → Task 6. Migration → Task 1.
- [x] **No placeholders:** All steps have actual code.
- [x] **Type consistency:** `get_next_counter: Callable[[str], int]` used in Task 2 and called with `lambda field_key: _get_next_auto_number(...)` in Tasks 3+4. `_get_next_auto_number` signature: `(session, org_id: str, entity_type_id: str, field_key: str) -> int`.
- [x] **`auto_number_value_exists`** removed from `forms/db_models.py` in Task 4; no remaining callers (both were `_with_auto_numbers` and `_auto_number_exists_fn`, both replaced).
- [x] **`nanoid` dependency** no longer imported after Task 2 rewrite. If nothing else uses it, `nanoid` can be removed from `requirements.txt` (optional cleanup, not blocking).
