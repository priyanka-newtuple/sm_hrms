"""Auto-number field value generation (sequential, zero-padded to 4 digits)."""

from __future__ import annotations

from typing import Any, Callable

AUTO_NUMBER_MAX_AFFIX_LENGTH = 64

_PAD_WIDTH = 4


def _format_value(counter: int, config: dict[str, Any] | None) -> str:
    """Format a sequential counter as a zero-padded string with optional affix.

    Pad width is fixed at 4 digits. Counter overflows naturally (9999 → 10000).
    """
    cfg = config or {}
    core = str(counter).zfill(_PAD_WIDTH)
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
    ``overwrite=True`` on create paths to always generate a fresh value,
    discarding any client-supplied value — auto_number identifiers are
    backend-generated and must never be trusted from request payloads.
    """
    seen: set[str] = set()
    for field in schema_fields or []:
        if str(field.get("type", "")).strip().lower() != "auto_number":
            continue
        field_id = field.get("field") or field.get("name")
        if not field_id:
            continue
        field_key = str(field_id)
        if field_key in seen:
            continue
        seen.add(field_key)
        if not overwrite and data.get(field_id):
            continue
        cfg = field.get("auto_number_config") or {}
        counter = get_next_counter(field_key)
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
