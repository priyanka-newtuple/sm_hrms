"""Compatibility helpers for legacy contract handling."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import Response


def attach_deprecated_fields_header(response: Response, field_names: list[str] | None) -> None:
    """Attach legacy field usage header when deprecated aliases are provided."""

    if not field_names:
        return
    unique = [name for name in dict.fromkeys(field_names) if str(name).strip()]
    if unique:
        response.headers["X-Deprecated-Fields"] = ",".join(unique)
