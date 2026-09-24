"""Sheet adapter for CSV/XLSX/XLS content."""

from __future__ import annotations

import json
from io import BytesIO

import pandas as pd
from pandas.api import types as pandas_types

from fileprocessor.models.interface import TabularColumn, TabularRow, TabularSheet


class SheetParserAdapter:
    """Adapter for spreadsheet-like files."""

    def supports(self, content_type: str, filename: str) -> bool:
        lower = filename.lower()
        return lower.endswith((".csv", ".xlsx", ".xls")) or content_type in {
            "text/csv",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.ms-excel",
        }

    def adapt(self, file_bytes: bytes, filename: str, content_type: str) -> dict[str, object]:
        # Let parse errors propagate (do NOT fall back to utf-8 decode); extract_content
        # reports parse_ok=False instead of returning garbage.
        if filename.lower().endswith(".csv") or content_type == "text/csv":
            df = pd.read_csv(BytesIO(file_bytes))
        else:
            df = pd.read_excel(BytesIO(file_bytes))
        table_rows = df.head(200).fillna("").to_dict(orient="records")
        text = df.to_csv(index=False)

        return {
            "adapter": "sheet",
            "filename": filename,
            "content_type": content_type,
            "text": text,
            "images": [],
            "tables": table_rows,
        }

    def extract_sheets(
        self, file_bytes: bytes, filename: str, content_type: str
    ) -> list[TabularSheet]:
        """Return every spreadsheet row in a JSON-safe, sheet-aware structure.

        ``adapt`` intentionally keeps its small table preview for general document
        tools. Callers that need deterministic row processing use this complete,
        structured path instead of round-tripping rows through rendered CSV text.
        """
        if filename.lower().endswith(".csv") or content_type == "text/csv":
            frames = {"CSV": pd.read_csv(BytesIO(file_bytes))}
        else:
            frames = pd.read_excel(BytesIO(file_bytes), sheet_name=None)

        sheets: list[TabularSheet] = []
        for sheet_name, frame in frames.items():
            # pandas/numpy scalar values (timestamps, NaN, integers) are not all
            # JSON serializable. pandas' JSON encoder normalizes them consistently
            # before the rows are persisted in the intake-job context.
            raw_rows = json.loads(frame.to_json(orient="records", date_format="iso"))
            columns = [str(column) for column in frame.columns]
            sheets.append(
                TabularSheet(
                    sheet_name=str(sheet_name),
                    row_count=len(raw_rows),
                    columns=[
                        TabularColumn(
                            name=column,
                            inferred_type=self._inferred_type(frame.iloc[:, index]),
                            sample_values=self._sample_values(raw_rows, column),
                        )
                        for index, column in enumerate(columns)
                    ],
                    rows=[
                        TabularRow(source_row_number=index, values=row)
                        for index, row in enumerate(raw_rows, start=1)
                    ],
                )
            )
        return sheets

    @staticmethod
    def _sample_values(rows: list[dict[str, object]], column: str) -> list[str]:
        values: list[str] = []
        for row in rows:
            value = row.get(column)
            normalized = str(value).strip()[:160] if value not in (None, "") else ""
            if normalized and normalized not in values:
                values.append(normalized)
            if len(values) == 3:
                break
        return values

    @staticmethod
    def _inferred_type(series: pd.Series) -> str:
        if pandas_types.is_bool_dtype(series.dtype):
            return "boolean"
        if pandas_types.is_integer_dtype(series.dtype):
            return "integer"
        if pandas_types.is_numeric_dtype(series.dtype):
            return "number"
        if pandas_types.is_datetime64_any_dtype(series.dtype):
            return "datetime"
        return "string"
