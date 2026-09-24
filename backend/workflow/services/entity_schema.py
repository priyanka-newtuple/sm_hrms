"""Entity-schema rules for workflow definitions.

Owns the rules that decide whether a definition's embedded entity schema is coherent: field and
default validity, calculated-field and table-calculation dependencies, and table/grid cell rules.

Its only I/O is the active-form lookup, which it performs through the forms manager supplied by
`workflow/manager.py`. Everything else is decided from arguments alone, and the service keeps no
state between calls: no roles, no audit, no persistence, and nothing remembered about a previous
request. The manager retains ownership of orchestration.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import ValidationError as PydanticValidationError

from calc import spec
from common.logger import logger
from exceptions import ValidationError
from workflow.models.interface import (
    FormFieldType,
    TableColumnType,
    TableRowMode,
    EntityField,
    EntityFieldType,
    EntitySchema,
    StateMachineDefinition,
    ValidationIssue,
    ValidationIssueCode,
    _matches_entity_field_type,
    matches_workflow_value,
)

if TYPE_CHECKING:
    from forms.manager import FormsServiceManager
    from forms.models.interface import EntityTypeSchemaContract


class EntitySchemaService:
    """Validate a definition's entity schema, embedded and against the live form."""

    def __init__(self, forms_service_manager: FormsServiceManager) -> None:
        """Take the forms manager from the caller.

        Stage 3.5 §9: a workflow service must not hold or construct another workflow service,
        and must not reach into another module's db_models. The forms manager is supplied by
        `workflow/manager.py`, which owns the wiring, and owns its own session.
        """
        self.forms_service_manager = forms_service_manager

    def resolve_active_schemas(self, organization_id: str, entity_type: str) -> list[EntityTypeSchemaContract]:
        """Read the entity type's currently active form schemas.

        Callers that run two schema checks over the same entity type in one operation should
        call this once and hand the result to both, via their `active_schemas` argument. That
        keeps it to a single read without the service holding onto the answer: this service is
        built once at startup and shared across requests, so anything remembered here would
        outlive the operation and go stale the moment a form is edited.
        """
        return list(
            self.forms_service_manager.get_active_entity_schemas(organization_id, entity_type)
        )

    def _column_calc_col_refs(self, node: object) -> set[str]:
        """Collect the column ids one cell-calculation expression depends on."""
        refs: set[str] = set()
        if isinstance(node, dict):
            if node.get("t") == "col":
                refs.add(str(node.get("col")))
            elif node.get("t") == "binary":
                refs |= self._column_calc_col_refs(node.get("left"))
                refs |= self._column_calc_col_refs(node.get("right"))
        return refs

    def _validate_schema_fields(self, definition: StateMachineDefinition) -> list[ValidationIssue]:
        """Check entity schema field declarations (e.g. enum defaults must be valid members)."""
        issues: list[ValidationIssue] = []
        for field in definition.entity_schema.fields:
            if (
                field.type == EntityFieldType.ENUM
                and field.default is not None
                and field.default not in field.enum_values
            ):
                issues.append(
                    ValidationIssue(
                        code=ValidationIssueCode.INVALID_ENUM_DEFAULT,
                        message=f"Entity field '{field.field}' has default value '{field.default}' which is not in its enum_values.",
                    )
                )
        issues.extend(self._validate_calc_fields(definition))
        return issues

    def _validate_calc_fields(self, definition: StateMachineDefinition) -> list[ValidationIssue]:
        """Check every calculated field, column and cell in the definition.

        Issue order is part of the contract: for each field in schema order, its own calc
        issues, then its column calcs, then its fixed-row cell calcs, and finally the
        whole-schema field cycle check.
        """
        fields = definition.entity_schema.fields
        field_names = {f.field for f in fields}
        table_columns = self._table_column_ids(fields)

        issues: list[ValidationIssue] = []
        calc_by_field: dict[str, dict] = {}
        for field in fields:
            if field.calc is not None:
                calc_by_field[field.field] = field.calc
                issues.extend(self._field_calc_issues(field, field_names, table_columns))
            issues.extend(self._column_calc_issues(field, table_columns))
            issues.extend(self._cell_calc_issues(field, field_names, table_columns))

        try:
            spec.topo_order(calc_by_field)
        except spec.CalcCycleError as exc:
            issues.append(ValidationIssue(
                code=ValidationIssueCode.CALC_CYCLE,
                message=str(exc),
            ))
        return issues

    @staticmethod
    def _table_column_ids(fields: list[EntityField]) -> dict[str, set[str]]:
        """Map each table field to the set of column ids it declares."""
        table_columns: dict[str, set[str]] = {}
        for field in fields:
            if isinstance(field.table_config, dict):
                cols = field.table_config.get("columns") or []
                table_columns[field.field] = {
                    str(c.get("id")) for c in cols if isinstance(c, dict) and c.get("id")
                }
        return table_columns

    @staticmethod
    def _field_calc_issues(
        field: EntityField,
        field_names: set[str],
        table_columns: dict[str, set[str]],
    ) -> list[ValidationIssue]:
        """Check one field's own calculation. Column references are not allowed here."""
        return [
            ValidationIssue(
                code=ValidationIssueCode.CALC_INVALID_REF,
                message=f"Entity field '{field.field}': {msg}",
            )
            for msg in spec.validate_calc_node(
                field.calc, field_names=field_names, table_columns=table_columns, allow_col=False
            )
        ]

    def _column_calc_issues(
        self, field: EntityField, table_columns: dict[str, set[str]]
    ) -> list[ValidationIssue]:
        """Check the per-row column calculations on one table field.

        A column calc may only reach sibling columns of the same table, and the computed
        columns must not form a cycle (a = b, b = a).
        """
        if not isinstance(field.table_config, dict):
            return []
        cols = field.table_config.get("columns") or []
        sibling_cols = table_columns.get(field.field, set())

        issues: list[ValidationIssue] = []
        for c in cols:
            if not isinstance(c, dict) or c.get("calc") is None:
                continue
            for msg in spec.validate_calc_node(
                c["calc"], field_names=set(), table_columns={}, allow_col=True
            ):
                issues.append(ValidationIssue(
                    code=ValidationIssueCode.CALC_INVALID_REF,
                    message=f"Column '{c.get('id')}' on '{field.field}': {msg}",
                ))
            for ref_col in self._column_calc_col_refs(c["calc"]):
                if ref_col not in sibling_cols:
                    issues.append(ValidationIssue(
                        code=ValidationIssueCode.CALC_INVALID_REF,
                        message=f"Column '{c.get('id')}' references unknown sibling column '{ref_col}'",
                    ))

        calc_by_col = {
            str(c.get("id")): c["calc"]
            for c in cols
            if isinstance(c, dict) and c.get("calc") is not None and c.get("id")
        }
        try:
            spec.column_topo_order(calc_by_col)
        except spec.CalcCycleError as exc:
            issues.append(ValidationIssue(
                code=ValidationIssueCode.CALC_CYCLE,
                message=f"Table '{field.field}': computed columns form a cycle ({exc})",
            ))
        return issues

    @staticmethod
    def _addressable_cells(
        rows: list[object], column_ids: set[str]
    ) -> set[tuple[str, str]]:
        """Every (row id, column id) pair a cell calculation is allowed to reference."""
        return {
            (str(r.get("id")), col_id)
            for r in rows
            if isinstance(r, dict)
            for col_id in column_ids
        }

    @staticmethod
    def _cell_calc_issues(
        field: EntityField,
        field_names: set[str],
        table_columns: dict[str, set[str]],
    ) -> list[ValidationIssue]:
        """Check per-cell calculations, which only fixed-row tables can declare.

        A dynamic table has no stable row ids, so there is nothing for a cell calc to address.
        """
        table_config = field.table_config if isinstance(field.table_config, dict) else None
        if not table_config:
            return []
        if (table_config.get("row_mode") or TableRowMode.DYNAMIC) != TableRowMode.FIXED:
            return []

        rows = table_config.get("rows") or []
        cell_coords = EntitySchemaService._addressable_cells(
            rows, table_columns.get(field.field, set())
        )

        issues: list[ValidationIssue] = []
        calc_by_cell: dict[tuple[str, str], dict] = {}
        for r in rows:
            if not isinstance(r, dict):
                continue
            cell_cfg = r.get("cell_config")
            if not isinstance(cell_cfg, dict):
                continue
            rid = str(r.get("id"))
            for col_id, cfg in cell_cfg.items():
                if not isinstance(cfg, dict) or cfg.get("calc") is None:
                    continue
                calc_by_cell[(rid, str(col_id))] = cfg["calc"]
                for msg in spec.validate_calc_node(
                    cfg["calc"], field_names=field_names, table_columns=table_columns,
                    allow_col=False, allow_cell=True, allow_agg=False, cell_coords=cell_coords,
                ):
                    issues.append(ValidationIssue(
                        code=ValidationIssueCode.CALC_INVALID_REF,
                        message=f"Cell '{rid}.{col_id}' on '{field.field}': {msg}",
                    ))
        try:
            spec.cell_topo_order(calc_by_cell)
        except spec.CalcCycleError as exc:
            issues.append(ValidationIssue(
                code=ValidationIssueCode.CALC_CYCLE,
                message=f"Table '{field.field}': {exc}",
            ))
        return issues

    @staticmethod
    def _normalize_form_field_type(field_type: str) -> str:
        """Map a form field type to the workflow field type it is compared against.

        Two separate vocabularies, so both sides name their own enum: `FormFieldType` is what a
        form field is saved as, `EntityFieldType` is what a workflow field stores. A form type
        the translation does not cover is returned unchanged.
        """
        normalized = field_type.strip().lower()
        if normalized in {FormFieldType.TEXT, FormFieldType.TEXTAREA, FormFieldType.SELECT}:
            return EntityFieldType.STRING.value
        if normalized == FormFieldType.PHONE:
            return EntityFieldType.PHONE.value
        if normalized == FormFieldType.URL:
            return EntityFieldType.URL.value
        if normalized in {FormFieldType.DATE, FormFieldType.DATETIME}:
            return EntityFieldType.DATETIME.value
        if normalized == FormFieldType.EMAIL:
            return EntityFieldType.EMAIL.value
        if normalized in {FormFieldType.NUMBER, FormFieldType.INTEGER}:
            # INTEGER, whose value is "int", is what `EntityField` stores for both of these.
            # Returning "integer" made the drift comparison never match.
            return EntityFieldType.INTEGER.value
        if normalized == FormFieldType.BOOLEAN:
            return EntityFieldType.BOOLEAN.value
        if normalized == FormFieldType.MULTI_SELECT:
            return EntityFieldType.MULTI_SELECT.value
        if normalized == FormFieldType.JSON_ARRAY:
            return EntityFieldType.JSON.value
        return normalized

    def _validate_table_value(
        self,
        field_name: str,
        value: object,
        table_config: object | None,
    ) -> None:
        """Validate a table/grid payload carried in a JSON entity field.

        Raises on the first problem found, in a fixed order: the config itself, then the row
        shapes, then the row count, then the individual cells. Callers surface the message, so
        the order decides which complaint a user sees when a table is wrong in several ways.
        """
        if table_config is None:
            return
        if not isinstance(table_config, dict):
            raise ValidationError(f"entity field '{field_name}' has invalid table_config")
        if not isinstance(value, list):
            raise ValidationError(f"entity field '{field_name}' expects table rows")

        validated_columns = self._validated_table_columns(field_name, table_config)
        for row_index, row in enumerate(value, start=1):
            if not isinstance(row, dict):
                raise ValidationError(
                    f"entity field '{field_name}' row {row_index} must be an object"
                )

        row_mode = str(table_config.get("row_mode") or TableRowMode.DYNAMIC).strip().lower()
        self._validate_table_row_count(
            field_name, value, validated_columns, row_mode, table_config
        )
        self._validate_table_cells(field_name, value, validated_columns, row_mode)

    @staticmethod
    def _validated_table_columns(field_name: str, table_config: dict) -> list[dict]:
        """Return the declared columns, rejecting a config that cannot describe a table."""
        columns = table_config.get("columns") or []
        if not isinstance(columns, list) or not columns:
            raise ValidationError(f"entity field '{field_name}' table_config requires columns")

        validated_columns: list[dict] = []
        for column in columns:
            if not isinstance(column, dict):
                raise ValidationError(
                    f"entity field '{field_name}' table column must be an object"
                )
            if not str(column.get("id") or "").strip():
                raise ValidationError(f"entity field '{field_name}' table column id is required")
            validated_columns.append(column)
        return validated_columns

    def _validate_table_row_count(
        self,
        field_name: str,
        value: list,
        validated_columns: list[dict],
        row_mode: str,
        table_config: dict,
    ) -> None:
        """Enforce min_rows/max_rows.

        A fixed-row table counts every row, because its rows are part of the definition. A
        dynamic table counts only rows the user actually put something in, so trailing blank
        rows left by the editor do not satisfy a minimum or breach a maximum.
        """
        counted_rows = (
            len(value)
            if row_mode == TableRowMode.FIXED
            else sum(
                1
                for row in value
                if isinstance(row, dict)
                and self._is_meaningful_table_row(row, validated_columns)
            )
        )
        min_rows = table_config.get("min_rows")
        max_rows = table_config.get("max_rows")
        if isinstance(min_rows, int) and counted_rows < min_rows:
            raise ValidationError(
                f"entity field '{field_name}' requires at least {min_rows} table rows"
            )
        if isinstance(max_rows, int) and max_rows >= 0 and counted_rows > max_rows:
            raise ValidationError(
                f"entity field '{field_name}' allows at most {max_rows} table rows"
            )

    def _validate_table_cells(
        self,
        field_name: str,
        value: list,
        validated_columns: list[dict],
        row_mode: str,
    ) -> None:
        """Check each cell against its column's required flag and declared type.

        Empty rows of a dynamic table are skipped entirely — the user has not filled them in,
        so their required columns are not yet a violation.
        """
        for row_index, row in enumerate(value, start=1):
            if row_mode != TableRowMode.FIXED and not self._is_meaningful_table_row(
                row, validated_columns
            ):
                continue
            for column in validated_columns:
                column_id = str(column.get("id") or "").strip()
                column_label = str(column.get("label") or column_id or "column")
                cell = row.get(column_id)
                if column.get("required") and self._is_empty_table_cell(cell):
                    raise ValidationError(
                        f"entity field '{field_name}' row {row_index} column '{column_label}' is required"
                    )
                if not self._matches_table_cell_type(
                    str(column.get("type") or TableColumnType.TEXT.value), cell
                ):
                    raise ValidationError(
                        f"entity field '{field_name}' row {row_index} column '{column_label}' has invalid type"
                    )

    @staticmethod
    def _is_empty_table_cell(value: object) -> bool:
        if value is None:
            return True
        if isinstance(value, str):
            return value.strip() == ""
        if isinstance(value, list):
            return len(value) == 0
        return False

    def _is_meaningful_table_row(self, row: dict, columns: list[dict]) -> bool:
        for column in columns:
            column_id = str(column.get("id") or "").strip()
            if column_id and not self._is_empty_table_cell(row.get(column_id)):
                return True
        return False

    def _matches_table_cell_type(self, type_name: str, value: object) -> bool:
        """Check one table cell's value against the type its column declares.

        An empty cell always passes: whether a cell may be empty is a required-ness question,
        answered separately by the caller. A column type this does not recognise also passes,
        so a table the form builder permitted is never blocked by an incomplete type list.
        """
        if self._is_empty_table_cell(value):
            return True
        normalized = type_name.strip().lower()
        if normalized == TableColumnType.URL:
            return _matches_entity_field_type(value, EntityFieldType.URL.value)
        if normalized in {
            TableColumnType.TEXT,
            TableColumnType.TEXTAREA,
            TableColumnType.EMAIL,
            TableColumnType.PHONE,
            TableColumnType.DATE,
            TableColumnType.DATETIME,
            TableColumnType.SELECT,
        }:
            return isinstance(value, str)
        if normalized == TableColumnType.BOOLEAN:
            return isinstance(value, bool)
        if normalized in {TableColumnType.INTEGER, TableColumnType.INT}:
            return isinstance(value, int) and not isinstance(value, bool)
        if normalized in {
            TableColumnType.NUMBER,
            TableColumnType.FLOAT,
            TableColumnType.CURRENCY,
            TableColumnType.PERCENT,
        }:
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        if normalized == TableColumnType.MULTI_SELECT:
            return isinstance(value, list)
        return True

    def _validate_entity_schema_against_active_forms(
        self,
        organization_id: str,
        definition: StateMachineDefinition,
        active_schemas: list[EntityTypeSchemaContract] | None = None,
    ) -> list[ValidationIssue]:
        """Compare the workflow's saved entity schema against the live active form.

        Reports, in order: fields the form no longer defines (blocking), fields the form has
        gained, and fields whose type differs — the last two as warnings, since the workflow
        still works, it is just behind. An entity type with no active form is not checked,
        and neither are the fields a pinned Method contributed.
        """
        active_specs = self._active_form_field_specs(
            organization_id, definition.entity_type, active_schemas
        )
        if not active_specs:
            return []

        entity_type = definition.entity_type
        fields = definition.entity_schema.fields
        embedded_fields = {field.field for field in fields}
        # A field a pinned Method contributed (`source_states` non-empty) is
        # authored in the Method Library and merged in at publish time, so no
        # form ever owned it and its absence from one is not drift. Only the
        # workflow's own fields — the ones that came from a form — can be
        # orphaned by that form dropping them.
        form_owned_fields = {field.field for field in fields if not field.source_states}

        issues: list[ValidationIssue] = []
        orphaned = sorted(form_owned_fields - set(active_specs))
        if orphaned:
            issues.append(self._drift_issue(
                ValidationIssueCode.ORPHANED_ENTITY_SCHEMA_FIELD,
                f"Workflow entity_schema for entity_type '{entity_type}' "
                f"contains fields not defined by active forms: {', '.join(orphaned)}.",
            ))

        added = sorted(set(active_specs) - embedded_fields)
        if added:
            issues.append(self._drift_issue(
                ValidationIssueCode.ENTITY_SCHEMA_FIELD_DRIFTED,
                f"The active form for entity_type '{entity_type}' has fields this "
                f"workflow hasn't picked up yet: {', '.join(added)}.",
                severity="warning",
            ))

        retyped = self._retyped_fields(fields, active_specs)
        if retyped:
            issues.append(self._drift_issue(
                ValidationIssueCode.ENTITY_SCHEMA_FIELD_DRIFTED,
                "These entity_schema fields have a different type in the active form than in "
                f"this workflow's saved definition: {', '.join(retyped)}.",
                severity="warning",
            ))

        return issues

    @staticmethod
    def _retyped_fields(
        fields: list[EntityField], active_specs: dict[str, dict[str, object]]
    ) -> list[str]:
        """Fields the workflow and the active form both define, but with different types."""
        return sorted(
            field.field
            for field in fields
            if field.field in active_specs and active_specs[field.field]["type"] != field.type
        )

    @staticmethod
    def _drift_issue(
        code: ValidationIssueCode, message: str, severity: str | None = None
    ) -> ValidationIssue:
        """Build one drift issue, leaving severity at the model default unless given."""
        if severity is None:
            return ValidationIssue(code=code, message=message)
        return ValidationIssue(code=code, message=message, severity=severity)

    def _live_fields_by_name(
        self,
        organization_id: str,
        entity_type: str,
        active_schemas: list[EntityTypeSchemaContract] | None = None,
    ) -> dict[str, EntityField]:
        """Index the live active form's fields by name, first definition winning."""
        schemas = (
            active_schemas
            if active_schemas is not None
            else self.resolve_active_schemas(organization_id, entity_type)
        )
        live_by_field: dict[str, EntityField] = {}
        for schema in schemas:
            for field in schema.fields:
                if field.field and field.field not in live_by_field:
                    live_by_field[field.field] = field
        return live_by_field

    def _resynced_field(
        self, field: EntityField, live: EntityField, organization_id: str, entity_type: str
    ) -> EntityField | None:
        """Return `field` with the live label and enum_values, or None if it cannot be applied.

        Re-validates through the model rather than model_copy, which skips validators: if the
        field's type has ALSO drifted from live, the live enum_values may not be a legal pairing
        with this field's existing type (enum_values on a non-enum field with no picklist_id, for
        instance). Better to leave the field untouched than persist a combination EntityField
        itself would reject — the type-drift warning is what surfaces that for a human.
        """
        try:
            return EntityField.model_validate(
                {
                    **field.model_dump(mode="json"),
                    "description": live.description,
                    "enum_values": list(live.enum_values),
                }
            )
        except PydanticValidationError:
            logger.debug(
                "entity_schema field '%s' type-drift prevented label/enum_values resync "
                "(org=%s, entity_type=%s)",
                field.field,
                organization_id,
                entity_type,
            )
            return None

    def _resync_entity_schema_field_metadata(
        self,
        organization_id: str,
        entity_schema: EntitySchema,
        active_schemas: list[EntityTypeSchemaContract] | None = None,
    ) -> EntitySchema:
        """Refresh label (`description`) and `enum_values` for fields the
        workflow already tracks, from the live active form schema for its
        entity type — never adds, removes, or reorders fields, and never
        touches type/required/other behavior-affecting attributes, so this
        can never change what a workflow validates or how guards evaluate.
        See `_validate_entity_schema_against_active_forms` for the companion
        check that flags fields the form has added/removed/retyped since
        this workflow's entity_schema was last saved."""
        if not entity_schema.fields:
            return entity_schema
        live_by_field = self._live_fields_by_name(
            organization_id, entity_schema.entity_type, active_schemas
        )
        if not live_by_field:
            return entity_schema

        changed = False
        resynced_fields: list[EntityField] = []
        for field in entity_schema.fields:
            live = live_by_field.get(field.field)
            if live is None or (
                live.description == field.description and live.enum_values == field.enum_values
            ):
                resynced_fields.append(field)
                continue
            candidate = self._resynced_field(
                field, live, organization_id, entity_schema.entity_type
            )
            if candidate is None:
                resynced_fields.append(field)
                continue
            changed = True
            resynced_fields.append(candidate)

        if not changed:
            return entity_schema
        return entity_schema.model_copy(update={"fields": resynced_fields})

    def _validate_entity_data(
        self,
        organization_id: str,
        definition: StateMachineDefinition,
        data: dict[str, object],
        schema_fields: list[EntityField] | None = None,
    ) -> None:
        """Validate data dict against the entity schema.

        Raises ValidationError when:
        - a required schema field is missing from data
        - a provided value's Python type does not match the declared schema type
        - data contains a key not declared in the schema
        """
        schema_specs = self._resolved_entity_field_specs(
            organization_id,
            definition,
            schema_fields=schema_fields,
        )
        # unknown keys
        unknown = [key for key in data if key not in schema_specs]
        if unknown:
            raise ValidationError(f"unknown entity fields: {', '.join(sorted(unknown))}")
        # required fields present
        missing = [
            field_name
            for field_name, spec in schema_specs.items()
            # A required timer is an interaction requirement, not a typed
            # value requirement. It may still be running while the record is
            # saved; a transition can separately require its completed value.
            if spec["required"]
            and spec["type"] != "timer_duration"
            and field_name not in data
        ]
        if missing:
            raise ValidationError(f"missing required entity fields: {', '.join(missing)}")
        # type check provided values
        for key, value in data.items():
            if value is None:
                continue
            if not matches_workflow_value(
                schema_specs[key]["type"], value, schema_specs[key].get("enum_values")
            ):
                raise ValidationError(
                    f"entity field '{key}' expects type '{schema_specs[key]['type']}', got '{type(value).__name__}'"
                )
            self._validate_table_value(key, value, schema_specs[key].get("table_config"))


    def _resolved_entity_field_specs(
        self,
        organization_id: str,
        definition: StateMachineDefinition,
        schema_fields: list[EntityField] | None = None,
    ) -> dict[str, dict[str, object]]:
        """Resolve fields from the workflow definition or the active form schema."""
        if schema_fields:
            return {
                item.field: {
                    "type": item.type,
                    "required": item.required,
                    "enum_values": item.enum_values or None,
                    "table_config": item.table_config,
                }
                for item in schema_fields
            }
        if definition.entity_schema.fields:
            return {
                item.field: {
                    "type": item.type,
                    "required": item.required,
                    "enum_values": item.enum_values or None,
                    "table_config": item.table_config,
                }
                for item in definition.entity_schema.fields
            }
        return self._active_form_field_specs(organization_id, definition.entity_type)

    def _active_form_field_specs(
        self,
        organization_id: str,
        entity_type: str,
        active_schemas: list[EntityTypeSchemaContract] | None = None,
    ) -> dict[str, dict[str, object]]:
        """Load active form fields for an entity type."""
        if active_schemas is None:
            active_schemas = self.resolve_active_schemas(organization_id, entity_type)
        if not active_schemas:
            return {}

        field_specs: dict[str, dict[str, object]] = {}
        for schema in active_schemas:
            for f in schema.fields:
                if not f.field or f.type in {"section", "reference"}:
                    continue
                if f.field in field_specs:
                    continue
                field_specs[f.field] = {
                    "type": self._normalize_form_field_type(f.type),
                    "required": f.required,
                    "table_config": f.table_config,
                }
        return field_specs
