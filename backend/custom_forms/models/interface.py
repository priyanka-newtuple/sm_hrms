"""Shape rules and key names for a custom form's payload.

Read by the validator, the schema/value mapping and the manager, so a typo in
one of them cannot fail silently as "not present".
"""

from __future__ import annotations

import re
from typing import Any, Protocol

# The frontend renders every cell with no virtualization, so this caps what an
# external API can hand the UI.
MAX_TOTAL_CELLS = 2000

DEFAULT_CONNECT_TIMEOUT_SECONDS = 5.0
DEFAULT_READ_TIMEOUT_SECONDS = 15.0

# Cell types mirror the frontend `FieldType`, grouped by the value shape each
# stores — which is what validation and coercion key off.
CURRENCY_CELL_TYPE = "currency"
NUMERIC_CELL_TYPES = frozenset({"number", "integer", CURRENCY_CELL_TYPE})
BOOLEAN_CELL_TYPES = frozenset({"boolean"})
LIST_CELL_TYPES = frozenset({"multi_select", "table"})
TEXT_CELL_TYPES = frozenset(
    {
        "text",
        "textarea",
        "email",
        "phone",
        "url",
        "date",
        "datetime",
        "select",
        "picklist_multi",
        "auto_number",
        "reference",
    }
)
# `section` is absent on purpose: sections carry their own titles.
CELL_TYPES = NUMERIC_CELL_TYPES | BOOLEAN_CELL_TYPES | LIST_CELL_TYPES | TEXT_CELL_TYPES

CALC_KEY = "calc"

# Whitelisted rather than passed wholesale: the payload is an external
# response, and only these keys mean anything to the renderer.
CELL_CONFIG_KEYS = frozenset(
    {
        CALC_KEY,
        "placeholder",
        "picklist_id",
        "picklist_id_2",
        "enum_values",
        "enum_labels",
        "enum_values_2",
        "enum_labels_2",
        "min_value",
        "max_value",
        "max_length",
        "rows",
        "col_span",
        "table_config",
        "currency_config",
        "source_entity",
        "source_field",
        "auto_number_config",
    }
)

# ── Payload keys ──────────────────────────────────────────────────────────
SECTIONS_KEY = "sections"
CELLS_KEY = "cells"
CALCULATIONS_KEY = "calculations"
ID_KEY = "id"
TITLE_KEY = "title"
LABEL_KEY = "label"
TYPE_KEY = "type"
VALUE_KEY = "value"
SOURCE_KEY = "source"
EDITABLE_KEY = "editable"
CONFIG_KEY = "config"
TABLE_CONFIG_KEY = "table_config"
TABLE_ROWS_KEY = "rows"
TABLE_COLUMNS_KEY = "columns"
COLUMN_READONLY_KEY = "readonly"
ROW_READONLY_CELLS_KEY = "readonly_cells"
ROW_LINE_KEY = "line"

TABLE_CELL_TYPE = "table"
DEFAULT_CELL_TYPE = "number"
DEFAULT_COLUMN_TYPE = "text"
CURRENCY_AMOUNT_KEY = "amount"
CURRENCY_CODE_KEY = "currency_code"
CURRENCY_TYPE_MARKER_KEY = "__type"

# Not "." — a dot makes an answer key look like a path to `$entity.<field>`
# and to `mapping.read_path`, both of which split on it.
VALUE_KEY_SEPARATOR = "__"
ROW_IDENTITY_KEYS = (ROW_LINE_KEY, ID_KEY, "_row_id")

# Shared with the executor and the background-jobs writer, so a rename cannot
# leave the two halves disagreeing silently.
CUSTOM_FORM_WRITEBACK_TARGET = "custom_form"
WRITEBACK_TARGET_META_KEY = "writeback_target"
CUSTOM_FORM_RESPONSE_META_KEY = "custom_form_response"

MODULE_NAME = "custom_forms"

# Rows and multi-select lists make a cell's value unbounded, so both value and
# config carry a size ceiling.
MAX_CELL_JSON_BYTES = 20_000

# Identifiers reference cell ids; only these functions exist.
ALLOWED_FORMULA_FUNCTIONS = frozenset({"min", "max", "round", "sum", "average"})
FORMULA_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

# A cell's `source`: dot-joined segments, each optionally indexed —
# `deductions[1].amount`. Kept in sync with mapping.read_path.
_SOURCE_SEGMENT = r"[A-Za-z_][A-Za-z0-9_]*(?:\[\d+\])*"
SOURCE_PATH = re.compile(rf"^{_SOURCE_SEGMENT}(?:\.{_SOURCE_SEGMENT})*$")

CURLY_PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")
ENTITY_PLACEHOLDER = re.compile(r"\$entity\.([a-zA-Z_][a-zA-Z0-9_]*)")


class WorkflowDbProtocol(Protocol):
    """The workflow persistence this module reads."""

    def list_method_pins(
        self, *, organization_id: str, workflow_state_machine_id: str
    ) -> list[tuple[str, str, str]]: ...


class MethodLibraryDbProtocol(Protocol):
    """The method library persistence this module reads."""

    def list_version_fields(
        self, *, organization_id: str, method_version_id: str
    ) -> list[Any]: ...

    def get_version(self, *, organization_id: str, version_id: str) -> Any: ...


class ConnectorsProtocol(Protocol):
    """The one connector call this module makes."""

    def run_for_entity(
        self,
        *,
        organization_id: str,
        connector_id: str,
        entity_values: dict[str, str] | None = None,
    ) -> Any: ...


class EntitiesDbProtocol(Protocol):
    """The record persistence this module reads and writes."""

    def get_entity_record_by_id(
        self, *, organization_id: str, entity_id: str, include_archived: bool = False
    ) -> Any: ...

    def merge_custom_form_data(
        self, *, organization_id: str, entity_id: str, values: dict
    ) -> None: ...
