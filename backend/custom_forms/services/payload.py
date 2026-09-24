"""Validation and normalization for a fetched custom form.

A payload is the JSON an external form API returns: sections of cells plus a
``calculations`` map (cell_id → formula string). This module is the trust
boundary between that external response and what we persist — anything that
passes here is safe for the frontend to render and evaluate.
"""

from __future__ import annotations

import json
from typing import Any, NoReturn

from common.logger import logger
from custom_forms.models.interface import (
    ALLOWED_FORMULA_FUNCTIONS,
    BOOLEAN_CELL_TYPES,
    CALC_KEY,
    CALCULATIONS_KEY,
    CELL_CONFIG_KEYS,
    CELL_TYPES,
    CELLS_KEY,
    CONFIG_KEY,
    CURRENCY_AMOUNT_KEY,
    CURRENCY_CELL_TYPE,
    CURRENCY_CODE_KEY,
    CURRENCY_TYPE_MARKER_KEY,
    DEFAULT_CELL_TYPE,
    EDITABLE_KEY,
    FORMULA_IDENTIFIER,
    ID_KEY,
    LABEL_KEY,
    LIST_CELL_TYPES,
    MAX_CELL_JSON_BYTES,
    MAX_TOTAL_CELLS,
    NUMERIC_CELL_TYPES,
    SECTIONS_KEY,
    SOURCE_KEY,
    SOURCE_PATH,
    TITLE_KEY,
    TYPE_KEY,
    VALUE_KEY,
)
from exceptions import ValidationError


def _reject(message: str) -> NoReturn:
    """Log and refuse. The payload is an external response, so every rejection
    is worth a trace of what was wrong with it."""
    logger.warning("custom form payload rejected: %s", message)
    raise ValidationError(message)


def validate_grid_payload(payload: Any) -> dict[str, Any]:
    """Validate a fetched payload and return the normalized snapshot to store.

    Raises ValidationError on any structural problem so the caller refuses to
    create an instance from a malformed external response.
    """
    if not isinstance(payload, dict):
        _reject("payload must be a JSON object")
    raw_sections = payload.get(SECTIONS_KEY)
    if not isinstance(raw_sections, list) or not raw_sections:
        _reject("payload.sections must be a non-empty list")
    raw_calculations = payload.get(CALCULATIONS_KEY) or {}
    if not isinstance(raw_calculations, dict):
        _reject("payload.calculations must be an object")

    cell_ids: set[str] = set()
    sections = _normalize_sections(raw_sections, cell_ids)
    calculations = _normalize_calculations(raw_calculations, cell_ids)
    _settle_derived_cells(sections, calculations)
    _reject_sources_on_derived(sections)
    return {SECTIONS_KEY: sections, CALCULATIONS_KEY: calculations}


def _normalize_sections(raw_sections: list[Any], cell_ids: set[str]) -> list[dict[str, Any]]:
    """Normalize every section and its cells, enforcing the total cell cap."""
    sections: list[dict[str, Any]] = []
    total_cells = 0
    for index, raw_section in enumerate(raw_sections):
        if not isinstance(raw_section, dict):
            _reject(f"sections[{index}] must be an object")
        raw_cells = raw_section.get(CELLS_KEY)
        if not isinstance(raw_cells, list):
            _reject(f"sections[{index}].cells must be a list")
        cells = [_normalize_cell(raw_cell, index, cell_ids) for raw_cell in raw_cells]
        total_cells += len(cells)
        if total_cells > MAX_TOTAL_CELLS:
            _reject(f"payload exceeds the {MAX_TOTAL_CELLS}-cell limit")
        sections.append(
            {
                ID_KEY: str(raw_section.get(ID_KEY) or f"section_{index}"),
                TITLE_KEY: str(raw_section.get(TITLE_KEY) or ""),
                CELLS_KEY: cells,
            }
        )
    return sections


def _settle_derived_cells(
    sections: list[dict[str, Any]], calculations: dict[str, Any]
) -> None:
    """Mark every derived cell non-editable, whatever the API claimed.

    Two ways to be derived: named in the calculations map, or carrying a `calc`
    CalcNode. Either way the result is a number, so the type must hold one.
    """
    for section in sections:
        for cell in section[CELLS_KEY]:
            derived_by = (
                "calculated"
                if cell[ID_KEY] in calculations
                else "a calc field"
                if cell.get(CONFIG_KEY, {}).get(CALC_KEY) is not None
                else None
            )
            if derived_by is None:
                continue
            if cell[TYPE_KEY] not in NUMERIC_CELL_TYPES:
                _reject(
                    f"cell '{cell[ID_KEY]}' is {derived_by} but its type "
                    f"'{cell[TYPE_KEY]}' cannot hold a number"
                )
            cell[EDITABLE_KEY] = False


def _reject_sources_on_derived(sections: list[dict[str, Any]]) -> None:
    """Refuse a `source` on a derived cell.

    Must run after `_settle_derived_cells`: a cell declared "editable": true
    but named in `calculations` is still derived. Its source would be silently
    ignored at fill time, so it is a configuration error upstream.
    """
    for section in sections:
        for cell in section[CELLS_KEY]:
            if SOURCE_KEY in cell and not cell[EDITABLE_KEY]:
                _reject(f"cell '{cell[ID_KEY]}' is derived, so a source on it is ignored")


def _normalize_cell(raw: Any, section_index: int, seen_ids: set[str]) -> dict[str, Any]:
    """Return one normalized cell, registering its id in ``seen_ids``."""
    if not isinstance(raw, dict):
        _reject(f"sections[{section_index}] contains a non-object cell")
    cell_id = raw.get(ID_KEY)
    if not isinstance(cell_id, str) or not cell_id.strip():
        _reject(f"sections[{section_index}] contains a cell without an id")
    cell_id = cell_id.strip()
    if cell_id in seen_ids:
        _reject(f"duplicate cell id '{cell_id}' — cell ids must be globally unique")
    if not FORMULA_IDENTIFIER.fullmatch(cell_id):
        _reject(
            f"cell id '{cell_id}' is not a valid identifier (letters, digits, underscore)"
        )
    seen_ids.add(cell_id)

    cell_type = str(raw.get(TYPE_KEY) or DEFAULT_CELL_TYPE)
    if cell_type not in CELL_TYPES:
        _reject(f"cell '{cell_id}' has unsupported type '{cell_type}'")

    cell: dict[str, Any] = {
        ID_KEY: cell_id,
        LABEL_KEY: str(raw.get(LABEL_KEY) or cell_id),
        TYPE_KEY: cell_type,
        VALUE_KEY: _normalize_value(cell_id, cell_type, raw.get(VALUE_KEY)),
        EDITABLE_KEY: bool(raw.get(EDITABLE_KEY, True)),
    }
    config = _normalize_config(cell_id, raw.get(CONFIG_KEY))
    if config:
        cell[CONFIG_KEY] = config
    source = raw.get(SOURCE_KEY)
    if source is not None:
        # fullmatch, not match: Python $ also matches before a trailing newline,
        # so .match would accept "receipts.m1\n" that the JS-side grammar rejects.
        if not isinstance(source, str) or not SOURCE_PATH.fullmatch(source):
            _reject(
                f"cell '{cell_id}' source {source!r} is not a valid path "
                "(dot-joined identifiers, optionally indexed)"
            )
        cell[SOURCE_KEY] = source
    return cell


def _normalize_value(cell_id: str, cell_type: str, value: Any) -> Any:
    """Return the cell's value, rejecting anything its type cannot hold.

    bool is checked before the numeric types because it is an int subclass — a
    JSON `true` must not land in a number cell as 1.
    """
    if value is None:
        return None
    if cell_type in BOOLEAN_CELL_TYPES:
        if not isinstance(value, bool):
            _reject(f"cell '{cell_id}' value must be true, false, or null")
        return value
    if cell_type == CURRENCY_CELL_TYPE:
        return _normalize_currency_value(cell_id, value)
    if cell_type in NUMERIC_CELL_TYPES:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            _reject(f"cell '{cell_id}' value must be a number or null")
        return value
    if cell_type in LIST_CELL_TYPES:
        if not isinstance(value, list):
            _reject(f"cell '{cell_id}' value must be a list or null")
        return _within_size_limit(cell_id, VALUE_KEY, value)
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        _reject(f"cell '{cell_id}' value must be a string, number, or null")
    return value


def _normalize_currency_value(cell_id: str, value: Any) -> Any:
    """Return a currency cell's value: a bare number, or the `{amount,
    currency_code}` object the platform's currency field stores and edits.
    """
    if isinstance(value, bool):
        _reject(f"cell '{cell_id}' value must be an amount or null")
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, dict):
        amount = value.get(CURRENCY_AMOUNT_KEY)
        if amount is not None and (
            isinstance(amount, bool) or not isinstance(amount, (int, float))
        ):
            _reject(f"cell '{cell_id}' currency amount must be a number or null")
        code = value.get(CURRENCY_CODE_KEY)
        if code is not None and not isinstance(code, str):
            _reject(f"cell '{cell_id}' currency_code must be a string")
        normalized: dict[str, Any] = {CURRENCY_TYPE_MARKER_KEY: CURRENCY_CELL_TYPE, CURRENCY_AMOUNT_KEY: amount}
        if code is not None:
            normalized[CURRENCY_CODE_KEY] = code
        return normalized
    _reject(f"cell '{cell_id}' value must be an amount or null")


def _normalize_config(cell_id: str, raw: Any) -> dict[str, Any]:
    """Return the cell's whitelisted rendering options (select choices, table
    columns, currency code, …). Unknown keys are dropped rather than rejected:
    a report API adding a field the renderer does not know is not an error."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        _reject(f"cell '{cell_id}' config must be an object")
    config = {key: value for key, value in raw.items() if key in CELL_CONFIG_KEYS}
    return _within_size_limit(cell_id, CONFIG_KEY, config) if config else {}


def _within_size_limit(cell_id: str, part: str, value: Any) -> Any:
    """Return `value` if it serializes within the per-cell ceiling.

    Also the JSON-safety check: a value that cannot be serialized cannot be
    stored in the snapshot's JSONB column or rendered by the frontend.
    """
    try:
        encoded = json.dumps(value)
    except (TypeError, ValueError) as exc:
        message = f"cell '{cell_id}' {part} is not JSON-serializable"
        logger.warning("custom form payload rejected: %s", message)
        raise ValidationError(message) from exc
    if len(encoded.encode()) > MAX_CELL_JSON_BYTES:
        _reject(
            f"cell '{cell_id}' {part} exceeds the {MAX_CELL_JSON_BYTES}-byte limit"
        )
    return value


def _normalize_calculations(raw: dict[str, Any], cell_ids: set[str]) -> dict[str, str]:
    """Return the validated cell_id → formula map."""
    calculations: dict[str, str] = {}
    for key, formula in raw.items():
        if key not in cell_ids:
            _reject(f"calculation target '{key}' is not a known cell id")
        if not isinstance(formula, str) or not formula.strip():
            _reject(f"calculation for '{key}' must be a non-empty string")
        for identifier in FORMULA_IDENTIFIER.findall(formula):
            if identifier not in cell_ids and identifier not in ALLOWED_FORMULA_FUNCTIONS:
                _reject(
                    f"calculation for '{key}' references unknown cell '{identifier}'"
                )
        calculations[key] = formula.strip()
    return calculations
