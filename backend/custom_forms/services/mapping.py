"""Read a results body against a custom form's schema into plain field values.

A custom form arrives in two calls: the connector on its method fetches the
schema (cells carrying `source`), and a results connector fetches the data body
those paths point into. This module joins them.

Nothing here raises: the outbound call has already succeeded by the time it
runs, and failing now would mark the action failed and retry a call that may
not be idempotent. An unresolved path is returned to the caller instead.
"""

from __future__ import annotations

import re
from typing import Any

from custom_forms.models.interface import (
    BOOLEAN_CELL_TYPES,
    CELLS_KEY,
    COLUMN_READONLY_KEY,
    CONFIG_KEY,
    CURRENCY_AMOUNT_KEY,
    CURRENCY_CELL_TYPE,
    DEFAULT_CELL_TYPE,
    DEFAULT_COLUMN_TYPE,
    EDITABLE_KEY,
    ID_KEY,
    LIST_CELL_TYPES,
    NUMERIC_CELL_TYPES,
    ROW_IDENTITY_KEYS,
    ROW_LINE_KEY,
    ROW_READONLY_CELLS_KEY,
    SECTIONS_KEY,
    SOURCE_KEY,
    TABLE_CELL_TYPE,
    TABLE_COLUMNS_KEY,
    TABLE_CONFIG_KEY,
    TABLE_ROWS_KEY,
    TYPE_KEY,
    VALUE_KEY,
    VALUE_KEY_SEPARATOR,
)

_SEGMENT = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)((?:\[\d+\])*)$")
_INDEX = re.compile(r"\[(\d+)\]")

_TEXT_TYPES = (str, int, float)
_NUMBER_TYPES = (int, float)


def value_key(cell_id: str, row_id: str | None = None, column_id: str | None = None) -> str:
    """The `custom_form_data` key one answer is stored under."""
    parts = [part for part in (cell_id, row_id, column_id) if part]
    return VALUE_KEY_SEPARATOR.join(parts)


def read_path(data: Any, path: str) -> Any | None:
    """Return the value at a dotted/indexed path, or None if it does not resolve.

    None covers a missing key, an out-of-range index, a non-object mid-path and
    a malformed segment alike: the caller cannot act on the distinction.
    """
    current = data
    for segment in path.split("."):
        match = _SEGMENT.match(segment)
        if match is None:
            return None
        key, indexes = match.group(1), match.group(2)
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
        for index in _INDEX.findall(indexes):
            position = int(index)
            if not isinstance(current, list) or position >= len(current):
                return None
            current = current[position]
    return current


def answer_keys(schema: dict[str, Any]) -> set[str]:
    """Every `custom_form_data` key one form's cells occupy."""
    keys: set[str] = set()
    for section in schema.get(SECTIONS_KEY) or []:
        if not isinstance(section, dict):
            continue
        for cell in section.get(CELLS_KEY) or []:
            if not isinstance(cell, dict):
                continue
            cell_id = str(cell.get(ID_KEY) or "")
            if not cell_id:
                continue
            table_config = cell.get(TABLE_CONFIG_KEY)
            if str(cell.get(TYPE_KEY) or "") == TABLE_CELL_TYPE and isinstance(
                table_config, dict
            ):
                for row in table_config.get(TABLE_ROWS_KEY) or []:
                    if not isinstance(row, dict):
                        continue
                    row_id = row.get(ID_KEY) or row.get(ROW_LINE_KEY)
                    if row_id is None:
                        continue
                    for column in _writable_columns(table_config, row):
                        keys.add(value_key(cell_id, str(row_id), str(column[ID_KEY])))
                continue
            keys.add(value_key(cell_id))
    return keys


def values_from_sources(
    schema: dict[str, Any], fetched: Any, existing: dict[str, Any] | None = None
) -> tuple[dict[str, Any], list[str]]:
    """Resolve one form's sourced cells into `{answer_key: value}`.

    Returns (values, unresolved_sources). A key already present in `existing`
    is left out, so a figure someone entered outranks a later API answer.
    """
    have = existing or {}
    values: dict[str, Any] = {}
    unresolved: list[str] = []

    for section in schema.get(SECTIONS_KEY) or []:
        if not isinstance(section, dict):
            continue
        for cell in section.get(CELLS_KEY) or []:
            if not isinstance(cell, dict):
                continue
            _read_cell(cell, fetched, have, values, unresolved)

    return values, unresolved


def _read_cell(
    cell: dict[str, Any],
    fetched: Any,
    have: dict[str, Any],
    values: dict[str, Any],
    unresolved: list[str],
) -> None:
    """Add one cell's answers to `values`, or note its source as unresolved."""
    source = cell.get(SOURCE_KEY)
    cell_id = str(cell.get(ID_KEY) or "")
    if not isinstance(source, str) or not cell_id or not cell.get(EDITABLE_KEY, True):
        return

    raw = read_path(fetched, source)
    if raw is None:
        unresolved.append(f"{cell_id}:{source}")
        return

    table_config = cell.get(TABLE_CONFIG_KEY)
    cell_type = str(cell.get(TYPE_KEY) or "")
    if cell_type == TABLE_CELL_TYPE and isinstance(table_config, dict):
        if not _read_table(cell_id, table_config, raw, have, values):
            unresolved.append(f"{cell_id}:{source}")
        return

    key = value_key(cell_id)
    if have.get(key) is not None:
        return
    coerced = _coerce(raw, cell_type or DEFAULT_CELL_TYPE)
    if coerced is None:
        unresolved.append(f"{cell_id}:{source}")
        return
    values[key] = coerced


def _rows_by_identity(fetched_rows: list[Any]) -> dict[str, dict[str, Any]]:
    """Index a fetched grid by whichever key each row identifies itself with."""
    by_key: dict[str, dict[str, Any]] = {}
    for row in fetched_rows:
        if not isinstance(row, dict):
            continue
        for candidate in ROW_IDENTITY_KEYS:
            identity = row.get(candidate)
            if identity is not None:
                by_key.setdefault(str(identity), row)
                break
    return by_key


def _writable_columns(
    table_config: dict[str, Any], row: dict[str, Any]
) -> list[dict[str, Any]]:
    """The columns this row accepts a value in.

    A grid states which cells are display-only per row, not on the column, so
    both have to be checked or a row's own labels look writable.
    """
    locked = {str(name) for name in row.get(ROW_READONLY_CELLS_KEY) or []}
    return [
        column
        for column in table_config.get(TABLE_COLUMNS_KEY) or []
        if isinstance(column, dict)
        and column.get(ID_KEY)
        and not column.get(COLUMN_READONLY_KEY)
        and str(column[ID_KEY]) not in locked
    ]


def _read_row(
    cell_id: str,
    table_config: dict[str, Any],
    row: dict[str, Any],
    match: dict[str, Any],
    have: dict[str, Any],
    values: dict[str, Any],
) -> int:
    """Write one row's answers, returning how many landed."""
    row_id = str(row.get(ID_KEY) or row.get(ROW_LINE_KEY))
    added = 0
    for column in _writable_columns(table_config, row):
        column_id = str(column[ID_KEY])
        key = value_key(cell_id, row_id, column_id)
        if have.get(key) is not None:
            continue
        coerced = _coerce(
            match.get(column_id), str(column.get(TYPE_KEY) or DEFAULT_COLUMN_TYPE)
        )
        if coerced is None:
            continue
        values[key] = coerced
        added += 1
    return added


def _read_table(
    cell_id: str,
    table_config: dict[str, Any],
    fetched_rows: Any,
    have: dict[str, Any],
    values: dict[str, Any],
) -> int:
    """Add a grid's answers, walking the schema's own rows.

    Never the fetched list, so a body belonging to another report cannot add
    rows or relabel the grid.
    """
    if not isinstance(fetched_rows, list):
        return 0
    by_key = _rows_by_identity(fetched_rows)
    added = 0
    for row in table_config.get(TABLE_ROWS_KEY) or []:
        if not isinstance(row, dict):
            continue
        row_id = row.get(ID_KEY) or row.get(ROW_LINE_KEY)
        if row_id is None:
            continue
        match = by_key.get(str(row_id))
        if match is not None:
            added += _read_row(cell_id, table_config, row, match, have, values)
    return added


def _coerce(value: Any, cell_type: str) -> Any | None:
    """Return the value in the cell's type, or None when it does not fit.

    bool is handled per type rather than rejected up front: it is the only
    thing a boolean cell accepts, and an int subclass a number cell must not
    silently take as 1.
    """
    if value is None:
        return None
    if cell_type in BOOLEAN_CELL_TYPES:
        return value if isinstance(value, bool) else None
    if isinstance(value, bool):
        return None
    if cell_type in NUMERIC_CELL_TYPES:
        if cell_type == CURRENCY_CELL_TYPE and isinstance(value, dict):
            amount = value.get(CURRENCY_AMOUNT_KEY)
            return value if isinstance(amount, _NUMBER_TYPES) else None
        return value if isinstance(value, _NUMBER_TYPES) else None
    if cell_type in LIST_CELL_TYPES:
        return value if isinstance(value, list) else None
    return str(value) if isinstance(value, _TEXT_TYPES) else None


def schema_without_values(form: dict[str, Any]) -> dict[str, Any]:
    """Strip a fetched form down to its schema.

    Answers belong in `custom_form_data`, so values are dropped and
    `table_config` is lifted out of `config` to keep the stored shape one level
    flatter than the wire shape.
    """
    sections: list[Any] = []
    for section in form.get(SECTIONS_KEY) or []:
        if not isinstance(section, dict):
            continue
        cells: list[Any] = []
        for cell in section.get(CELLS_KEY) or []:
            if not isinstance(cell, dict):
                continue
            cleaned = {
                key: value
                for key, value in cell.items()
                if key not in (VALUE_KEY, CONFIG_KEY, TABLE_CONFIG_KEY)
            }
            table_config = cell.get(TABLE_CONFIG_KEY) or (cell.get(CONFIG_KEY) or {}).get(
                TABLE_CONFIG_KEY
            )
            if isinstance(table_config, dict):
                cleaned[TABLE_CONFIG_KEY] = _table_config_without_values(table_config)
            cells.append(cleaned)
        sections.append({**section, CELLS_KEY: cells})
    return {**form, SECTIONS_KEY: sections}


def _table_config_without_values(table_config: dict[str, Any]) -> dict[str, Any]:
    """A grid's definition with any per-row answer dropped."""
    rows = [
        {key: value for key, value in row.items() if key != VALUE_KEY}
        for row in table_config.get(TABLE_ROWS_KEY) or []
        if isinstance(row, dict)
    ]
    return {**table_config, TABLE_ROWS_KEY: rows}
