"""Relationship discovery and deterministic parent resolution for bulk import."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from bulk_import.models import (
    BulkImportFixedRelationBinding,
    BulkImportRelationBinding,
    BulkImportRelationDefinition,
)
from exceptions import ValidationError

if TYPE_CHECKING:
    from entities.manager import EntitiesServiceManager


class BulkImportRelationBindingService:
    """Resolve fixed and spreadsheet-provided parents using existing entity records."""

    def __init__(self, *, entities: EntitiesServiceManager) -> None:
        self.entities = entities

    def discover(
        self,
        actor: dict[str, object],
        target_entity_type_id: str,
    ) -> list[BulkImportRelationDefinition]:
        """List inheritance-style incoming relationships available to the target type."""
        organization_id = str(actor.get("organization_id") or "")
        type_names = {
            item.entity_type_id: item.name
            for item in self.entities.list_entity_type_records(
                organization_id=organization_id, include_inactive=False
            )
        }
        declarations = self.entities.list_entity_relation_declarations_for_actor(
            actor, target_entity_type_id, direction="to"
        )
        return [
            BulkImportRelationDefinition(
                relation_def_id=item.relation_def_id,
                source_entity_type_id=item.from_entity_type_id,
                source_entity_type_name=type_names.get(item.from_entity_type_id, "Related record"),
                relation_type=str(item.relation_type.value).upper(),
            )
            for item in declarations.items
            if item.to_entity_type_id == target_entity_type_id and item.relation_name is None
        ]

    def apply_fixed_choices(
        self,
        actor: dict[str, object],
        definitions: list[BulkImportRelationDefinition],
        choices: list[BulkImportFixedRelationBinding],
    ) -> list[BulkImportRelationDefinition]:
        """Validate fixed parents and enrich definitions with their display labels."""
        definitions_by_id = {item.relation_def_id: item for item in definitions}
        seen: set[str] = set()
        for choice in choices:
            if choice.relation_def_id in seen:
                raise ValidationError("a fixed parent relationship was selected more than once")
            seen.add(choice.relation_def_id)
            definition = definitions_by_id.get(choice.relation_def_id)
            if definition is None:
                raise ValidationError("fixed parent references an unavailable relationship")
            record = self.entities.get_entity_record_for_actor(actor, choice.source_entity_id)
            if record.entity_type_id != definition.source_entity_type_id:
                raise ValidationError("fixed parent has the wrong entity type")
            definition.fixed_source_entity_id = record.entity_id
            definition.fixed_source_entity_label = self._record_label(record.data, record.entity_id)
        return definitions

    def build_bindings(
        self,
        actor: dict[str, object],
        definitions: list[BulkImportRelationDefinition],
        relation_column_mapping: dict[str, str],
        row: dict[str, Any],
        indexes: dict[tuple[str, str], tuple[Any | None, str | None]] | None = None,
    ) -> list[BulkImportRelationBinding]:
        """Build one draft's fixed or exact-identifier column bindings."""
        indexes = indexes if indexes is not None else {}
        bindings: list[BulkImportRelationBinding] = []
        for definition in definitions:
            if definition.fixed_source_entity_id:
                bindings.append(
                    self._binding(
                        definition,
                        mode="fixed",
                        source_entity_id=definition.fixed_source_entity_id,
                        source_entity_label=definition.fixed_source_entity_label,
                        status="resolved",
                    )
                )
                continue
            column = relation_column_mapping.get(definition.relation_def_id)
            if column:
                bindings.append(
                    self._resolve_column_binding(actor, definition, column, row, indexes)
                )
            elif definition.relation_type == "REFERENCE":
                bindings.append(
                    self._binding(
                        definition,
                        mode="column",
                        error=f"Choose a fixed {definition.source_entity_type_name} or map a parent column",
                    )
                )
        return bindings

    def _resolve_column_binding(
        self,
        actor: dict[str, object],
        definition: BulkImportRelationDefinition,
        column: str,
        row: dict[str, Any],
        lookups: dict[tuple[str, str], tuple[Any | None, str | None]],
    ) -> BulkImportRelationBinding:
        source_value = str(row.get(column) or "").strip()
        if not source_value:
            return self._binding(
                definition,
                mode="column",
                source_column=column,
                error=f"No {definition.source_entity_type_name} identifier in {column}",
            )
        cache_key = (definition.source_entity_type_id, source_value)
        if cache_key not in lookups:
            lookups[cache_key] = self._find_parent(actor, definition, source_value)
        record, error = lookups[cache_key]
        return self._binding(
            definition,
            mode="column",
            source_entity_id=record.entity_id if record else None,
            source_entity_label=(
                self._record_label(record.data, record.entity_id) if record else None
            ),
            source_column=column,
            source_value=source_value,
            status="resolved" if record else "missing",
            error=error,
        )

    def _find_parent(
        self,
        actor: dict[str, object],
        definition: BulkImportRelationDefinition,
        source_value: str,
    ) -> tuple[Any | None, str | None]:
        """Resolve one identifier with bounded search and explicit ambiguity handling."""
        records = self.entities.list_entity_records_by_type_name_for_actor(
            actor,
            definition.source_entity_type_name,
            search=source_value,
            limit=20,
        ).items
        exact = [record for record in records if self._identifier(record) == source_value]
        if len(exact) == 1:
            return exact[0], None
        folded = [
            record
            for record in records
            if self._identifier(record).casefold() == source_value.casefold()
        ]
        if len(folded) == 1:
            return folded[0], None
        if len(folded) > 1:
            return None, (
                f'Ambiguous {definition.source_entity_type_name} identifier "{source_value}"; '
                "use the exact capitalization"
            )
        return None, f'No exact {definition.source_entity_type_name} match for "{source_value}"'

    @staticmethod
    def _identifier(record: Any) -> str:
        return str((record.data or {}).get("identifier") or "").strip()

    @staticmethod
    def validate_column_mapping(
        definitions: list[BulkImportRelationDefinition],
        mapping: dict[str, str],
        columns: set[str],
    ) -> None:
        available = {item.relation_def_id: item for item in definitions}
        for relation_def_id, column in mapping.items():
            definition = available.get(relation_def_id)
            if definition is None:
                raise ValidationError("parent mapping references an unavailable relationship")
            if definition.fixed_source_entity_id:
                raise ValidationError("a fixed parent cannot also use a spreadsheet column")
            if column not in columns:
                raise ValidationError("parent mapping references an unknown column")

    @staticmethod
    def resolved_source_ids(bindings: list[BulkImportRelationBinding]) -> list[str]:
        return list(
            dict.fromkeys(
                item.source_entity_id
                for item in bindings
                if item.status == "resolved" and item.source_entity_id
            )
        )

    @staticmethod
    def _record_label(data: dict[str, Any], entity_id: str) -> str:
        for key in ("identifier", "name", "title", "full_name"):
            value = str((data or {}).get(key) or "").strip()
            if value:
                return value
        return entity_id[:8]

    @staticmethod
    def _binding(
        definition: BulkImportRelationDefinition, **values: Any
    ) -> BulkImportRelationBinding:
        return BulkImportRelationBinding(
            relation_def_id=definition.relation_def_id,
            source_entity_type_id=definition.source_entity_type_id,
            source_entity_type_name=definition.source_entity_type_name,
            relation_type=definition.relation_type,
            **values,
        )
