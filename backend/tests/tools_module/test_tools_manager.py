from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from connectors.manager import ConnectorsServiceManager
from connectors.models.interface import ConnectorContract
from entities.models.response import EntityRecordResponse
from exceptions import NotFoundError, ServiceError, ValidationError
from tools.models.interface import ToolExecutionContext, ToolExecutionResult
from tools.models.request import ToolExecutionLogListRequest, ToolExecutionRequest

if TYPE_CHECKING:
    from tools.manager import ToolsServiceManager

from .factories import (
    PLATFORM_RUNTIME_TOOL_ARGUMENTS,
    build_platform_runtime_arguments,
    build_platform_runtime_output,
)
from .fakes import (
    StubConnectorsDbModelService,
    StubDashboardServiceManager,
    StubEntitiesManager,
    StubWorkflowManager,
)


def test_validate_runtime_tools_handles_none_and_empty_request(tools_manager) -> None:
    all_tools = tools_manager.validate_runtime_tools(None)
    assert "read_document" in all_tools
    assert "add_stage_comment" in all_tools

    assert tools_manager.validate_runtime_tools([]) == []
    assert tools_manager.build_runtime_tools([]) == []


def test_execute_tool_persists_modular_execution_log(
    tools_manager,
    recruiter_actor,
    comments_manager,
) -> None:
    result = tools_manager.execute_tool_for_actor(
        recruiter_actor,
        ToolExecutionRequest(
            tool_name="add_stage_comment",
            arguments={"entity_id": "entity-1", "text": "hello"},
            source="agent",
        ),
    )

    assert result.success is True
    assert result.execution_backend == "modular"
    assert result.execution_id is not None
    assert comments_manager.last_call is not None
    assert comments_manager.last_call["text"] == "hello"

    history = tools_manager.list_executions_for_actor(recruiter_actor, ToolExecutionLogListRequest())
    assert history.total == 1
    assert history.items[0].id == result.execution_id
    assert history.items[0].tool_name == "add_stage_comment"


@pytest.mark.parametrize("tool_name", sorted(PLATFORM_RUNTIME_TOOL_ARGUMENTS))
def test_execute_tool_persists_platform_runtime_execution_log(
    tools_manager,
    recruiter_actor,
    monkeypatch,
    tool_name: str,
) -> None:
    def _execute_platform_tool(
        tool_name: str,
        arguments: dict[str, object],
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        assert context.organization_id == "org-1"
        return ToolExecutionResult(
            success=True,
            tool_name=tool_name,
            output=build_platform_runtime_output(tool_name, arguments),
        )

    monkeypatch.setattr(tools_manager, "_execute_platform_tool", _execute_platform_tool)

    result = tools_manager.execute_tool_for_actor(
        recruiter_actor,
        ToolExecutionRequest(tool_name=tool_name, arguments=build_platform_runtime_arguments(tool_name)),
    )

    assert result.success is True
    assert result.execution_backend == "platform_runtime"
    assert result.execution_id is not None
    assert result.output["tool_name"] == tool_name

    log_entry = tools_manager.get_execution_for_actor(recruiter_actor, result.execution_id)
    assert log_entry.execution_backend == "platform_runtime"
    assert log_entry.arguments == build_platform_runtime_arguments(tool_name)


def test_execute_list_entity_types_uses_modular_handler(tools_manager, recruiter_actor) -> None:
    result = tools_manager.execute_tool_for_actor(
        recruiter_actor,
        ToolExecutionRequest(tool_name="list_entity_types", arguments={}),
    )

    assert result.success is True
    assert result.execution_backend == "modular"
    assert result.output["count"] == 1
    assert result.output["entity_types"][0]["entity_type"] == "application"


def test_execute_read_document_extracts_content_via_fileprocessor(tools_manager, recruiter_actor) -> None:
    result = tools_manager.execute_tool_for_actor(
        recruiter_actor,
        ToolExecutionRequest(
            tool_name="read_document",
            arguments={"storage_key": "documents/resume.txt"},
        ),
    )

    assert result.success is True
    assert result.execution_backend == "platform_runtime"
    assert result.output["document_id"] == "doc-1"
    assert result.output["text"] == "Hello world"
    assert result.output["detected_format"] == "text"


def test_read_document_falls_back_to_file_id_from_context(tools_manager) -> None:
    # No document_id/storage_key in the tool args — the file id comes from the run
    # context (set when the run was triggered by a document upload).
    result = tools_manager._execute_read_document(
        {},
        ToolExecutionContext(organization_id="org-1", metadata={"file_id": "doc-1"}),
    )

    assert result.success is True
    assert result.output["document_id"] == "doc-1"
    assert result.output["text"] == "Hello world"


def test_read_document_fallback_through_public_execute_tool(tools_manager) -> None:
    # Exercise the full public dispatch path (execute_tool → descriptor lookup →
    # handler) to verify the context->file_id fallback works end-to-end, not just via
    # the private handler. The run context carries file_id in metadata (set by the
    # agent capability layer at runtime); no document_id/storage_key in the args.
    result = tools_manager.execute_tool(
        "read_document",
        {},
        ToolExecutionContext(organization_id="org-1", metadata={"file_id": "doc-1"}),
    )

    assert result.success is True
    assert result.output["document_id"] == "doc-1"
    assert result.output["text"] == "Hello world"


def test_read_document_requires_id_when_absent_everywhere(tools_manager) -> None:
    with pytest.raises(ValidationError):
        tools_manager._execute_read_document(
            {}, ToolExecutionContext(organization_id="org-1")
        )


def test_read_job_document_returns_per_file_results_for_a_batch(tools_manager) -> None:
    result = tools_manager._execute_read_job_document(
        {"file_ids": ["file-1", "file-2"]},
        ToolExecutionContext(
            organization_id="org-1",
            run_id="run-1",
            metadata={"file_slug_map": {"file-1": "file-1", "file-2": "file-2"}},
        ),
    )

    assert result.success is True
    results = result.output["results"]
    assert [item["file_id"] for item in results] == ["file-1", "file-2"]
    assert all(item["status"] == "ok" for item in results)
    assert all(item["text"] == "Hello world" for item in results)


def test_read_job_document_rejects_an_unrecognized_slug(tools_manager) -> None:
    result = tools_manager._execute_read_job_document(
        {"file_ids": ["file-unknown"]},
        ToolExecutionContext(organization_id="org-1", run_id="run-1b", metadata={"file_slug_map": {}}),
    )

    entry = result.output["results"][0]
    assert entry["status"] == "error"
    assert "unknown file slug" in entry["message"]


def test_read_job_document_isolates_a_per_file_error_in_a_batch(tools_manager, monkeypatch) -> None:
    original_read_source = tools_manager.documents_service_manager.read_document_source

    def _flaky_read_source(organization_id: str, *, document_id=None, storage_key=None):
        if document_id == "file-bad":
            return None
        return original_read_source(organization_id, document_id=document_id, storage_key=storage_key)

    monkeypatch.setattr(
        tools_manager.documents_service_manager, "read_document_source", _flaky_read_source
    )

    result = tools_manager._execute_read_job_document(
        {"file_ids": ["file-1", "file-bad"]},
        ToolExecutionContext(
            organization_id="org-1",
            run_id="run-2",
            metadata={"file_slug_map": {"file-1": "file-1", "file-bad": "file-bad"}},
        ),
    )

    assert result.success is True  # one bad file never fails the whole call
    by_id = {item["file_id"]: item for item in result.output["results"]}
    assert by_id["file-1"]["status"] == "ok"
    assert by_id["file-bad"]["status"] == "error"
    assert "not found" in by_id["file-bad"]["message"]


def test_read_job_document_rejects_empty_file_ids(tools_manager) -> None:
    with pytest.raises(ValidationError, match="non-empty"):
        tools_manager._execute_read_job_document(
            {"file_ids": []}, ToolExecutionContext(organization_id="org-1", run_id="run-3")
        )


def test_read_job_document_rejects_more_than_the_per_call_limit(tools_manager) -> None:
    with pytest.raises(ValidationError, match="at most"):
        tools_manager._execute_read_job_document(
            {"file_ids": ["file-1", "file-2", "file-3", "file-4"]},
            ToolExecutionContext(organization_id="org-1", run_id="run-4"),
        )


def test_read_job_document_truncates_oversized_file_text(tools_manager, monkeypatch) -> None:
    from tools.models.interface import READ_JOB_DOCUMENT_PER_FILE_CHAR_CAP

    oversized_text = "x" * (READ_JOB_DOCUMENT_PER_FILE_CHAR_CAP + 500)
    monkeypatch.setattr(
        tools_manager.fileprocessor_service_manager,
        "extract_content",
        lambda **_: {"parse_ok": True, "text": oversized_text, "detected_format": "text", "truncated": False},
    )

    result = tools_manager._execute_read_job_document(
        {"file_ids": ["file-1"]},
        ToolExecutionContext(
            organization_id="org-1",
            run_id="run-5",
            metadata={"file_slug_map": {"file-1": "file-1"}},
        ),
    )

    entry = result.output["results"][0]
    assert entry["status"] == "ok"
    assert entry["truncated"] is True
    assert len(entry["text"]) == READ_JOB_DOCUMENT_PER_FILE_CHAR_CAP


def test_read_job_document_stops_once_the_run_budget_is_exhausted(tools_manager) -> None:
    from tools.models.interface import READ_JOB_DOCUMENT_RUN_BUDGET_CHARS

    tools_manager._read_job_document_run_budget["run-6"] = READ_JOB_DOCUMENT_RUN_BUDGET_CHARS

    result = tools_manager._execute_read_job_document(
        {"file_ids": ["file-1"]},
        ToolExecutionContext(organization_id="org-1", run_id="run-6"),
    )

    entry = result.output["results"][0]
    assert entry["status"] == "error"
    assert "context budget exhausted" in entry["message"]


def test_execute_get_form_schema_reads_form_definition_from_entities_manager(tools_manager, recruiter_actor) -> None:
    result = tools_manager.execute_tool_for_actor(
        recruiter_actor,
        ToolExecutionRequest(
            tool_name="get_form_schema",
            arguments={"entity_type": "ATS.Candidate"},
        ),
    )

    assert result.success is True
    assert result.execution_backend == "platform_runtime"
    assert result.output["entity_type"] == "ATS.Candidate"

    fields = {f["id"]: f for f in result.output["fields"]}
    identifier = fields["identifier"]
    assert identifier["label"] == "Candidate Unique Name"
    assert identifier["required"] is True
    assert identifier["system"] is True
    assert identifier["generated"] is False
    assert "full_name" in identifier["description"]
    # Scalar fields keep the original shape (byte-compatible with prior behavior).
    assert fields["full_name"]["type"] == "text"
    assert fields["full_name"]["required"] is True
    assert fields["candidate_source"]["options"] == ["Referral", "Website"]
    assert result.output["attachment_support"] == {
        "supported": True,
        "mapping_key": "remote_file_columns",
        "default_mode": "managed_copy_with_source_url",
        "accepted_references": ["https_url", "uploaded_filename"],
        "description": (
            "In spreadsheet mapping mode, classify image/document URL or uploaded "
            "filename columns as remote_file_columns. The platform previews URLs "
            "directly, then fetches and attaches managed copies only after final "
            "confirmation; do not place file bytes in entity fields."
        ),
    }

    # A Table/Grid field is surfaced as type "table" with its column keys so an agent
    # can build the row-array for update_entity.
    table_field = fields["skills_table"]
    assert table_field["type"] == "table"
    table = table_field["table"]
    assert table["row_mode"] == "dynamic"
    cols = {c["key"]: c for c in table["columns"]}
    assert set(cols) == {"skill", "years", "score"}
    assert cols["skill"]["type"] == "text" and cols["skill"]["required"] is True
    # A calc column is flagged readonly so the agent skips computed cells.
    assert cols["score"]["readonly"] is True


def test_execute_get_form_schema_marks_templated_identifier_as_generated(
    manager_factory, recruiter_actor
) -> None:
    entities_manager = StubEntitiesManager()
    original_get = entities_manager.get_entity_type_record

    def get_templated_type(*, organization_id: str, name: str):  # noqa: ANN202
        record = original_get(organization_id=organization_id, name=name)
        if record is not None:
            record.schema_definition["identifier_template"] = "PROD-{{seq}}"
        return record

    entities_manager.get_entity_type_record = get_templated_type  # type: ignore[method-assign]
    manager = manager_factory(entities_manager=entities_manager)

    result = manager.execute_tool_for_actor(
        recruiter_actor,
        ToolExecutionRequest(
            tool_name="get_form_schema",
            arguments={"entity_type": "ATS.Candidate"},
        ),
    )

    identifier = next(field for field in result.output["fields"] if field["id"] == "identifier")
    assert identifier["required"] is False
    assert identifier["generated"] is True


def test_execute_get_picklist_values_reads_options_from_form_definitions(tools_manager, recruiter_actor) -> None:
    result = tools_manager.execute_tool_for_actor(
        recruiter_actor,
        ToolExecutionRequest(
            tool_name="get_picklist_values",
            arguments={"picklist_id": "candidate_source"},
        ),
    )

    assert result.success is True
    assert result.execution_backend == "platform_runtime"
    assert result.output["picklist_id"] == "candidate_source"
    assert result.output["options"] == ["Referral", "Website"]


def test_execute_list_events_filters_modular_calendar_events_by_entity(tools_manager, recruiter_actor) -> None:
    result = tools_manager.execute_tool_for_actor(
        recruiter_actor,
        ToolExecutionRequest(
            tool_name="list_events",
            arguments={"entity_id": "entity-1"},
        ),
    )

    assert result.success is True
    assert result.execution_backend == "platform_runtime"
    assert result.output["count"] == 1
    assert result.output["events"][0]["entity_id"] == "entity-1"


def test_execute_calendar_invite_uses_modular_handler(tools_manager, recruiter_actor, integrations_manager) -> None:
    result = tools_manager.execute_tool_for_actor(
        recruiter_actor,
        ToolExecutionRequest(
            tool_name="send_calendar_invite",
            arguments={
                "title": "Interview",
                "starts_at": "2026-03-20T10:00:00Z",
                "ends_at": "2026-03-20T11:00:00Z",
                "attendees": ["candidate@example.com"],
            },
        ),
    )

    assert result.success is True
    assert result.execution_backend == "modular"
    assert result.output["event_id"] == "evt-1"
    assert integrations_manager.last_payload is not None
    assert integrations_manager.last_payload["title"] == "Interview"


def test_execute_tool_persists_failure_log_for_platform_runtime_errors(
    tools_manager,
    recruiter_actor,
    monkeypatch,
) -> None:
    def _execute_platform_tool(
        tool_name: str,
        arguments: dict[str, object],
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        _ = tool_name, arguments, context
        raise ServiceError("platform runtime failed")

    monkeypatch.setattr(tools_manager, "_execute_platform_tool", _execute_platform_tool)

    with pytest.raises(ServiceError, match="platform runtime failed"):
        tools_manager.execute_tool_for_actor(
            recruiter_actor,
            ToolExecutionRequest(
                tool_name="read_document",
                arguments={"storage_key": "documents/resume.pdf"},
            ),
        )

    history = tools_manager.list_executions_for_actor(recruiter_actor, ToolExecutionLogListRequest())
    assert history.total == 1
    assert history.items[0].tool_name == "read_document"
    assert history.items[0].success is False
    assert history.items[0].execution_backend == "platform_runtime"
    assert history.items[0].error == "platform runtime failed"


def test_execute_tool_infers_entity_scope_from_supported_platform_runtime_arguments(
    tools_manager,
    recruiter_actor,
) -> None:
    event_result = tools_manager.execute_tool_for_actor(
        recruiter_actor,
        ToolExecutionRequest(
            tool_name="list_events",
            arguments={"entity_id": "entity-1"},
        ),
    )
    event_log = tools_manager.get_execution_for_actor(recruiter_actor, event_result.execution_id)
    assert event_log.entity_id == "entity-1"

    schema_result = tools_manager.execute_tool_for_actor(
        recruiter_actor,
        ToolExecutionRequest(
            tool_name="get_form_schema",
            arguments={"entity_type": "ATS.Candidate"},
        ),
    )
    schema_log = tools_manager.get_execution_for_actor(recruiter_actor, schema_result.execution_id)
    assert schema_log.entity_type == "ATS.Candidate"


def test_execute_tool_raises_clear_error_for_unsupported_platform_runtime_tool(
    tools_manager,
    recruiter_actor,
) -> None:
    with pytest.raises(ValidationError, match="Tool is not available in modular backend"):
        tools_manager.execute_tool_for_actor(
            recruiter_actor,
            ToolExecutionRequest(
                tool_name="get_entity",
                arguments={"entity_id": "entity-1"},
            ),
        )


def test_execution_history_is_scoped_by_actor_organization(tools_manager, admin_actor) -> None:
    tools_manager.db_model_service.create_execution_log(
        {
            "organization_id": "org-2",
            "source": "mcp",
            "tool_name": "read_document",
            "arguments": {},
            "result": {},
            "success": True,
            "execution_backend": "platform_runtime",
        }
    )

    history = tools_manager.list_executions_for_actor(admin_actor, ToolExecutionLogListRequest())
    assert history.total == 0


def test_execute_create_entity_routes_through_actor_path(manager_factory, recruiter_actor) -> None:
    entities = StubEntitiesManager()
    manager = manager_factory(entities_manager=entities)

    result = manager.execute_tool_for_actor(
        recruiter_actor,
        ToolExecutionRequest(
            tool_name="create_entity",
            arguments={"entity_type_id": "et-application", "data": {"name": "Acme"}},
        ),
    )

    assert result.success is True
    assert result.execution_backend == "modular"
    # No "identifier" was supplied, so it's backfilled from "name" (see the
    # identifier-fallback tests below) — the agent never has to know that field exists.
    assert result.output["data"] == {"name": "Acme", "identifier": "Acme"}
    assert result.output["owner_id"] == "recruiter-user"
    # Must use the actor-facing path (uniqueness/RBAC), not the system-level create.
    assert entities.create_for_actor_called is True
    # The agent/user roles are threaded through so the entity RBAC can apply.
    assert entities.last_actor["roles"] == ["recruiter"]


def test_execute_create_entity_does_not_require_reference_sources(manager_factory, recruiter_actor) -> None:
    # A document-created entity must not hard-fail when its type has a required
    # REFERENCE relation and no source is available (STAT-356). The tool opts out
    # of the required-reference check and forwards any source ids the agent supplies.
    entities = StubEntitiesManager()
    manager = manager_factory(entities_manager=entities)

    manager.execute_tool_for_actor(
        recruiter_actor,
        ToolExecutionRequest(
            tool_name="create_entity",
            arguments={
                "entity_type_id": "et-application",
                "data": {"name": "Acme"},
                "source_entity_ids": ["prov-1"],
            },
        ),
    )

    assert entities.last_require_reference_sources is False
    assert entities.last_create_request.source_entity_ids == ["prov-1"]


def test_execute_create_entity_backfills_identifier_from_full_name(manager_factory, recruiter_actor) -> None:
    # An agent extracting a resume has no reason to know the platform's implicit
    # "identifier" field exists — it must not fail just because the field was omitted.
    entities = StubEntitiesManager()
    manager = manager_factory(entities_manager=entities)

    result = manager.execute_tool_for_actor(
        recruiter_actor,
        ToolExecutionRequest(
            tool_name="create_entity",
            arguments={
                "entity_type_id": "et-application",
                "data": {"full_name": "Aparna Khatri", "email": "aparna@example.com"},
            },
        ),
    )

    assert result.success is True
    assert result.output["data"]["identifier"] == "Aparna Khatri"


def test_execute_create_entity_does_not_override_explicit_identifier(manager_factory, recruiter_actor) -> None:
    entities = StubEntitiesManager()
    manager = manager_factory(entities_manager=entities)

    result = manager.execute_tool_for_actor(
        recruiter_actor,
        ToolExecutionRequest(
            tool_name="create_entity",
            arguments={
                "entity_type_id": "et-application",
                "data": {"identifier": "Custom Id", "full_name": "Aparna Khatri"},
            },
        ),
    )

    assert result.output["data"]["identifier"] == "Custom Id"


def test_execute_create_entity_rejects_duplicate_identifier(manager_factory, recruiter_actor) -> None:
    entities = StubEntitiesManager()
    entities.seed_record(
        EntityRecordResponse(
            entity_id="entity-1",
            organization_id="org-1",
            entity_type_id="et-application",
            data={"external_id": "DUP"},
        )
    )
    manager = manager_factory(entities_manager=entities)

    with pytest.raises(ValidationError, match="already exists"):
        manager.execute_tool_for_actor(
            recruiter_actor,
            ToolExecutionRequest(
                tool_name="create_entity",
                arguments={"entity_type_id": "et-application", "data": {"external_id": "DUP"}},
            ),
        )


def test_execute_create_entity_requires_entity_type(manager_factory, recruiter_actor) -> None:
    manager = manager_factory(entities_manager=StubEntitiesManager())

    with pytest.raises(ValidationError, match="entity_type_id is required"):
        manager.execute_tool_for_actor(
            recruiter_actor,
            ToolExecutionRequest(tool_name="create_entity", arguments={"data": {}}),
        )


def test_execute_create_entity_resolves_entity_type_by_name(manager_factory, recruiter_actor) -> None:
    # The model passes a human name ("application") instead of the stored id;
    # it must resolve to the real entity_type_id ("et-application") and succeed.
    entities = StubEntitiesManager()
    manager = manager_factory(entities_manager=entities)

    result = manager.execute_tool_for_actor(
        recruiter_actor,
        ToolExecutionRequest(
            tool_name="create_entity",
            arguments={"entity_type_id": "application", "data": {"name": "Acme"}},
        ),
    )

    assert result.success is True
    assert result.output["entity_type_id"] == "et-application"
    assert entities.create_for_actor_called is True


def test_execute_create_entity_unknown_type_lists_available(manager_factory, recruiter_actor) -> None:
    manager = manager_factory(entities_manager=StubEntitiesManager())

    with pytest.raises(ValidationError, match="was not found"):
        manager.execute_tool_for_actor(
            recruiter_actor,
            ToolExecutionRequest(
                tool_name="create_entity",
                arguments={"entity_type_id": "does_not_exist", "data": {"name": "x"}},
            ),
        )


def test_render_stat_tile_resolves_entity_type_name_in_filter(manager_factory, recruiter_actor) -> None:
    # entity_type_id passed as a name must resolve to the real id so the count
    # isn't silently filtered to zero by an unmatched id.
    dashboard = StubDashboardServiceManager()
    manager = manager_factory(entities_manager=StubEntitiesManager(), dashboard_service_manager=dashboard)

    manager.execute_tool_for_actor(
        recruiter_actor,
        ToolExecutionRequest(
            tool_name="render_ui_component",
            arguments={"component_id": "stat_tile", "metric": "entities.count", "entity_type_id": "application"},
        ),
    )
    assert dashboard.last_filters["entity_type_id"] == "et-application"


def test_render_stat_tile_drops_unresolvable_entity_type_filter(manager_factory, recruiter_actor) -> None:
    dashboard = StubDashboardServiceManager()
    manager = manager_factory(entities_manager=StubEntitiesManager(), dashboard_service_manager=dashboard)

    manager.execute_tool_for_actor(
        recruiter_actor,
        ToolExecutionRequest(
            tool_name="render_ui_component",
            arguments={"component_id": "stat_tile", "metric": "entities.count", "entity_type_id": "bogus"},
        ),
    )
    # Unresolvable id is dropped (count all) rather than filtering to 0.
    assert "entity_type_id" not in dashboard.last_filters


def test_execute_enroll_entity_in_workflow_routes_through_workflow_manager(
    manager_factory,
    recruiter_actor,
) -> None:
    workflow = StubWorkflowManager()
    manager = manager_factory(workflow_service_manager=workflow)

    result = manager.execute_tool_for_actor(
        recruiter_actor,
        ToolExecutionRequest(
            tool_name="enroll_entity_in_workflow",
            arguments={
                "entity_id": "entity-1",
                "machine_name": "workflow_m4vsvyi9_6c51sk",
            },
        ),
    )

    assert result.success is True
    assert result.execution_backend == "modular"
    assert result.output["entity_id"] == "entity-1"
    assert result.output["machine_name"] == "workflow_m4vsvyi9_6c51sk"
    assert result.output["current_state"] == "INITIAL"
    assert workflow.last_actor["roles"] == ["recruiter"]
    assert workflow.last_machine_name == "workflow_m4vsvyi9_6c51sk"
    assert workflow.last_entity_id == "entity-1"


def test_execute_enroll_entity_in_workflow_requires_machine_name(
    manager_factory,
    recruiter_actor,
) -> None:
    manager = manager_factory(workflow_service_manager=StubWorkflowManager())

    with pytest.raises(ValidationError, match="machine_name is required"):
        manager.execute_tool_for_actor(
            recruiter_actor,
            ToolExecutionRequest(
                tool_name="enroll_entity_in_workflow",
                arguments={"entity_id": "entity-1"},
            ),
        )


def test_execute_enroll_resolves_workflow_display_name(manager_factory, recruiter_actor) -> None:
    # The model passes the workflow's display name ("Candidate Pipeline") instead
    # of its machine_name; enroll must resolve it (via list) and use the real
    # machine_name, so the entity actually lands on the board.
    workflow = StubWorkflowManager()
    real = "workflow_m4vsvyi9_6c51sk"

    def only_real(actor, machine_name):  # noqa: ANN001, ANN202
        if machine_name != real:
            raise NotFoundError("unknown machine_name")
        return workflow._stub_state_machine_record(actor, real)

    workflow.get_active_state_machine_for_actor = only_real  # type: ignore[method-assign]

    result = manager_factory(workflow_service_manager=workflow).execute_tool_for_actor(
        recruiter_actor,
        ToolExecutionRequest(
            tool_name="enroll_entity_in_workflow",
            arguments={"entity_id": "entity-1", "machine_name": "Candidate Pipeline"},
        ),
    )

    assert result.success is True
    assert result.output["machine_name"] == real
    assert workflow.last_machine_name == real


def test_move_entity_to_state_runs_matching_transition(manager_factory, recruiter_actor) -> None:
    workflow = StubWorkflowManager()
    manager = manager_factory(workflow_service_manager=workflow)

    result = manager.execute_tool_for_actor(
        recruiter_actor,
        ToolExecutionRequest(
            tool_name="move_entity_to_state",
            arguments={"entity_id": "entity-1", "target_state": "screening"},
        ),
    )

    assert result.success is True
    assert result.output["changed"] is True
    assert result.output["to_state"] == "SCREENING"
    assert workflow.last_trigger == "to_screening"


def test_move_entity_to_state_noop_when_already_there(manager_factory, recruiter_actor) -> None:
    manager = manager_factory(workflow_service_manager=StubWorkflowManager())

    result = manager.execute_tool_for_actor(
        recruiter_actor,
        ToolExecutionRequest(
            tool_name="move_entity_to_state",
            arguments={"entity_id": "entity-1", "target_state": "INITIAL"},
        ),
    )

    assert result.success is True
    assert result.output["changed"] is False


def test_move_entity_to_state_blocked_transition_explains(manager_factory, recruiter_actor) -> None:
    manager = manager_factory(workflow_service_manager=StubWorkflowManager())

    with pytest.raises(ValidationError, match="needs approval"):
        manager.execute_tool_for_actor(
            recruiter_actor,
            ToolExecutionRequest(
                tool_name="move_entity_to_state",
                arguments={"entity_id": "entity-1", "target_state": "HIRED"},
            ),
        )


def test_move_entity_to_state_unreachable_lists_states(manager_factory, recruiter_actor) -> None:
    manager = manager_factory(workflow_service_manager=StubWorkflowManager())

    with pytest.raises(ValidationError, match="Reachable states"):
        manager.execute_tool_for_actor(
            recruiter_actor,
            ToolExecutionRequest(
                tool_name="move_entity_to_state",
                arguments={"entity_id": "entity-1", "target_state": "OFFER"},
            ),
        )


def test_execute_list_workflows_returns_published_workflows(
    manager_factory,
    recruiter_actor,
) -> None:
    workflow = StubWorkflowManager()
    manager = manager_factory(workflow_service_manager=workflow)

    result = manager.execute_tool_for_actor(
        recruiter_actor,
        ToolExecutionRequest(tool_name="list_workflows", arguments={}),
    )

    assert result.success is True
    assert result.execution_backend == "modular"
    assert result.output["count"] == 1
    assert result.output["workflows"][0]["machine_name"] == "workflow_m4vsvyi9_6c51sk"
    assert result.output["workflows"][0]["entity_type"] == "ATS.Candidate"


def test_execute_render_ui_component_pipeline_board_returns_workflow_id_and_summary(
    manager_factory,
    recruiter_actor,
) -> None:
    workflow = StubWorkflowManager()
    manager = manager_factory(workflow_service_manager=workflow)

    result = manager.execute_tool_for_actor(
        recruiter_actor,
        ToolExecutionRequest(
            tool_name="render_ui_component",
            arguments={"component_id": "pipeline_board", "machine_name": "workflow_m4vsvyi9_6c51sk"},
        ),
    )

    assert result.success is True
    render = result.output["__render__"]
    assert render["component"] == "pipeline_board"
    # The board self-fetches on the frontend by workflowId; the tool returns only
    # the id + view + a citable summary, never serialized entity rows.
    assert render["props"]["workflowId"] == "workflow-row-1"
    assert render["props"]["view"] == "kanban"
    assert render["props"]["summary"]["total"] == 1
    assert render["props"]["summary"]["machine_name"] == "workflow_m4vsvyi9_6c51sk"
    assert "entities" not in render["props"]
    assert workflow.last_machine_name == "workflow_m4vsvyi9_6c51sk"


def test_pipeline_board_summary_carries_citable_rows_with_names(
    manager_factory,
    recruiter_actor,
) -> None:
    """The model needs the rows, the widget does not.

    The board returned counts only, so "show the board and the assignee names"
    left the model with nothing to read. Rows go under `summary`, not props.
    """
    manager = manager_factory(workflow_service_manager=StubWorkflowManager())

    result = manager.execute_tool_for_actor(
        recruiter_actor,
        ToolExecutionRequest(
            tool_name="render_ui_component",
            arguments={"component_id": "pipeline_board", "machine_name": "workflow_m4vsvyi9_6c51sk"},
        ),
    )

    summary = result.output["__render__"]["props"]["summary"]
    assert summary["rows"] == [
        {
            "entity_id": "entity-1",
            "display_name": "Dhiraj Nambiar",
            "current_state": "INITIAL",
            "owner_name": "Vinay Kumar",
            "assignee_name": "Priya Sharma",
        }
    ]
    assert summary["rows_truncated"] is False
    # Still not render props: the widget self-fetches by workflowId.
    assert "entities" not in result.output["__render__"]["props"]


def test_execute_render_ui_component_pipeline_list_and_calendar_views(
    manager_factory,
    recruiter_actor,
) -> None:
    manager = manager_factory(workflow_service_manager=StubWorkflowManager())

    for component_id, expected_view in (("pipeline_list", "list"), ("pipeline_calendar", "calendar")):
        result = manager.execute_tool_for_actor(
            recruiter_actor,
            ToolExecutionRequest(
                tool_name="render_ui_component",
                arguments={"component_id": component_id, "machine_name": "workflow_m4vsvyi9_6c51sk"},
            ),
        )
        render = result.output["__render__"]
        assert render["component"] == component_id
        assert render["props"]["view"] == expected_view
        assert render["props"]["workflowId"] == "workflow-row-1"


def test_execute_render_ui_component_entity_table_filters_by_state(
    manager_factory,
    recruiter_actor,
) -> None:
    workflow = StubWorkflowManager()
    manager = manager_factory(workflow_service_manager=workflow)

    result = manager.execute_tool_for_actor(
        recruiter_actor,
        ToolExecutionRequest(
            tool_name="render_ui_component",
            arguments={
                "component_id": "entity_table",
                "machine_name": "workflow_m4vsvyi9_6c51sk",
                "state": "SCREENING",
            },
        ),
    )

    render = result.output["__render__"]
    assert render["component"] == "entity_table"
    assert render["props"]["entities"][0]["current_state"] == "SCREENING"
    assert render["props"]["workflowId"] == "workflow-row-1"
    assert render["props"]["entityType"] == "ATS.Candidate"
    assert workflow.last_current_state == "SCREENING"


def test_execute_render_ui_component_dashboard_widget_builds_def_and_data(
    manager_factory,
    recruiter_actor,
) -> None:
    dashboard = StubDashboardServiceManager()
    manager = manager_factory(dashboard_service_manager=dashboard)

    result = manager.execute_tool_for_actor(
        recruiter_actor,
        ToolExecutionRequest(
            tool_name="render_ui_component",
            arguments={"component_id": "dashboard_widget", "metric": "pipeline.by_state"},
        ),
    )

    render = result.output["__render__"]
    assert render["component"] == "dashboard_widget"
    # def derived from the real metric registry (series output -> chart)
    assert render["props"]["def"]["type"] == "chart"
    assert render["props"]["def"]["metric"] == "pipeline.by_state"
    # data comes only from get_data_for_actor (never model-authored)
    assert render["props"]["data"] == {"kind": "scalar", "value": 42, "prevValue": 30}
    assert dashboard.last_items[0].metric == "pipeline.by_state"


def test_execute_render_ui_component_dashboard_widget_rejects_unknown_metric(
    manager_factory,
    recruiter_actor,
) -> None:
    manager = manager_factory(dashboard_service_manager=StubDashboardServiceManager())

    with pytest.raises(ValidationError, match="Unknown metric"):
        manager.execute_tool_for_actor(
            recruiter_actor,
            ToolExecutionRequest(
                tool_name="render_ui_component",
                arguments={"component_id": "dashboard_widget", "metric": "not_a_real_metric"},
            ),
        )


def test_execute_render_ui_component_full_dashboard(
    manager_factory,
    recruiter_actor,
) -> None:
    dashboard = StubDashboardServiceManager()
    manager = manager_factory(dashboard_service_manager=dashboard)

    result = manager.execute_tool_for_actor(
        recruiter_actor,
        ToolExecutionRequest(
            tool_name="render_ui_component",
            arguments={"component_id": "dashboard"},
        ),
    )

    render = result.output["__render__"]
    assert render["component"] == "dashboard"
    widgets = render["props"]["widgets"]
    assert len(widgets) == 2
    by_id = {w["def"]["id"]: w for w in widgets}
    # metric widget gets computed data; embedded widget (no metric) has data None
    assert by_id["w-count"]["data"] == {"kind": "scalar", "value": 42, "prevValue": 30}
    assert by_id["w-board"]["data"] is None


def test_execute_render_ui_component_requires_machine_name(
    manager_factory,
    recruiter_actor,
) -> None:
    manager = manager_factory(workflow_service_manager=StubWorkflowManager())

    with pytest.raises(ValidationError, match="machine_name is required"):
        manager.execute_tool_for_actor(
            recruiter_actor,
            ToolExecutionRequest(
                tool_name="render_ui_component",
                arguments={"component_id": "pipeline_board"},
            ),
        )


def test_execute_render_ui_component_stat_tile_routes_through_dashboard_manager(
    manager_factory,
    recruiter_actor,
) -> None:
    dashboard = StubDashboardServiceManager()
    manager = manager_factory(dashboard_service_manager=dashboard)

    result = manager.execute_tool_for_actor(
        recruiter_actor,
        ToolExecutionRequest(
            tool_name="render_ui_component",
            arguments={"component_id": "stat_tile", "metric": "entities.count"},
        ),
    )

    render = result.output["__render__"]
    assert render["component"] == "stat_tile"
    assert render["props"]["value"] == 42
    assert render["props"]["prevValue"] == 30
    assert dashboard.last_metric_key == "entities.count"
    assert dashboard.last_organization_id == "org-1"


def test_execute_render_ui_component_rejects_unsupported_metric(
    manager_factory,
    recruiter_actor,
) -> None:
    manager = manager_factory(dashboard_service_manager=StubDashboardServiceManager())

    with pytest.raises(ValidationError, match="Unsupported metric"):
        manager.execute_tool_for_actor(
            recruiter_actor,
            ToolExecutionRequest(
                tool_name="render_ui_component",
                arguments={"component_id": "stat_tile", "metric": "not_a_real_metric"},
            ),
        )


def test_execute_render_ui_component_rejects_unsupported_component_id(
    manager_factory,
    recruiter_actor,
) -> None:
    manager = manager_factory()

    with pytest.raises(ValidationError, match="Unsupported component_id"):
        manager.execute_tool_for_actor(
            recruiter_actor,
            ToolExecutionRequest(
                tool_name="render_ui_component",
                arguments={"component_id": "not_a_real_component"},
            ),
        )


@pytest.mark.parametrize(
    "metric,expected_type",
    [
        ("entities.count", "stat"),       # scalar
        ("sla.compliance", "gauge"),      # gauge
        ("events.recent", "table"),       # rows
        ("events.activity", "activity"),  # rows (special-cased)
        ("pipeline.by_state", "chart"),   # series
        ("incidents.trend", "chart"),     # multiseries
    ],
)
def test_widget_def_for_metric_maps_every_output_kind(metric: str, expected_type: str) -> None:
    from tools.manager import ToolsServiceManager

    widget_def = ToolsServiceManager._widget_def_for_metric(metric, None, None, None)
    assert widget_def["type"] == expected_type
    assert widget_def["metric"] == metric
    assert widget_def["viz"] in ToolsServiceManager._VALID_WIDGET_VIZ
    assert widget_def["id"] == f"agent-{metric}"


def test_widget_def_for_metric_honors_requested_viz_title_subtitle() -> None:
    from tools.manager import ToolsServiceManager

    widget_def = ToolsServiceManager._widget_def_for_metric("pipeline.by_state", "pie", "My Title", "My sub")
    assert widget_def["viz"] == "pie"
    assert widget_def["title"] == "My Title"
    assert widget_def["subtitle"] == "My sub"

    # An invalid viz falls back to the metric's default visual, not the bad value.
    fallback = ToolsServiceManager._widget_def_for_metric("pipeline.by_state", "not_a_viz", None, None)
    assert fallback["viz"] in ToolsServiceManager._VALID_WIDGET_VIZ
    assert fallback["viz"] != "not_a_viz"


def test_execute_update_entity_merges_partial_data(manager_factory, recruiter_actor) -> None:
    entities = StubEntitiesManager()
    entities.seed_record(
        EntityRecordResponse(
            entity_id="entity-1",
            organization_id="org-1",
            entity_type_id="et-application",
            data={"name": "Acme", "stage": "applied", "external_id": "E1"},
        )
    )
    manager = manager_factory(entities_manager=entities)

    result = manager.execute_tool_for_actor(
        recruiter_actor,
        ToolExecutionRequest(
            tool_name="update_entity",
            arguments={"entity_id": "entity-1", "data": {"stage": "screening"}},
        ),
    )

    assert result.success is True
    assert entities.update_for_actor_called is True
    # Partial update must MERGE: sibling fields survive, only "stage" changes.
    assert result.output["data"] == {"name": "Acme", "stage": "screening", "external_id": "E1"}


def test_execute_update_entity_missing_record_raises_not_found(manager_factory, recruiter_actor) -> None:
    manager = manager_factory(entities_manager=StubEntitiesManager())

    with pytest.raises(NotFoundError, match="entity not found"):
        manager.execute_tool_for_actor(
            recruiter_actor,
            ToolExecutionRequest(
                tool_name="update_entity",
                arguments={"entity_id": "missing", "data": {}},
            ),
        )


def test_execute_delete_entity_archives_record(manager_factory, recruiter_actor) -> None:
    entities = StubEntitiesManager()
    entities.seed_record(
        EntityRecordResponse(
            entity_id="entity-1",
            organization_id="org-1",
            entity_type_id="et-application",
            data={"name": "Acme"},
        )
    )
    manager = manager_factory(entities_manager=entities)

    result = manager.execute_tool_for_actor(
        recruiter_actor,
        ToolExecutionRequest(tool_name="delete_entity", arguments={"entity_id": "entity-1"}),
    )

    assert result.success is True
    assert result.execution_backend == "modular"
    assert result.output["entity_id"] == "entity-1"
    assert result.output["archived_at"] is not None
    assert entities.archive_for_actor_called is True


def test_execute_delete_entity_missing_record_raises_not_found(manager_factory, recruiter_actor) -> None:
    manager = manager_factory(entities_manager=StubEntitiesManager())

    with pytest.raises(NotFoundError, match="entity not found"):
        manager.execute_tool_for_actor(
            recruiter_actor,
            ToolExecutionRequest(tool_name="delete_entity", arguments={"entity_id": "missing"}),
        )


def test_entity_crud_tools_are_mcp_exposed_and_mutating(tools_manager) -> None:
    catalog = {tool.name: tool for tool in tools_manager.get_catalog().tools}
    for tool_name in ("create_entity", "update_entity", "delete_entity"):
        assert tool_name in catalog, f"{tool_name} should be exposed in the catalog"
        assert catalog[tool_name].mcp_exposed is True
        assert catalog[tool_name].is_mutating is True


def test_run_schedule_now_is_mcp_exposed_and_mutating(tools_manager) -> None:
    catalog = {tool.name: tool for tool in tools_manager.get_catalog().tools}

    assert catalog["run_schedule_now"].mcp_exposed is True
    assert catalog["run_schedule_now"].default_enabled is False
    assert catalog["run_schedule_now"].is_mutating is True
    assert catalog["run_schedule_now"].parameters["required"] == [
        "schedule_id",
        "invocation_id",
    ]


# --- FT-0135: date windows and state names on metric-backed components ---


def _stat_tile(manager, actor, **arguments):
    """Run render_ui_component for a stat_tile with the given arguments."""
    return manager.execute_tool_for_actor(
        actor,
        ToolExecutionRequest(
            tool_name="render_ui_component",
            arguments={"component_id": "stat_tile", **arguments},
        ),
    )


def test_stat_tile_passes_the_requested_time_window_to_the_metric(
    manager_factory, recruiter_actor
) -> None:
    """A date range asked for on a stat_tile must reach the query.

    stat_tile built its own filter dict and never read `filters`, so "how many
    in the last 7 days" was answered with an all-time count and no warning.
    """
    dashboard = StubDashboardServiceManager()
    manager = manager_factory(
        entities_manager=StubEntitiesManager(), dashboard_service_manager=dashboard
    )

    _stat_tile(
        manager,
        recruiter_actor,
        metric="entities.count",
        filters={"time_range": "last_7d"},
    )

    assert dashboard.last_filters["time_range"] == "last_7d"


def test_stat_tile_passes_a_custom_date_range_to_the_metric(
    manager_factory, recruiter_actor
) -> None:
    """Windows with no preset ("the last 5 days") travel as date_from/date_to."""
    dashboard = StubDashboardServiceManager()
    manager = manager_factory(
        entities_manager=StubEntitiesManager(), dashboard_service_manager=dashboard
    )

    _stat_tile(
        manager,
        recruiter_actor,
        metric="entities.count",
        filters={"date_from": "2026-09-01", "date_to": "2026-09-05"},
    )

    assert dashboard.last_filters["date_from"] == "2026-09-01"
    assert dashboard.last_filters["date_to"] == "2026-09-05"


def test_stat_tile_scopes_the_metric_to_a_named_workflow(
    manager_factory, recruiter_actor
) -> None:
    """machine_name on a stat_tile becomes a workflow_id filter.

    Without it, "moved to HIRED" counted that state across every workflow.
    """
    dashboard = StubDashboardServiceManager()
    manager = manager_factory(
        workflow_service_manager=StubWorkflowManager(),
        dashboard_service_manager=dashboard,
    )

    _stat_tile(
        manager,
        recruiter_actor,
        metric="entities.reached_state",
        state="HIRED",
        machine_name="workflow_m4vsvyi9_6c51sk",
    )

    assert dashboard.last_filters["workflow_id"] == "workflow-row-1"


def test_stat_tile_corrects_the_casing_of_a_requested_state(
    manager_factory, recruiter_actor
) -> None:
    """"hired" must become "HIRED" rather than matching nothing.

    States are compared exactly in SQL and are mixed case in real data, so a
    guessed name silently counted zero.
    """
    dashboard = StubDashboardServiceManager()
    manager = manager_factory(dashboard_service_manager=dashboard)

    _stat_tile(manager, recruiter_actor, metric="entities.reached_state", state="hired")

    assert dashboard.last_filters["state"] == "HIRED"


def test_stat_tile_rejects_a_state_that_does_not_exist(
    manager_factory, recruiter_actor
) -> None:
    """An unknown state errors and names the real ones, instead of counting 0."""
    manager = manager_factory(dashboard_service_manager=StubDashboardServiceManager())

    with pytest.raises(ValidationError) as excinfo:
        _stat_tile(manager, recruiter_actor, metric="entities.reached_state", state="Done")

    message = str(excinfo.value)
    assert "Done" in message
    assert "HIRED" in message


def test_state_counting_metrics_require_a_state(manager_factory, recruiter_actor) -> None:
    """reached_state with no state returns 0 downstream, which reads as an answer."""
    manager = manager_factory(dashboard_service_manager=StubDashboardServiceManager())

    with pytest.raises(ValidationError):
        _stat_tile(manager, recruiter_actor, metric="entities.reached_state")


def test_dashboard_widget_surfaces_a_failed_metric_as_an_error(
    manager_factory, recruiter_actor
) -> None:
    """The dashboard degrades a broken widget to an error payload; a tool must not.

    Handing that payload back as props let the model narrate a chart that had
    actually failed.
    """
    dashboard = StubDashboardServiceManager()
    dashboard.widget_data = {"kind": "error", "error": "Unsupported time_range 'last 5 days'"}
    manager = manager_factory(dashboard_service_manager=dashboard)

    with pytest.raises(ValidationError) as excinfo:
        manager.execute_tool_for_actor(
            recruiter_actor,
            ToolExecutionRequest(
                tool_name="render_ui_component",
                arguments={
                    "component_id": "dashboard_widget",
                    "metric": "entities.count",
                    "filters": {"time_range": "last 5 days"},
                },
            ),
        )

    assert "last 5 days" in str(excinfo.value)


def test_list_workflows_reports_each_workflow_state_name(
    manager_factory, recruiter_actor
) -> None:
    """The model can only pass an exact state if it can read the real names."""
    manager = manager_factory(workflow_service_manager=StubWorkflowManager())

    result = manager.execute_tool_for_actor(
        recruiter_actor, ToolExecutionRequest(tool_name="list_workflows", arguments={})
    )

    assert result.output["workflows"][0]["states"] == ["INITIAL", "SCREENING", "HIRED"]


def test_stat_tile_accepts_the_time_window_as_a_top_level_argument(
    manager_factory, recruiter_actor
) -> None:
    """time_range must work outside `filters` too.

    `state` is a top-level argument, so the model generalizes and passes
    time_range there as well. Reading it only from `filters` dropped the window
    and answered an all-time number. Caught against the real agent, not a stub.
    """
    dashboard = StubDashboardServiceManager()
    manager = manager_factory(
        entities_manager=StubEntitiesManager(), dashboard_service_manager=dashboard
    )

    _stat_tile(manager, recruiter_actor, metric="entities.count", time_range="last_7d")

    assert dashboard.last_filters["time_range"] == "last_7d"


def test_stat_tile_rejects_a_state_that_matches_more_than_one(
    manager_factory, recruiter_actor
) -> None:
    """Two states differing only in case must not be resolved by picking one.

    Guessing here would answer about the wrong state while looking correct, so
    the ambiguity is reported and both candidates are named.
    """
    dashboard = StubDashboardServiceManager()
    dashboard.STATES = ("Done", "DONE", "INITIAL")
    manager = manager_factory(dashboard_service_manager=dashboard)

    with pytest.raises(ValidationError) as excinfo:
        _stat_tile(manager, recruiter_actor, metric="entities.reached_state", state="done")

    message = str(excinfo.value)
    assert "Done" in message
    assert "DONE" in message


def test_stat_tile_accepts_workflow_id_as_a_top_level_argument(
    manager_factory, recruiter_actor
) -> None:
    """workflow_id is misplaced the same way time_range was.

    The model generalizes from `state` sitting at the top level, and a dropped
    workflow_id answers about every workflow while looking scoped.
    """
    dashboard = StubDashboardServiceManager()
    manager = manager_factory(dashboard_service_manager=dashboard)

    _stat_tile(
        manager,
        recruiter_actor,
        metric="entities.in_state",
        state="HIRED",
        workflow_id="workflow-row-1",
    )

    assert dashboard.last_filters["workflow_id"] == "workflow-row-1"


def test_stat_tile_refuses_to_run_unscoped_when_the_workflow_has_no_id(
    manager_factory, recruiter_actor
) -> None:
    """An unusable machine_name must fail, not quietly widen to every workflow.

    Scoping was asked for explicitly, so answering across all workflows would
    look like an answer about the named one.
    """
    workflow = StubWorkflowManager()
    dashboard = StubDashboardServiceManager()
    manager = manager_factory(
        workflow_service_manager=workflow, dashboard_service_manager=dashboard
    )

    class _IdlessWorkflow:
        id = None
        machine_name = "workflow_m4vsvyi9_6c51sk"

    workflow.get_active_state_machine_for_actor = (
        lambda actor, machine_name: _IdlessWorkflow()  # noqa: ARG005
    )

    with pytest.raises(ServiceError):
        _stat_tile(
            manager,
            recruiter_actor,
            metric="entities.in_state",
            state="HIRED",
            machine_name="workflow_m4vsvyi9_6c51sk",
        )


def test_list_workflows_returns_one_row_per_workflow_not_per_version(
    manager_factory, recruiter_actor
) -> None:
    """Every published version shares a machine_name, so all of them read as many.

    The agent counted a metric once per version and summed the results,
    answering 8 where the true figure was 4.
    """
    workflow = StubWorkflowManager()
    manager = manager_factory(workflow_service_manager=workflow)

    result = manager.execute_tool_for_actor(
        recruiter_actor, ToolExecutionRequest(tool_name="list_workflows", arguments={})
    )

    names = [w["machine_name"] for w in result.output["workflows"]]
    assert len(names) == len(set(names))


def test_a_single_number_metric_cannot_be_rendered_as_a_chart(
    manager_factory, recruiter_actor
) -> None:
    """A scalar drawn as a bar reads as a trend and is not one.

    "Chart tickets moved to Done over time" was answered with
    entities.reached_state and viz=line, i.e. one number in a chart frame. The
    error names the metric that actually plots movement per day.
    """
    dashboard = StubDashboardServiceManager()
    manager = manager_factory(dashboard_service_manager=dashboard)

    with pytest.raises(ValidationError) as excinfo:
        manager.execute_tool_for_actor(
            recruiter_actor,
            ToolExecutionRequest(
                tool_name="render_ui_component",
                arguments={
                    "component_id": "dashboard_widget",
                    "metric": "entities.reached_state",
                    "state": "HIRED",
                    "viz": "line",
                },
            ),
        )

    assert "transitions.over_time" in str(excinfo.value)


def test_a_single_number_metric_still_renders_without_a_chart_visual(
    manager_factory, recruiter_actor
) -> None:
    """The guard must only reject the mismatch, not the ordinary scalar case."""
    dashboard = StubDashboardServiceManager()
    manager = manager_factory(dashboard_service_manager=dashboard)

    result = manager.execute_tool_for_actor(
        recruiter_actor,
        ToolExecutionRequest(
            tool_name="render_ui_component",
            arguments={
                "component_id": "dashboard_widget",
                "metric": "entities.reached_state",
                "state": "HIRED",
            },
        ),
    )

    assert result.success is True


# --- FT-0218: agent-exposed connector tool blocks on an unresolved placeholder ---


def _connector_manager(manager_factory, connector: ConnectorContract) -> ToolsServiceManager:
    """A tools manager wired with one connector, via a real ConnectorsServiceManager
    so `run_connector_call` (the function under test) runs for real."""
    return manager_factory(
        connectors_service_manager=ConnectorsServiceManager(
            StubConnectorsDbModelService({connector.id: connector}), None, None
        )
    )


def _connector_tool(
    manager: ToolsServiceManager, actor: dict, connector_id: str, **arguments: object
):
    """Run a connector exposed as an agent tool, via its real dispatch path."""
    tool_name = f"connector__{connector_id.replace('-', '').lower()}"
    return manager.execute_tool_for_actor(
        actor, ToolExecutionRequest(tool_name=tool_name, arguments=dict(arguments))
    )


def _exposed_connector(**overrides: object) -> ConnectorContract:
    base: dict[str, object] = {
        "id": "11111111-1111-1111-1111-111111111111",
        "organization_id": "org-1",
        "name": "inriver-upsert",
        "base_url": "https://example.test",
        "method": "POST",
        "path": "/entities:upsert",
        "headers": {},
        "query_params": {},
        "expose_as_tool": True,
        "entity_types": [],
    }
    base.update(overrides)
    return ConnectorContract(**base)


def test_connector_tool_blocks_on_an_input_the_agent_did_not_supply(
    manager_factory, recruiter_actor
) -> None:
    """The tool schema marks every {{input}} placeholder required; the runtime
    must actually enforce that, not silently send "" the way it used to."""
    connector = _exposed_connector(body_template={"code": "{{sku}}"})
    manager = _connector_manager(manager_factory, connector)

    result = _connector_tool(manager, recruiter_actor, connector.id)

    assert result.success is False
    assert "sku" in (result.error or "")


def test_connector_tool_fires_when_every_input_is_supplied(
    manager_factory, recruiter_actor
) -> None:
    """The strict check must not block a call the agent filled in correctly."""
    connector = _exposed_connector(body_template={"code": "{{sku}}"})
    manager = _connector_manager(manager_factory, connector)

    result = _connector_tool(manager, recruiter_actor, connector.id, sku="ABC-1")

    # Reaches the network (and fails there, since example.test resolves nowhere
    # in this sandbox) - the point is it is not blocked pre-flight.
    assert "unresolved placeholders" not in (result.error or "")


def test_render_without_a_component_id_says_which_ones_exist(
    manager_factory, recruiter_actor
) -> None:
    """A bare "unsupported" made the model drop the question instead of resending.

    It re-sent a call having lost component_id, could not tell what was wrong,
    and reported that no such data existed.
    """
    manager = manager_factory(dashboard_service_manager=StubDashboardServiceManager())

    with pytest.raises(ValidationError) as excinfo:
        manager.execute_tool_for_actor(
            recruiter_actor,
            ToolExecutionRequest(
                tool_name="render_ui_component",
                arguments={"metric": "entities.reached_state", "state": "HIRED"},
            ),
        )

    message = str(excinfo.value)
    assert "component_id is required" in message
    assert "dashboard_widget" in message


def test_a_state_missing_from_one_workflow_points_at_the_wider_search(
    manager_factory, recruiter_actor
) -> None:
    """Listing only that workflow's states invited a swap to a similar name.

    Asked about QA, the model scoped to a workflow that has none, saw REVIEW in
    the list and answered about REVIEW, which holds entirely different tickets.
    """
    workflow = StubWorkflowManager()
    dashboard = StubDashboardServiceManager()
    manager = manager_factory(
        workflow_service_manager=workflow, dashboard_service_manager=dashboard
    )

    def _scoped_options(actor, workflow_id=None):
        """The workflow lacks QA; the organization has it."""
        names = ("INITIAL", "SCREENING") if workflow_id else ("INITIAL", "SCREENING", "QA")
        return SimpleNamespace(
            states=[SimpleNamespace(value=name, label=name) for name in names]
        )

    dashboard.get_filter_options_for_actor = _scoped_options

    with pytest.raises(ValidationError) as excinfo:
        _stat_tile(
            manager,
            recruiter_actor,
            metric="entities.reached_state",
            state="QA",
            machine_name="workflow_m4vsvyi9_6c51sk",
        )

    message = str(excinfo.value)
    assert "without machine_name" in message
    assert "QA" in message
