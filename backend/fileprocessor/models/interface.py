"""Neutral contracts produced by file content processors."""

from __future__ import annotations

from typing import Any

from common.data_model import BaseModel


class TabularColumn(BaseModel):
    """Profile of one source column, independent of any destination schema."""

    name: str
    inferred_type: str
    sample_values: list[str]


class TabularRow(BaseModel):
    """One parsed row with a stable, one-based position in its source sheet."""

    source_row_number: int
    values: dict[str, Any]


class TabularSheet(BaseModel):
    """Canonical representation of one CSV or workbook sheet."""

    sheet_name: str
    row_count: int
    columns: list[TabularColumn]
    rows: list[TabularRow]
