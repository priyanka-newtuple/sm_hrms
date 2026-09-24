"""Shared helpers for dashboard global entity filtering."""

from __future__ import annotations

from typing import Any

GLOBAL_ENTITY_IDS_FILTER = "__global_entity_ids"


def global_entity_ids(filters: dict[str, Any] | None) -> list[str] | None:
    """Extract the resolved global entity id set from dashboard filters."""
    raw = (filters or {}).get(GLOBAL_ENTITY_IDS_FILTER)
    if not isinstance(raw, list):
        return None
    return [str(item) for item in raw if str(item)]
