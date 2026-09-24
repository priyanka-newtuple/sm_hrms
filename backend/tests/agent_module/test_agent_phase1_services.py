from __future__ import annotations

import sys
import types
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from agent.controller import AgentRestController
from agent.manager import AgentServiceManager
from agent.models.interface import (
    AgentExecutionContext,
    AgentSessionContext,
    AgentRuntimeSpec,
    RequestContext,
    RuntimeBackendRunRequest,
    RuntimeBackendResult,
    RuntimeContext,
)
from agent.models.request import (
    AgentConstraints,
    AgentDefinitionCreate,
    AgentDefinitionUpdate,
    AgentResumeRequest,
    AgentRunRequest,
)
from agent.services.context import AgentContextService
from agent.services.definitions import AgentDefinitionService
from agent.services.runtime import AgentRuntimeService
from agent.services.sdk_adapter import AgentsSdkRuntimeAdapterBase, OpenAIAgentsSdkRuntimeAdapter
from exceptions import NotFoundError, ServiceError, ValidationError

from .fakes import InMemoryAgentModelServiceFake, StubLlmManager


class _FakeModelSettings:
    """Stand-in for the real agents.ModelSettings — just captures kwargs."""

    def __init__(self, **kwargs) -> None:  # noqa: ANN001
        self.kwargs = kwargs


class FakeBackend:
    def __init__(
        self,
        *,
        result: RuntimeBackendResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result or RuntimeBackendResult(
            status="completed",
            output_text="phase 1 response",
            tokens_used=12,
            backend_metadata={"backend": "fake"},
        )
        self.error = error
        self.requests = []

    def run(self, request):  # noqa: ANN001
        self.requests.append(request)
        if self.error:
            raise self.error
        return self.result

    def resume(self, request):  # noqa: ANN001
        self.requests.append(request)
        if self.error:
            raise self.error
        return self.result


class FakeCapabilityResolver:
    class Registry:
        def list_enabled_capabilities(self, context, capability_ids):  # noqa: ANN001
            _ = context
            return [
                SimpleNamespace(
                    id=capability_ids[0],
                    tool_id="list_entity_types",
                    capability_key="entity.list_types",
                    description="List entity types",
                    input_schema={"type": "object", "properties": {}},
                )
            ]

    mcp_registry_service = Registry()

    def build_sdk_tools(
        self, context, tool_ids, execution_context, *, run_id, session_id, document_id=None, file_slug_map=None
    ):  # noqa: ANN001
        _ = context, execution_context, run_id, session_id, document_id, file_slug_map
        return [{"name": tool_ids[0]}]


def _context(org_id: str = "org-1") -> RequestContext:
    return RequestContext(
        organization_id=org_id,
        user_id="admin-user",
        roles=["admin"],
        request_id="req-1",
    )


def _create_definition(
    service: AgentDefinitionService,
    context: RequestContext,
    *,
    name: str = "screening_helper",
    allowed_tools: list[str] | None = None,
):
    return service.create_definition(
        context,
        AgentDefinitionCreate(
            name=name,
            display_name="Screening Helper",
            description="Reads candidate screening context.",
            system_prompt="You help recruiters understand the current context.",
            allowed_tools=allowed_tools or [],
            model_override="gpt-4.1-mini",
        ),
    )


def test_definition_service_validates_models_and_scopes_by_tenant(agent_repo_fake) -> None:
    service = AgentDefinitionService(agent_repo_fake)
    org_one = _context("org-1")
    org_two = _context("org-2")
    created = _create_definition(service, org_one)

    assert service.get_definition(org_one, created.definition_id).definition_id == created.definition_id
    with pytest.raises(NotFoundError):
        service.get_definition(org_two, created.definition_id)

    with pytest.raises(ValidationError):
        service.create_definition(
            org_one,
            AgentDefinitionCreate(
                name="bad_model",
                display_name="Bad Model",
                system_prompt="This prompt is long enough for validation.",
                model_override="bad model!",
            ),
        )

    with pytest.raises(ValidationError):
        service.create_definition(
            org_one,
            AgentDefinitionCreate(
                name="bad_tool",
                display_name="Bad Tool",
                system_prompt="This prompt is long enough for validation.",
                allowed_tools=["legacy_tool_name"],
            ),
        )

    # Provider-prefixed model identifiers (with "/") are accepted.
    for model in ("gemini/gemini-1.5-flash", "azure/gpt-4o", "bedrock/anthropic.claude-3-5-sonnet-20240620-v1:0"):
        prefixed = service.create_definition(
            org_one,
            AgentDefinitionCreate(
                name=f"prefixed_{model.split('/')[0]}",
                display_name="Prefixed Model",
                system_prompt="This prompt is long enough for validation.",
                model_override=model,
            ),
        )
        assert prefixed.model_override == model


def test_runtime_spec_uses_configured_max_iterations(agent_repo_fake) -> None:
    service = AgentDefinitionService(agent_repo_fake)
    context = _context("org-1")
    definition = service.create_definition(
        context,
        AgentDefinitionCreate(
            name="long_running_helper",
            display_name="Long Running Helper",
            system_prompt="You complete workflows that need several tool calls.",
            constraints=AgentConstraints(max_iterations=17),
        ),
    )

    spec = service.build_runtime_spec(context, definition.definition_id)

    assert spec.max_turns == 17


def _agent_mode_template():
    from agent.models.interface import AgentTemplateContract
    from agent.services.definitions import AGENT_MODE_BUILTIN_NAME

    return AgentTemplateContract(
        name=AGENT_MODE_BUILTIN_NAME,
        display_name="Agent",
        description="Built-in Agent Mode assistant.",
        system_prompt="You are the built-in Agent Mode assistant.",
        allowed_tools=None,
        is_system=True,
    )


def test_agent_mode_builtin_hidden_editable_and_all_tools(agent_repo_fake) -> None:
    from agent.services.definitions import AGENT_MODE_BUILTIN_NAME

    template = _agent_mode_template()
    service = AgentDefinitionService(agent_repo_fake, builtin_templates=[template])
    context = _context("org-1")

    # Hidden from the default list; present only when explicitly included.
    listed = service.list_definitions(context, active_only=False)
    assert all(d.name != AGENT_MODE_BUILTIN_NAME for d in listed)
    included = service.list_definitions(context, active_only=False, include_agent_mode=True)
    assert any(d.name == AGENT_MODE_BUILTIN_NAME for d in included)

    # Dedicated fetch resolves it.
    agent_mode = service.get_agent_mode_definition(context)
    assert agent_mode.name == AGENT_MODE_BUILTIN_NAME

    # Runtime spec grants all tools and carries no stored tool_ids.
    spec = service.build_runtime_spec(context, agent_mode.definition_id)
    assert spec.all_tools is True
    assert spec.tool_ids == []
    assert spec.max_turns == template.constraints.max_iterations

    # Editable like any other seeded system agent.
    updated = service.update_definition(
        context,
        agent_mode.definition_id,
        AgentDefinitionUpdate(display_name="Tuned Assistant"),
    )
    assert updated.display_name == "Tuned Assistant"

    # ...except that it must stay active.
    with pytest.raises(ValidationError):
        service.update_definition(
            context,
            agent_mode.definition_id,
            AgentDefinitionUpdate(is_active=False),
        )
    with pytest.raises(ValidationError):
        service.disable_definition(context, agent_mode.definition_id)


def test_ensure_builtin_definitions_never_overwrites_customizations(agent_repo_fake) -> None:
    """Seeding is create-if-missing; it must not resync an edited row.

    ``ensure_builtin_definitions`` runs on every definitions read, so a
    force-resync here would silently revert an admin's edit on the next request.
    """
    template = _agent_mode_template()
    service = AgentDefinitionService(agent_repo_fake, builtin_templates=[template])
    context = _context("org-1")
    agent_mode = service.get_agent_mode_definition(context)

    service.update_definition(
        context,
        agent_mode.definition_id,
        AgentDefinitionUpdate(
            display_name="Tuned Assistant",
            system_prompt="You are a tuned Agent Mode assistant.",
        ),
    )

    # Two more seeding passes, as separate reads would trigger.
    service.ensure_builtin_definitions(context)
    service.ensure_builtin_definitions(context)

    reread = service.get_agent_mode_definition(context)
    assert reread.display_name == "Tuned Assistant"
    assert reread.system_prompt == "You are a tuned Agent Mode assistant."


def test_update_allows_customizing_builtin_definition(agent_repo_fake) -> None:
    service = AgentDefinitionService(agent_repo_fake)
    context = _context("org-1")
    builtins = [d for d in service.list_definitions(context) if d.is_system]
    assert builtins, "expected at least one seeded built-in definition"

    updated = service.update_definition(
        context,
        builtins[0].definition_id,
        AgentDefinitionUpdate(model_override="gpt-5.2-chat-latest"),
    )

    assert updated.model_override == "gpt-5.2-chat-latest"
    assert updated.is_system is True  # identity flag is preserved


def test_context_service_builds_deterministic_bounded_session_context(agent_repo_fake) -> None:
    context = _context()
    definition = _create_definition(AgentDefinitionService(agent_repo_fake), context)
    session = agent_repo_fake.create_session(
        definition.definition_id,
        context.user_id or "admin-user",
        context.organization_id,
        {"source": "test"},
    )
    for index in range(12):
        agent_repo_fake.create_message(
            session_id=session.session_id,
            role="user",
            content=f"message {index}",
            tokens_used=0,
        )

    service = AgentContextService(agent_repo_fake, max_recent_messages=3)
    execution_context = service.build_context(
        context,
        session_id=session.session_id,
        request_context={"allowed_actions": ["read"]},
    )

    assert execution_context.runtime.organization_id == "org-1"
    assert execution_context.domain.allowed_actions == ["read"]
    assert execution_context.session is not None
    assert [item["content"] for item in execution_context.session.recent_messages] == [
        "message 9",
        "message 10",
        "message 11",
    ]


def test_runtime_service_persists_success_with_mocked_backend(agent_repo_fake) -> None:
    context = _context()
    capability_id = "11111111-1111-4111-8111-111111111111"
    definition_service = AgentDefinitionService(agent_repo_fake)
    definition = _create_definition(
        definition_service,
        context,
        allowed_tools=[capability_id],
    )
    runtime = AgentRuntimeService(
        agent_repo_fake,
        definition_service,
        AgentContextService(agent_repo_fake),
        FakeBackend(
            result=RuntimeBackendResult(
                status="completed",
                output_text="phase 1 response",
                tokens_used=12,
                backend_metadata={
                    "llm_requests": [
                        {
                            "api": "chat.completions",
                            "body": {
                                "model": "gpt-4.1-mini",
                                "messages": [
                                    {
                                        "role": "system",
                                        "content": "You help recruiters understand the current context.",
                                    },
                                    {"role": "user", "content": "Summarize the context"},
                                ],
                                "tools": [
                                    {
                                        "type": "function",
                                        "function": {
                                            "name": "list_entity_types",
                                            "description": "List entity types",
                                            "parameters": {
                                                "type": "object",
                                                "properties": {},
                                            },
                                        },
                                    }
                                ],
                            },
                        }
                    ],
                    "tool_calls": [
                        {
                            "tool": "list_entity_types",
                            "args": {},
                            "result": {"count": 1},
                            "success": True,
                            "duration_ms": 4,
                        }
                    ]
                },
            )
        ),
        FakeCapabilityResolver(),
    )

    run = runtime.run(
        context,
        AgentRunRequest(definition_id=definition.definition_id, input="Summarize the context"),
    )

    assert run.status == "completed"
    assert run.output_text == "phase 1 response"
    assert run.completed_at is not None
    assert agent_repo_fake.get_run(run.run_id, context.organization_id) is not None
    assert run.session_id is not None
    messages = agent_repo_fake.list_messages(run.session_id)
    assert [message.role for message in messages] == ["user", "agent"]
    assert [message.content for message in messages] == [
        "Summarize the context",
        "phase 1 response",
    ]
    assert messages[1].tool_calls == [
        {
            "tool": "list_entity_types",
            "args": {},
            "result": {"count": 1},
            "success": True,
            "duration_ms": 4,
        }
    ]
    session = agent_repo_fake.get_session(run.session_id, context.user_id, context.organization_id)
    assert session is not None
    assert session.title == "Summarize the context"
    assert session.message_count == 2
    assert session.total_tokens == 12
    trace_runs, trace_total = agent_repo_fake.list_trace_runs(
        context.organization_id,
        limit=10,
        offset=0,
        status="success",
    )
    assert trace_total == 1
    assert trace_runs[0].session_id == run.session_id
    assert trace_runs[0].input_message == "Summarize the context"
    trace_events = agent_repo_fake.list_trace_events(trace_runs[0].id)
    assert [event.kind for event in trace_events] == [
        "context",
        "llm_request",
        "user_message",
        "tool_call",
        "assistant_message",
        "run_summary",
    ]
    assert trace_events[1].payload["api"] == "chat.completions"
    assert trace_events[1].payload["body"]["messages"][1] == {
        "role": "user",
        "content": "Summarize the context",
    }
    assert trace_events[1].payload["body"]["tools"][0]["function"]["name"] == "list_entity_types"
    assert trace_events[1].payload["body"]["tools"][0]["function"]["parameters"] == {
        "type": "object",
        "properties": {},
    }
    assert trace_events[3].payload["tool"] == "list_entity_types"


def test_runtime_reuses_session_context_for_follow_up(agent_repo_fake) -> None:
    context = _context()
    definition_service = AgentDefinitionService(agent_repo_fake)
    definition = _create_definition(definition_service, context)
    backend = FakeBackend()
    runtime = AgentRuntimeService(
        agent_repo_fake,
        definition_service,
        AgentContextService(agent_repo_fake),
        backend,
    )

    first = runtime.run(
        context,
        AgentRunRequest(definition_id=definition.definition_id, input="First prompt"),
    )
    second = runtime.run(
        context,
        AgentRunRequest(
            definition_id=definition.definition_id,
            input="Follow up",
            session_id=first.session_id,
        ),
    )

    assert second.session_id == first.session_id
    follow_up_context = backend.requests[-1].execution_context
    assert follow_up_context.session is not None
    assert [message["content"] for message in follow_up_context.session.recent_messages] == [
        "First prompt",
        "phase 1 response",
    ]
    assert len(agent_repo_fake.list_messages(first.session_id)) == 4


def test_runtime_service_persists_failure_without_leaking_secret(agent_repo_fake) -> None:
    context = _context()
    definition_service = AgentDefinitionService(agent_repo_fake)
    definition = _create_definition(definition_service, context)
    runtime = AgentRuntimeService(
        agent_repo_fake,
        definition_service,
        AgentContextService(agent_repo_fake),
        FakeBackend(error=RuntimeError("api_key=secret-value")),
    )

    run = runtime.run(
        context,
        AgentRunRequest(definition_id=definition.definition_id, input="Summarize the context"),
    )

    assert run.status == "failed"
    assert run.error == "Agent execution failed due to provider configuration."
    assert run.completed_at is not None
    trace_runs, trace_total = agent_repo_fake.list_trace_runs(
        context.organization_id,
        limit=10,
        offset=0,
        status="error",
    )
    assert trace_total == 1
    trace_events = agent_repo_fake.list_trace_events(trace_runs[0].id)
    assert trace_events[-2].kind == "error"
    assert trace_events[-2].payload["message"] == run.error


def test_failed_run_does_not_persist_the_raw_error_as_an_agent_message(
    agent_repo_fake,
) -> None:
    """A failed run must not put its error in the chat.

    Stored messages are replayed to the model, so it read "Max turns (12)
    exceeded" as its own reply and made up an explanation for it.
    """
    context = _context()
    definition_service = AgentDefinitionService(agent_repo_fake)
    definition = _create_definition(definition_service, context)
    runtime = AgentRuntimeService(
        agent_repo_fake,
        definition_service,
        AgentContextService(agent_repo_fake),
        FakeBackend(error=RuntimeError("Max turns (12) exceeded")),
    )

    run = runtime.run(
        context,
        AgentRunRequest(definition_id=definition.definition_id, input="Who is assigned?"),
    )

    assert run.status == "failed"
    messages = agent_repo_fake.list_messages(run.session_id)
    agent_messages = [m for m in messages if m.role == "agent"]
    assert len(agent_messages) == 1
    content = agent_messages[0].content
    assert "Max turns" not in content
    assert content == "I wasn't able to complete that request."
    # The real error is still recorded on the run itself.
    assert run.error


def test_runtime_rejects_cross_tenant_run_access(agent_repo_fake) -> None:
    context = _context("org-1")
    definition_service = AgentDefinitionService(agent_repo_fake)
    definition = _create_definition(definition_service, context)
    runtime = AgentRuntimeService(
        agent_repo_fake,
        definition_service,
        AgentContextService(agent_repo_fake),
        FakeBackend(),
    )
    run = runtime.run(context, AgentRunRequest(definition_id=definition.definition_id, input="Run"))

    with pytest.raises(NotFoundError):
        runtime.get_run(_context("org-2"), run.run_id)


def test_cancel_run_marks_run_as_cancelled(agent_repo_fake) -> None:
    context = _context("org-1")
    definition_service = AgentDefinitionService(agent_repo_fake)
    definition = _create_definition(definition_service, context)
    runtime = AgentRuntimeService(
        agent_repo_fake,
        definition_service,
        AgentContextService(agent_repo_fake),
        FakeBackend(),
    )
    run = runtime.run(context, AgentRunRequest(definition_id=definition.definition_id, input="start"))
    # Move the run out of a terminal state so cancellation has an effect.
    agent_repo_fake.update_run(run.run_id, context.organization_id, {"status": "running"})

    cancelled = runtime.cancel_run(context, run.run_id)

    assert cancelled.status == "cancelled"
    assert cancelled.completed_at is not None


def test_resume_run_with_new_input_text(agent_repo_fake) -> None:
    context = _context("org-1")
    definition_service = AgentDefinitionService(agent_repo_fake)
    definition = _create_definition(definition_service, context)
    backend = FakeBackend(
        result=RuntimeBackendResult(status="completed", output_text="resumed output")
    )
    runtime = AgentRuntimeService(
        agent_repo_fake,
        definition_service,
        AgentContextService(agent_repo_fake),
        backend,
    )
    run = runtime.run(context, AgentRunRequest(definition_id=definition.definition_id, input="start"))
    # Put the run into a resumable state before resuming with new input.
    agent_repo_fake.update_run(
        run.run_id, context.organization_id, {"status": "waiting_for_approval"}
    )

    resumed = runtime.resume(
        context, run.run_id, AgentResumeRequest(input="continue")
    )

    assert resumed.status == "completed"
    assert resumed.output_text == "resumed output"
    resume_request = backend.requests[-1]
    assert resume_request.input_text == "continue"


def test_api_run_creation_persists_status() -> None:
    repo = InMemoryAgentModelServiceFake()
    definition = _create_definition(AgentDefinitionService(repo), _context())
    manager = AgentServiceManager(
        repo,
        database_service_manager=None,
        config=None,
        tools_service_manager=object(),
        llm_service_manager=StubLlmManager(),
    )
    manager.runtime_service.execution_backend = FakeBackend(
        result=RuntimeBackendResult(
            status="completed",
            output_text="api response",
            backend_metadata={"backend": "fake"},
        )
    )
    router = APIRouter()
    AgentRestController(manager).prepare(router)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/agent/runs",
        headers={"x-user-id": "admin-user", "x-org-id": "org-1", "x-user-roles": "admin"},
        json={"definition_id": definition.definition_id, "input": "Summarize"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "completed"
    assert body["output"] == "api response"
    persisted = repo.get_run(body["run_id"], "org-1")
    assert persisted is not None
    assert persisted.status == "completed"

    traces_response = client.get(
        "/agent-traces/sessions",
        headers={"x-user-id": "admin-user", "x-org-id": "org-1", "x-user-roles": "admin"},
    )
    assert traces_response.status_code == 200
    traces = traces_response.json()
    assert traces["total"] == 1
    assert traces["items"][0]["latest_status"] == "success"

    trace_runs_response = client.get(
        f"/agent-traces/runs?session_id={body['session_id']}",
        headers={"x-user-id": "admin-user", "x-org-id": "org-1", "x-user-roles": "admin"},
    )
    assert trace_runs_response.status_code == 200
    trace_runs = trace_runs_response.json()
    assert trace_runs["total"] == 1
    assert trace_runs["items"][0]["input_message"] == "Summarize"

    trace_detail_response = client.get(
        f"/agent-traces/runs/{trace_runs['items'][0]['id']}",
        headers={"x-user-id": "admin-user", "x-org-id": "org-1", "x-user-roles": "admin"},
    )
    assert trace_detail_response.status_code == 200
    trace_detail = trace_detail_response.json()
    assert [event["kind"] for event in trace_detail["events"]] == [
        "context",
        "user_message",
        "assistant_message",
        "run_summary",
    ]

    sessions_response = client.get(
        "/agent/sessions",
        headers={"x-user-id": "admin-user", "x-org-id": "org-1", "x-user-roles": "admin"},
    )
    assert sessions_response.status_code == 200
    sessions = sessions_response.json()
    assert len(sessions) == 1
    assert sessions[0]["message_count"] == 2

    session_response = client.get(
        f"/agent/sessions/{body['session_id']}",
        headers={"x-user-id": "admin-user", "x-org-id": "org-1", "x-user-roles": "admin"},
    )
    assert session_response.status_code == 200
    session_body = session_response.json()
    assert [message["role"] for message in session_body["messages"]] == ["user", "agent"]


def test_agent_mode_session_resolves_its_display_name() -> None:
    """An Agent Mode session must report its agent name, not null.

    ``list_sessions_for_actor`` builds its definition lookup from
    ``list_definitions``, which hides agent_mode unless explicitly included — so
    the name resolved to None and the session list rendered blank.
    """
    repo = InMemoryAgentModelServiceFake()
    template = _agent_mode_template()
    manager = AgentServiceManager(
        repo,
        database_service_manager=None,
        config=None,
        tools_service_manager=object(),
        llm_service_manager=StubLlmManager(),
        system_agent_templates=[template],
    )
    manager.runtime_service.execution_backend = FakeBackend(
        result=RuntimeBackendResult(
            status="completed",
            output_text="api response",
            backend_metadata={"backend": "fake"},
        )
    )
    router = APIRouter()
    AgentRestController(manager).prepare(router)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    headers = {"x-user-id": "admin-user", "x-org-id": "org-1", "x-user-roles": "admin"}

    agent_mode = client.get("/agent/definitions/agent-mode", headers=headers).json()
    run_response = client.post(
        "/agent/runs",
        headers=headers,
        json={"definition_id": agent_mode["definition_id"], "input": "Summarize"},
    )
    assert run_response.status_code == 201

    sessions = client.get("/agent/sessions", headers=headers).json()
    assert len(sessions) == 1
    assert sessions[0]["agent_name"] == template.display_name


def test_failed_tool_call_marks_trace_status_partial(agent_repo_fake) -> None:
    context = _context()
    definition_service = AgentDefinitionService(agent_repo_fake)
    definition = _create_definition(definition_service, context)
    runtime = AgentRuntimeService(
        agent_repo_fake,
        definition_service,
        AgentContextService(agent_repo_fake),
        FakeBackend(
            result=RuntimeBackendResult(
                status="completed",
                output_text="entity creation failed",
                backend_metadata={
                    "tool_calls": [
                        {
                            "tool": "create_entity",
                            "args": {},
                            "result": {"success": False},
                            "success": False,
                            "duration_ms": 3,
                        }
                    ]
                },
            )
        ),
        FakeCapabilityResolver(),
    )

    run = runtime.run(
        context,
        AgentRunRequest(definition_id=definition.definition_id, input="Create it"),
    )

    # The run lifecycle still completed; only the trace display status reflects the failure.
    assert run.status == "completed"
    sessions, _ = agent_repo_fake.list_trace_sessions(
        context.organization_id, limit=10, offset=0
    )
    assert sessions[0].latest_status == "partial"


def test_trace_detail_rejects_expired_retained_runs() -> None:
    repo = InMemoryAgentModelServiceFake()
    manager = AgentServiceManager(
        repo,
        database_service_manager=None,
        config=None,
        tools_service_manager=object(),
        llm_service_manager=StubLlmManager(),
    )
    expired = repo.persist_trace(
        {
            "organization_id": "org-1",
            "user_id": "admin-user",
            "agent_name": "Expired Agent",
            "run_type": "agent_run",
            "status": "success",
            "model": "gpt-4.1-mini",
            "input_message": "old prompt",
            "session_id": "session-expired",
            "context": {},
            "tokens_used": 0,
            "duration_ms": 1,
            "started_at": datetime.now(UTC) - timedelta(days=40),
            "completed_at": datetime.now(UTC) - timedelta(days=40),
            "expires_at": datetime.now(UTC) + timedelta(days=1),
            "created_at": datetime.now(UTC) - timedelta(days=40),
            "updated_at": datetime.now(UTC) - timedelta(days=40),
        },
        [{"seq": 1, "kind": "context", "payload": {}}],
    )
    # Simulate a row that is expired but has not been purged yet.
    repo.trace_runs[expired.id]["expires_at"] = datetime.now(UTC) - timedelta(seconds=1)

    with pytest.raises(NotFoundError):
        manager.get_trace_run_for_actor(
            {"organization_id": "org-1", "user_id": "admin-user", "roles": ["admin"]},
            expired.id,
        )


def test_trace_sessions_paginate_across_all_retained_runs() -> None:
    repo = InMemoryAgentModelServiceFake()
    base_time = datetime.now(UTC) - timedelta(hours=2)
    for index in range(1005):
        repo.persist_trace(
            {
                "organization_id": "org-1",
                "user_id": "admin-user",
                "agent_name": "Trace Agent",
                "run_type": "agent_run",
                "status": "success",
                "model": "gpt-4.1-mini",
                "input_message": f"prompt {index}",
                "session_id": f"session-{index}",
                "context": {},
                "tokens_used": index,
                "duration_ms": 1,
                "started_at": base_time + timedelta(seconds=index),
                "completed_at": base_time + timedelta(seconds=index, milliseconds=1),
                "expires_at": datetime.now(UTC) + timedelta(days=1),
                "created_at": base_time + timedelta(seconds=index),
                "updated_at": base_time + timedelta(seconds=index),
            },
            [{"seq": 1, "kind": "context", "payload": {}}],
        )

    sessions, total = repo.list_trace_sessions(
        "org-1",
        limit=10,
        offset=1000,
    )

    assert total == 1005
    assert len(sessions) == 5
    assert sessions[0].session_id == "session-4"
    assert sessions[-1].session_id == "session-0"


def _backend_run_request(org_id: str = "org-1", model: str = "gpt-4.1-mini"):
    runtime_spec = AgentRuntimeSpec(
        definition_id="def-1",
        key="screening_helper",
        name="Screening Helper",
        instructions="You help recruiters.",
        model=model,
    )
    execution_context = AgentExecutionContext(
        request=_context(org_id),
        runtime=RuntimeContext(organization_id=org_id, user_id="admin-user"),
    )
    return RuntimeBackendRunRequest(
        run_id="run-1",
        runtime_spec=runtime_spec,
        input_text="Summarize the candidate",
        execution_context=execution_context,
    )


def _backend_run_request_with_history(org_id: str = "org-1", model: str = "gpt-4.1-mini"):
    request = _backend_run_request(org_id=org_id, model=model)
    return request.model_copy(
        update={
            "execution_context": request.execution_context.model_copy(
                update={
                    "session": AgentSessionContext(
                        session_id="session-1",
                        definition_id="def-1",
                        recent_messages=[
                            {
                                "message_id": "m1",
                                "role": "user",
                                "content": "First prompt",
                                "created_at": "2026-01-01T00:00:00+00:00",
                            },
                            {
                                "message_id": "m2",
                                "role": "agent",
                                "content": "First response",
                                "created_at": "2026-01-01T00:00:01+00:00",
                            },
                        ],
                    )
                }
            ),
            "input_text": "Follow up",
        }
    )


def test_openai_adapter_extends_agents_sdk_base() -> None:
    assert issubclass(OpenAIAgentsSdkRuntimeAdapter, AgentsSdkRuntimeAdapterBase)


def test_adapter_delegates_model_construction_to_llm_manager(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeAgent:
        def __init__(self, name=None, instructions=None, model=None, tools=None, model_settings=None) -> None:  # noqa: ANN001
            self.name = name
            captured["agent_model"] = model

    class FakeResult:
        final_output = "agent answer"
        last_agent = type("A", (), {"name": "Screening Helper"})()

    class FakeRunner:
        @staticmethod
        async def run(agent, input_text, *, max_turns):  # noqa: ANN001
            captured["input_text"] = input_text
            captured["max_turns"] = max_turns
            return FakeResult()

    fake_agents = types.ModuleType("agents")
    fake_agents.Agent = FakeAgent
    fake_agents.Runner = FakeRunner
    fake_agents.ModelSettings = _FakeModelSettings
    monkeypatch.setitem(sys.modules, "agents", fake_agents)
    # Agent/ModelSettings are imported at module load time in sdk_adapter.py (not
    # lazily inside the function like Runner is), so patching sys.modules alone
    # doesn't reach them — the module's own already-bound names must be patched too.
    monkeypatch.setattr("agent.services.sdk_adapter.Agent", FakeAgent)
    monkeypatch.setattr("agent.services.sdk_adapter.ModelSettings", _FakeModelSettings)

    class FakeLlmManager:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def build_agent_chat_model(self, **kwargs):  # noqa: ANN001
            self.calls.append(kwargs)
            model = type("Model", (), {})()
            model.captured_llm_requests = []
            return model

    llm_manager = FakeLlmManager()
    adapter = OpenAIAgentsSdkRuntimeAdapter(llm_service_manager=llm_manager)
    result = adapter.run(_backend_run_request())

    assert llm_manager.calls == [{"organization_id": "org-1", "model_name": "gpt-4.1-mini"}]
    assert captured["agent_model"] is not None
    assert captured["max_turns"] == 10
    assert result.status == "completed"
    assert result.output_text == "agent answer"


def test_adapter_passes_recent_session_messages_to_sdk(monkeypatch) -> None:
    captured: dict[str, object] = {}


    class FakeAgent:
        def __init__(self, name=None, instructions=None, model=None, tools=None, model_settings=None) -> None:  # noqa: ANN001
            self.name = name

    class FakeResult:
        final_output = "follow-up answer"
        last_agent = type("A", (), {"name": "Screening Helper"})()

    class FakeRunner:
        @staticmethod
        async def run(agent, input_text, *, max_turns):  # noqa: ANN001
            _ = max_turns
            captured["input_text"] = input_text
            return FakeResult()

    fake_agents = types.ModuleType("agents")
    fake_agents.Agent = FakeAgent
    fake_agents.Runner = FakeRunner
    fake_agents.ModelSettings = _FakeModelSettings
    monkeypatch.setitem(sys.modules, "agents", fake_agents)
    monkeypatch.setattr("agent.services.sdk_adapter.Agent", FakeAgent)
    monkeypatch.setattr("agent.services.sdk_adapter.ModelSettings", _FakeModelSettings)

    adapter = OpenAIAgentsSdkRuntimeAdapter(
        llm_service_manager=StubLlmManager(model="gpt-4.1-mini", api_key="sk-org-key")
    )
    result = adapter.run(_backend_run_request_with_history())

    assert result.output_text == "follow-up answer"
    assert captured["input_text"] == [
        {"role": "user", "content": "First prompt"},
        {"role": "assistant", "content": "First response"},
        {"role": "user", "content": "Follow up"},
    ]


def test_adapter_extracts_usage_and_tool_calls_from_sdk_result(monkeypatch) -> None:
    class FakeAgent:
        def __init__(self, name=None, instructions=None, model=None, tools=None, model_settings=None) -> None:  # noqa: ANN001
            self.name = name

    class FakeUsage:
        total_tokens = 37

    class FakeResponse:
        usage = FakeUsage()

    class FakeRawCall:
        def model_dump(self, mode="json"):  # noqa: ANN001
            _ = mode
            return {
                "type": "function_call",
                "call_id": "call-1",
                "name": "list_entity_types",
                "arguments": "{}",
            }

    class FakeRawOutput:
        def model_dump(self, mode="json"):  # noqa: ANN001
            _ = mode
            return {
                "type": "function_call_output",
                "call_id": "call-1",
                "output": '{"success": true, "output": {"count": 3}}',
            }

    class FakeToolCallItem:
        type = "tool_call_item"
        raw_item = FakeRawCall()

    class FakeToolOutputItem:
        type = "tool_call_output_item"
        raw_item = FakeRawOutput()
        output = '{"success": true, "output": {"count": 3}}'

    class FakeResult:
        final_output = "agent answer"
        last_agent = type("A", (), {"name": "Screening Helper"})()
        raw_responses = [FakeResponse()]
        new_items = [FakeToolCallItem(), FakeToolOutputItem()]

    class FakeRunner:
        @staticmethod
        async def run(agent, input_text, *, max_turns):  # noqa: ANN001
            _ = agent, input_text, max_turns
            return FakeResult()

    fake_agents = types.ModuleType("agents")
    fake_agents.Agent = FakeAgent
    fake_agents.Runner = FakeRunner
    fake_agents.ModelSettings = _FakeModelSettings
    monkeypatch.setitem(sys.modules, "agents", fake_agents)
    monkeypatch.setattr("agent.services.sdk_adapter.Agent", FakeAgent)
    monkeypatch.setattr("agent.services.sdk_adapter.ModelSettings", _FakeModelSettings)

    adapter = OpenAIAgentsSdkRuntimeAdapter(
        llm_service_manager=StubLlmManager(model="gpt-4.1-mini", api_key="sk-org-key")
    )

    result = adapter.run(_backend_run_request())

    assert result.tokens_used == 37
    assert result.backend_metadata["tool_calls"] == [
        {
            "tool": "list_entity_types",
            "args": {},
            "result": {"success": True, "output": {"count": 3}},
            "success": True,
            "duration_ms": 0,
            "tool_call_id": "call-1",
            "raw_call": {
                "type": "function_call",
                "call_id": "call-1",
                "name": "list_entity_types",
                "arguments": "{}",
            },
        }
    ]


def test_adapter_requires_org_key_from_credential_store(monkeypatch) -> None:
    fake_agents = types.ModuleType("agents")
    fake_agents.Agent = object
    fake_agents.ModelSettings = _FakeModelSettings
    monkeypatch.setitem(sys.modules, "agents", fake_agents)
    adapter = OpenAIAgentsSdkRuntimeAdapter(
        llm_service_manager=StubLlmManager(model="gpt-4.1-mini", api_key=None)
    )
    with pytest.raises(ServiceError, match="No OpenAI API key"):
        adapter.run(_backend_run_request())


def test_manager_injects_llm_service_into_runtime_adapter() -> None:
    repo = InMemoryAgentModelServiceFake()
    manager = AgentServiceManager(
        repo,
        llm_service_manager=StubLlmManager(
            model="gpt-4.1-mini", api_key="sk-from-integrations"
        ),
    )
    assert manager.runtime_service.execution_backend._llm_service_manager is manager.llm_service_manager


def test_runtime_spec_tells_the_agent_todays_date(agent_repo_fake) -> None:
    """The agent has to know the date to turn "the last 5 days" into real dates.

    Metric windows accept a fixed set of presets plus date_from/date_to. A
    period the presets do not cover has to become actual dates, and nothing
    used to tell the model what today was, so it could not work them out.
    """
    from datetime import UTC, datetime

    service = AgentDefinitionService(agent_repo_fake)
    context = _context("org-1")
    definition = service.create_definition(
        context,
        AgentDefinitionCreate(
            name="date_aware_helper",
            display_name="Date Aware Helper",
            system_prompt="You answer questions about the pipeline.",
        ),
    )

    spec = service.build_runtime_spec(context, definition.definition_id)

    assert datetime.now(UTC).date().isoformat() in spec.instructions
    # The original prompt is kept, not replaced.
    assert "You answer questions about the pipeline." in spec.instructions
    # And the vocabulary is named, so a preset is not guessed at.
    assert "last_<N>d" in spec.instructions
    assert "date_from" in spec.instructions
