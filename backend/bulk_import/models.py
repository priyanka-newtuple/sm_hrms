"""Contracts for the bulk import review lifecycle."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from common.data_model import BaseModel, ExtendedStrEnum

# What a QUEUED job is waiting for — read by the worker's poll loop (follow-up PR)
# to decide whether to call `_run_queued_analysis` or `_run_queued_commit`, since
# both `analyze` and `commit` route through the same QUEUED status value.


# Bulk import upload limits/defaults, read by bulk_import/controller.py's
# create_job route. The file cap protects agent context as well as upload size.
MAX_BULK_IMPORT_FILES = 20
DEFAULT_UPLOAD_CONTENT_TYPE = "application/octet-stream"
FALLBACK_UPLOAD_PREFIX = "upload"

# Manual-mode identifier synthesis (no AI involved) — field priority, then max suffix attempts.
IDENTIFIER_SYNTHESIS_FIELD_PRIORITY = (
    "full_name",
    "name",
    "title",
    "display_name",
    "email_address",
    "email",
)
IDENTIFIER_SYNTHESIS_MAX_SUFFIX_ATTEMPTS = 500

# Per-job input sent to the bulk_import_extractor agent run (bulk_import/manager.py's
# _extract_job). The agent's fixed behavior/tool-usage guidance lives in the system
# prompt (common/system_agents.json) — this only supplies the per-job facts and the
# exact output shape. Kept here, not in manager.py, so the wording is easy to find
# and change without touching orchestration code.
#
# Files are listed as slug = filename pairs (file_manifest) — never a real file id.
# The real id never appears in the prompt, any tool call, or the model's final
# answer; it's only ever known to our own code (see _extract_job's slug_map).
EXTRACTION_USER_PROMPT_TEMPLATE = (
    "Mode: document_extraction. Target entity type: {entity_type_name}. "
    "This job has {file_count} file(s):\n"
    "{file_manifest}\n"
    "Always refer to a file by its slug (file_1, file_2, ...) shown above; never "
    "any other id. Extract every entity you can find across these files. For each "
    "entity, populate identifier with its best human-readable record name unless "
    "get_form_schema marks identifier as generated. The same value may also populate "
    "a domain field such as product_name or full_name. Return "
    "only JSON: "
    '{{"entities":[{{"data":{{"schema_field":"value"}},"confidence":0.0,'
    '"file_ids":["file_1"]}}],"skipped_files":[{{"file_id":"file_2","reason":"..."}}]}}.'
)

SPREADSHEET_MAPPING_USER_PROMPT_TEMPLATE = (
    "Mode: spreadsheet_mapping. Target entity type: {entity_type_name}.\n"
    "Infer semantic mappings from source columns to the exact schema field keys returned by "
    "get_form_schema. Unless identifier is marked as generated, map the best human-readable "
    "name column to identifier. Keep its domain mapping too, so Product Name can map to both "
    "identifier and product_name. A source column may map to multiple fields, and multiple "
    "source columns may contribute to the same field. Use the sample values to disambiguate "
    "headers. Also identify columns whose values are file references, such as image URLs, "
    "document URLs, spec-sheet links, or filenames matching another uploaded file. Put those "
    "columns in remote_file_columns. When columns contain thumbnail and full-resolution versions "
    "of the same asset, prefer the canonical full-resolution column instead of importing both. "
    "Do not map a file-reference column to an ordinary form "
    "field unless that field is explicitly intended to store a live URL. The platform will "
    "preview the source URL directly and create a managed copy only after final confirmation, "
    "while preserving the source URL. Do not "
    "extract entities or process every row. Return only JSON: "
    '{{"mappings":[{{"file_id":"file_1","sheet_name":"Sheet1",'
    '"column_mapping":{{"Source column":["schema_field"]}},'
    '"remote_file_columns":["Image URL"],'
    '"relation_column_mapping":{{"relation_definition_id":"Parent column"}}}}]}}.\n'
    "A relationship mapping means the source column contains the identifier of an existing "
    "provider record. Only use relationship definition ids listed below. Do not map a fixed "
    "relationship, because it already applies to every row.\n"
    "Available parent relationships:\n{relationship_manifest}\n"
    "Spreadsheet metadata and samples:\n{spreadsheet_manifest}"
)


class BulkImportRemoteFileReference(BaseModel):
    """A spreadsheet cell interpreted as an attachment reference."""

    source_column: str
    source_value: str
    source_url: str | None = None
    filename: str | None = None
    file_id: str | None = None
    status: str = "pending"
    error: str | None = None


class BulkImportRelationDefinition(BaseModel):
    """Incoming relationship available while importing the target entity type."""

    relation_def_id: str
    source_entity_type_id: str
    source_entity_type_name: str
    relation_type: Literal["REFERENCE", "SNAPSHOT"]
    fixed_source_entity_id: str | None = None
    fixed_source_entity_label: str | None = None


class BulkImportFixedRelationBinding(BaseModel):
    """One parent record selected as the default for every imported draft."""

    relation_def_id: str
    source_entity_id: str


class BulkImportRelationBinding(BaseModel):
    """Resolved or exceptional parent assignment for one proposed entity."""

    relation_def_id: str
    source_entity_type_id: str
    source_entity_type_name: str
    relation_type: Literal["REFERENCE", "SNAPSHOT"]
    mode: Literal["fixed", "column"]
    source_entity_id: str | None = None
    source_entity_label: str | None = None
    source_column: str | None = None
    source_value: str | None = None
    status: Literal["resolved", "missing"] = "missing"
    error: str | None = None


class BulkImportDraft(BaseModel):
    """A proposed entity extracted from one or more source files, pending review/commit."""

    draft_id: str
    data: dict[str, Any] = Field(default_factory=dict)
    file_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0, ge=0, le=1)
    selected: bool = True
    review_decision: Literal["accepted", "modified", "rejected"] | None = None
    entity_id: str | None = None
    existing_entity: bool = False
    attached_file_ids: list[str] = Field(default_factory=list)
    files_attached: bool = False
    workflow_enrolled: bool = False
    error: str | None = None
    source_kind: str = "document"
    source_sheet_name: str | None = None
    source_row_number: int | None = None
    remote_file_references: list[BulkImportRemoteFileReference] = Field(default_factory=list)
    relation_bindings: list[BulkImportRelationBinding] = Field(default_factory=list)


class BulkImportSpreadsheetSource(BaseModel):
    """Parsed spreadsheet sheet and its agent-proposed field mapping."""

    file_id: str
    filename: str
    sheet_name: str
    row_count: int = 0
    columns: list[str] = Field(default_factory=list)
    column_mapping: dict[str, list[str]] = Field(default_factory=dict)
    remote_file_columns: list[str] = Field(default_factory=list)
    relation_column_mapping: dict[str, str] = Field(default_factory=dict)
    unmapped_columns: list[str] = Field(default_factory=list)


class BulkImportSpreadsheetMapping(BaseModel):
    """Reviewer-selected source-column mapping for one spreadsheet sheet."""

    file_id: str
    sheet_name: str
    column_mapping: dict[str, list[str]] = Field(default_factory=dict)
    remote_file_columns: list[str] = Field(default_factory=list)
    relation_column_mapping: dict[str, str] = Field(default_factory=dict)


class BulkImportSpreadsheetMappingRequest(BaseModel):
    """Complete mapping selection submitted for the spreadsheet sources in a job."""

    mappings: list[BulkImportSpreadsheetMapping] = Field(default_factory=list)


class BulkImportSpreadsheetPreparation(BaseModel):
    """Spreadsheet drafts and source metadata returned to bulk-import orchestration."""

    drafts: list[BulkImportDraft] = Field(default_factory=list)
    sources: list[BulkImportSpreadsheetSource] = Field(default_factory=list)
    skipped_files: dict[str, str] = Field(default_factory=dict)
    mapping_agent_run_id: str | None = None
    parser_warnings: list[str] = Field(default_factory=list)


class QUEUED_JOB_STATUS(ExtendedStrEnum):
    """The status of a queued job."""

    QUEUED_FOR_ANALYZE = "analyze"
    QUEUED_FOR_COMMIT = "commit"


class BulkImportReviewRequest(BaseModel):
    """Reviewer-submitted edits to proposed drafts before commit."""

    drafts: list[BulkImportDraft]
    unmapped_file_ids: list[str] = Field(default_factory=list)
    workflow_name: str | None = None


class BulkImportDiagnostics(BaseModel):
    """Non-critical debug metadata for diagnosing bulk-import worker failures."""

    analysis_stage: str | None = None
    mapping_agent_run_id: str | None = None
    extraction_agent_run_ids: list[str] = Field(default_factory=list)
    parser_warnings: list[str] = Field(default_factory=list)


class BulkImportJobResponse(BaseModel):
    """API view of a bulk import job: its state, files, drafts, and outcome counts."""

    job_id: str
    status: str
    operation: str | None = None
    entity_type_id: str
    entity_type_name: str
    workflow_name: str | None = None
    files: list[dict[str, Any]] = Field(default_factory=list)
    drafts: list[BulkImportDraft] = Field(default_factory=list)
    unmapped_file_ids: list[str] = Field(default_factory=list)
    processed_count: int = 0
    failed_count: int = 0
    created_count: int = 0
    existing_count: int = 0
    commit_processed_count: int = 0
    commit_total_count: int = 0
    cancel_requested: bool = False
    errors: list[str] = Field(default_factory=list)
    spreadsheet_sources: list[BulkImportSpreadsheetSource] = Field(default_factory=list)
    relation_definitions: list[BulkImportRelationDefinition] = Field(default_factory=list)
    diagnostics: BulkImportDiagnostics | None = None


class BulkImportJobSummary(BaseModel):
    """Lightweight view of a bulk import job for the recent-imports list.

    Deliberately excludes `files`/`drafts`/`errors` (the full payload `get_job`
    returns) — this is meant to be cheap to fetch as a list, not a per-job detail
    view.
    """

    job_id: str
    status: str
    entity_type_id: str
    entity_type_name: str
    file_count: int = 0
    draft_count: int = 0
    created_at: str | None = None
    updated_at: str | None = None


class BulkImportJobListResponse(BaseModel):
    """API view of an organization's recent bulk import jobs, newest first."""

    items: list[BulkImportJobSummary] = Field(default_factory=list)
