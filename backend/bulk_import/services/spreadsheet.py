"""Spreadsheet-specific preparation for bulk-import review."""

from __future__ import annotations

import json
import os
import re
from typing import TYPE_CHECKING, Any
from uuid import NAMESPACE_URL, uuid5

from agent.models.request import AgentRunRequest
from bulk_import.models import (
    SPREADSHEET_MAPPING_USER_PROMPT_TEMPLATE,
    BulkImportDraft,
    BulkImportRelationDefinition,
    BulkImportRemoteFileReference,
    BulkImportSpreadsheetMapping,
    BulkImportSpreadsheetPreparation,
    BulkImportSpreadsheetSource,
)
from bulk_import.services.agent_results import parse_agent_payload_with_metadata
from common.logger import logger
from entities.models.interface import IDENTIFIER_FIELD_KEY
from exceptions import ServiceError, ValidationError
from fileprocessor.models.interface import TabularSheet

if TYPE_CHECKING:
    from collections.abc import Callable

    from agent.manager import AgentServiceManager
    from bulk_import.services.relation_bindings import BulkImportRelationBindingService
    from entities.manager import EntitiesServiceManager
    from filehandler.manager import FilehandlerServiceManager
    from fileprocessor.manager import FileprocessorServiceManager

SPREADSHEET_EXTENSIONS = frozenset({".csv", ".xls", ".xlsx"})
IDENTIFIER_MAPPING_TARGET_PRIORITY = (
    "product_name",
    "full_name",
    "name",
    "title",
    "display_name",
    "company_name",
    "email_address",
    "email",
)


class SpreadsheetImportService:
    """Prepare spreadsheet rows and mappings for bulk-import review."""

    def __init__(
        self,
        *,
        filehandler: FilehandlerServiceManager,
        fileprocessor: FileprocessorServiceManager,
        entities: EntitiesServiceManager,
        agents: AgentServiceManager,
        relations: BulkImportRelationBindingService,
    ) -> None:
        self.filehandler = filehandler
        self.fileprocessor = fileprocessor
        self.entities = entities
        self.agents = agents
        self.relations = relations

    @staticmethod
    def is_spreadsheet_file(file: dict[str, Any]) -> bool:
        """Return whether a stored source should use deterministic tabular parsing."""
        extension = os.path.splitext(str(file.get("filename") or ""))[1].lower()
        return extension in SPREADSHEET_EXTENSIONS

    def prepare_drafts(
        self,
        actor: dict[str, object],
        *,
        organization_id: str,
        job_id: str,
        entity_type_id: str,
        entity_type_name: str,
        files: list[dict[str, Any]],
        uploaded_files: list[dict[str, Any]],
        mapping_overrides: dict[tuple[str, str], BulkImportSpreadsheetMapping] | None = None,
        definition_id_provider: Callable[[], str] | None = None,
        relation_definitions: list[BulkImportRelationDefinition] | None = None,
    ) -> BulkImportSpreadsheetPreparation:
        """Parse rows and apply agent-proposed or reviewer-provided mappings."""
        relation_definitions = relation_definitions or []
        if not files:
            return BulkImportSpreadsheetPreparation()

        parsed_sheets: list[dict[str, Any]] = []
        skipped: dict[str, str] = {}
        for file in files:
            file_id = str(file.get("file_id") or "")
            filename = str(file.get("filename") or "unknown")
            try:
                source = self.filehandler.read_document_source(
                    organization_id, document_id=file_id, storage_key=None
                )
                if source is None:
                    raise ServiceError("stored spreadsheet could not be read")
                sheets = self.fileprocessor.extract_tabular_sheets(
                    filename=str(source.get("filename") or filename),
                    content_type=str(source.get("content_type") or "application/octet-stream"),
                    file_bytes=source.get("file_bytes") or b"",
                )
                for sheet_index, raw_sheet in enumerate(sheets):
                    sheet = TabularSheet.model_validate(raw_sheet)
                    sheet_name = sheet.sheet_name or f"Sheet {sheet_index + 1}"
                    parsed_sheets.append(
                        {
                            "file_id": file_id,
                            "filename": filename,
                            "sheet_name": sheet_name,
                            "columns": [column.name for column in sheet.columns],
                            "column_samples": {
                                column.name: column.sample_values for column in sheet.columns
                            },
                            "rows": sheet.rows,
                        }
                    )
            except Exception as exc:
                logger.warning("bulk import: spreadsheet %s could not be parsed: %s", file_id, exc)
                skipped[file_id] = str(exc)

        inferred_mappings: dict[tuple[str, str], BulkImportSpreadsheetMapping] = {}
        mapping_agent_run_id: str | None = None
        parser_warnings: list[str] = []
        if mapping_overrides is None and parsed_sheets:
            if definition_id_provider is None:
                raise ServiceError("spreadsheet mapping requires an agent definition")
            inferred_mappings, mapping_agent_run_id, parser_warnings = self._infer_mappings(
                actor,
                entity_type_id=entity_type_id,
                entity_type_name=entity_type_name,
                parsed_sheets=parsed_sheets,
                definition_id=definition_id_provider(),
                relation_definitions=relation_definitions,
            )

        allowed_targets = set(self._field_lookup(organization_id, entity_type_name).values())
        drafts: list[BulkImportDraft] = []
        sources: list[BulkImportSpreadsheetSource] = []
        proposals = mapping_overrides or inferred_mappings
        relation_lookups: dict[tuple[str, str], tuple[Any | None, str | None]] = {}
        for sheet in parsed_sheets:
            file_id = str(sheet["file_id"])
            filename = str(sheet["filename"])
            sheet_name = str(sheet["sheet_name"])
            columns = list(sheet["columns"])
            rows = list(sheet["rows"])
            proposal = proposals.get(
                (file_id, sheet_name),
                BulkImportSpreadsheetMapping(file_id=file_id, sheet_name=sheet_name),
            )
            mapping = {
                column: list(dict.fromkeys(targets))
                for column, targets in proposal.column_mapping.items()
                if column in columns
                and targets
                and all(target in allowed_targets for target in targets)
            }
            remote_file_columns = [
                column
                for column in dict.fromkeys(proposal.remote_file_columns)
                if column in columns
            ]
            relation_column_mapping = {
                relation_def_id: column
                for relation_def_id, column in proposal.relation_column_mapping.items()
                if column in columns
                and any(item.relation_def_id == relation_def_id for item in relation_definitions)
                and not next(
                    item.fixed_source_entity_id
                    for item in relation_definitions
                    if item.relation_def_id == relation_def_id
                )
            }
            sources.append(
                BulkImportSpreadsheetSource(
                    file_id=file_id,
                    filename=filename,
                    sheet_name=sheet_name,
                    row_count=len(rows),
                    columns=columns,
                    column_mapping=mapping,
                    remote_file_columns=remote_file_columns,
                    relation_column_mapping=relation_column_mapping,
                    unmapped_columns=[
                        column
                        for column in columns
                        if column not in mapping
                        and column not in remote_file_columns
                        and column not in relation_column_mapping.values()
                    ],
                )
            )
            for tabular_row in rows:
                row = tabular_row.values
                values_by_target: dict[str, list[Any]] = {}
                for source_column, targets in mapping.items():
                    value = row.get(source_column)
                    if value in (None, ""):
                        continue
                    for target in targets:
                        values_by_target.setdefault(target, []).append(value)
                data = {
                    target: values[0]
                    if len(values) == 1
                    else " ".join(str(value) for value in values)
                    for target, values in values_by_target.items()
                }
                drafts.append(
                    BulkImportDraft(
                        draft_id=str(
                            uuid5(
                                NAMESPACE_URL,
                                f"bulk-import:{organization_id}:{job_id}:{file_id}:"
                                f"{sheet_name}:{tabular_row.source_row_number}",
                            )
                        ),
                        data=data,
                        file_ids=[],
                        confidence=0.9 if data else 0,
                        selected=bool(data),
                        error=(
                            None if data else "No spreadsheet columns mapped to this entity schema"
                        ),
                        source_kind="spreadsheet",
                        source_sheet_name=sheet_name,
                        source_row_number=tabular_row.source_row_number,
                        remote_file_references=[
                            BulkImportRemoteFileReference(
                                source_column=column,
                                source_value=str(row.get(column) or "").strip(),
                            )
                            for column in remote_file_columns
                            if str(row.get(column) or "").strip()
                        ],
                        relation_bindings=self.relations.build_bindings(
                            actor,
                            relation_definitions,
                            relation_column_mapping,
                            row,
                            indexes=relation_lookups,
                        ),
                    )
                )

        self._resolve_file_references(uploaded_files, drafts)
        return BulkImportSpreadsheetPreparation(
            drafts=drafts,
            sources=sources,
            skipped_files=skipped,
            mapping_agent_run_id=mapping_agent_run_id,
            parser_warnings=parser_warnings,
        )

    def validate_mappings(
        self,
        *,
        organization_id: str,
        entity_type_name: str,
        known_sources: list[BulkImportSpreadsheetSource],
        mappings: list[BulkImportSpreadsheetMapping],
        relation_definitions: list[BulkImportRelationDefinition] | None = None,
    ) -> None:
        """Validate reviewer mappings against parsed sources and the current entity schema."""
        source_columns = {
            (source.file_id, source.sheet_name): set(source.columns) for source in known_sources
        }
        allowed_targets = set(self._field_lookup(organization_id, entity_type_name).values())
        relation_definitions = relation_definitions or []
        for item in mappings:
            source_key = (item.file_id, item.sheet_name)
            if source_key not in source_columns:
                raise ValidationError("spreadsheet mapping references an unknown sheet")
            if any(column not in source_columns[source_key] for column in item.column_mapping):
                raise ValidationError("spreadsheet mapping references an unknown column")
            if any(column not in source_columns[source_key] for column in item.remote_file_columns):
                raise ValidationError("remote file mapping references an unknown column")
            if any(
                target not in allowed_targets
                for targets in item.column_mapping.values()
                for target in targets
            ):
                raise ValidationError("spreadsheet mapping references an unknown entity field")
            self.relations.validate_column_mapping(
                relation_definitions,
                item.relation_column_mapping,
                source_columns[source_key],
            )

    def _infer_mappings(
        self,
        actor: dict[str, object],
        *,
        entity_type_id: str,
        entity_type_name: str,
        parsed_sheets: list[dict[str, Any]],
        definition_id: str,
        relation_definitions: list[BulkImportRelationDefinition],
    ) -> tuple[dict[tuple[str, str], BulkImportSpreadsheetMapping], str | None, list[str]]:
        file_ids = list(dict.fromkeys(str(sheet["file_id"]) for sheet in parsed_sheets))
        slug_map = {f"file_{index + 1}": file_id for index, file_id in enumerate(file_ids)}
        reverse_slug_map = {file_id: slug for slug, file_id in slug_map.items()}
        manifest = [
            {
                "file_id": reverse_slug_map[str(sheet["file_id"])],
                "filename": sheet["filename"],
                "sheet_name": sheet["sheet_name"],
                "columns": sheet["columns"],
                "column_samples": sheet["column_samples"],
            }
            for sheet in parsed_sheets
        ]
        run = self.agents.run_agent_for_actor(
            actor,
            AgentRunRequest(
                definition_id=definition_id,
                input=SPREADSHEET_MAPPING_USER_PROMPT_TEMPLATE.format(
                    entity_type_name=entity_type_name,
                    relationship_manifest=json.dumps(
                        [
                            {
                                "relation_definition_id": item.relation_def_id,
                                "provider_entity_type": item.source_entity_type_name,
                                "relation_type": item.relation_type,
                            }
                            for item in relation_definitions
                            if not item.fixed_source_entity_id
                        ],
                        ensure_ascii=False,
                    ),
                    spreadsheet_manifest=json.dumps(manifest, ensure_ascii=False, default=str),
                ),
            ),
        )
        run_id = str(getattr(run, "run_id", "") or "") or None
        if run.status != "completed":
            exc = ServiceError(run.error or "spreadsheet mapping agent did not complete")
            exc.mapping_agent_run_id = run_id
            raise exc
        try:
            parsed = parse_agent_payload_with_metadata(str(run.output or ""))
        except ValidationError as exc:
            exc.mapping_agent_run_id = run_id
            raise
        payload = parsed.payload
        result: dict[tuple[str, str], BulkImportSpreadsheetMapping] = {}
        for item in payload.get("mappings") or []:
            if not isinstance(item, dict):
                continue
            file_id = slug_map.get(str(item.get("file_id") or ""))
            raw_mapping = item.get("column_mapping")
            if file_id is None or not isinstance(raw_mapping, dict):
                continue
            raw_remote_columns = item.get("remote_file_columns")
            raw_relation_mapping = item.get("relation_column_mapping")
            proposal = BulkImportSpreadsheetMapping(
                file_id=file_id,
                sheet_name=str(item.get("sheet_name") or ""),
                column_mapping={
                    str(column): [str(target) for target in targets if str(target).strip()]
                    for column, targets in raw_mapping.items()
                    if isinstance(targets, list)
                },
                remote_file_columns=(
                    [str(column) for column in raw_remote_columns if str(column).strip()]
                    if isinstance(raw_remote_columns, list)
                    else []
                ),
                relation_column_mapping=(
                    {
                        str(relation_def_id): str(column)
                        for relation_def_id, column in raw_relation_mapping.items()
                        if str(relation_def_id).strip() and str(column).strip()
                    }
                    if isinstance(raw_relation_mapping, dict)
                    else {}
                ),
            )
            result[(proposal.file_id, proposal.sheet_name)] = proposal

        identifier_template = self.entities.get_identifier_template_for_actor(actor, entity_type_id)
        if not identifier_template:
            for proposal in result.values():
                self._ensure_identifier_mapping(proposal.column_mapping)
        return result, run_id, parsed.warnings

    def _field_lookup(self, organization_id: str, entity_type_name: str) -> dict[str, str]:
        lookup = {self._normalized_column_name(IDENTIFIER_FIELD_KEY): IDENTIFIER_FIELD_KEY}
        for field in self.entities.get_form_fields(organization_id, entity_type_name):
            if not isinstance(field, dict):
                continue
            field_id = str(field.get("field") or field.get("name") or field.get("id") or "").strip()
            if not field_id:
                continue
            for candidate in (field_id, field.get("label"), field_id.replace("_", " ")):
                normalized = self._normalized_column_name(candidate)
                if normalized:
                    lookup.setdefault(normalized, field_id)
        return lookup

    @staticmethod
    def _normalized_column_name(value: object) -> str:
        return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())

    @staticmethod
    def _split_file_references(value: str) -> list[str]:
        return [item.strip() for item in re.split(r"[\n;]+", value) if item.strip()]

    def _resolve_file_references(
        self,
        uploaded_files: list[dict[str, Any]],
        drafts: list[BulkImportDraft],
    ) -> None:
        uploaded_by_name = {
            str(item.get("filename") or "").strip().casefold(): item
            for item in uploaded_files
            if str(item.get("filename") or "").strip()
        }
        for draft in drafts:
            original = list(draft.remote_file_references)
            draft.remote_file_references = []
            for reference in original:
                for value in self._split_file_references(reference.source_value):
                    resolved = reference.model_copy(update={"source_value": value})
                    draft.remote_file_references.append(resolved)
                    if value.lower().startswith(("http://", "https://")):
                        resolved.source_url = value
                        if value.lower().startswith("https://"):
                            resolved.status = "referenced"
                        else:
                            resolved.status = "failed"
                            resolved.error = "remote attachments must use HTTPS"
                        continue
                    stored = uploaded_by_name.get(os.path.basename(value).casefold())
                    if stored:
                        resolved.file_id = str(stored.get("file_id") or "") or None
                        resolved.filename = str(stored.get("filename") or value)
                        resolved.status = "resolved"
                    else:
                        resolved.filename = os.path.basename(value)
                        resolved.status = "missing"
                        resolved.error = "no uploaded file matches this filename"
                    if resolved.file_id and resolved.file_id not in draft.file_ids:
                        draft.file_ids.append(resolved.file_id)

    @staticmethod
    def _ensure_identifier_mapping(mapping: dict[str, list[str]]) -> None:
        if any(IDENTIFIER_FIELD_KEY in targets for targets in mapping.values()):
            return
        for target in IDENTIFIER_MAPPING_TARGET_PRIORITY:
            source_targets = next(
                (targets for targets in mapping.values() if target in targets),
                None,
            )
            if source_targets is not None:
                source_targets.append(IDENTIFIER_FIELD_KEY)
                return
