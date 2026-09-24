"""Unit tests for the generic agent_run executor."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from agent.models.request import AgentRunRequest
from entities.db_models import EntityRecordModel, EntityRelationModel
from executor.executors.agent_run import AgentExecutor
from executor.models.interface import ExecutorInput, ExecutorValue, ValueKind


class _FakeAgentResponse:
    """Minimal stand-in for AgentRunResponse (only the attributes the executor reads)."""

    def __init__(
        self,
        *,
        status: str = "completed",
        output: str | None = None,
        error: str | None = None,
        run_id: str = "run-1",
    ) -> None:
        self.status = status
        self.output = output
        self.error = error
        self.run_id = run_id


class _FakeAgentService:
    """Records the last request and returns a canned response."""

    def __init__(self, response: _FakeAgentResponse) -> None:
        self._response = response
        self.last_actor: dict[str, Any] | None = None
        self.last_request: Any = None

    def run_agent_for_actor(self, actor: dict[str, Any], request: Any) -> _FakeAgentResponse:
        self.last_actor = actor
        self.last_request = request
        return self._response


def _make_input(config: dict[str, Any], *, org_id: str = "org-1") -> ExecutorInput:
    """Build an ExecutorInput carrying org_id and the raw action config."""
    fields = {
        "org_id": ExecutorValue(kind=ValueKind.TEXT, value=org_id),
        "_raw_config": ExecutorValue(kind=ValueKind.TEXT, value=json.dumps(config)),
    }
    return ExecutorInput(
        entity_id="entity-1",
        entity_type="ATS.Application",
        current_state="AI_SCREENING",
        fields=fields,
    )


def _executor(response: _FakeAgentResponse) -> AgentExecutor:
    executor = AgentExecutor()
    executor.agent_service = _FakeAgentService(response)
    return executor


def test_happy_path_maps_json_output_to_entity_fields() -> None:
    executor = _executor(
        _FakeAgentResponse(output='{"score": 8, "recommendation": "advance"}')
    )
    config = {
        "agent_id": "agent-123",
        "output_mapping": {"score": "ai_score", "recommendation": "ai_status"},
    }

    result = executor.execute(_make_input(config), db=None)

    assert result.success is True
    assert result.data.outcome == "success"
    assert result.data.fields["ai_score"].value == 8
    assert result.data.fields["ai_status"].value == "advance"
    assert result.data.meta["run_id"] == "run-1"


def test_prompt_includes_output_keys_and_system_actor_carries_org() -> None:
    executor = _executor(_FakeAgentResponse(output='{"score": 5}'))
    fake_service = executor.agent_service
    config = {"agent_id": "agent-123", "output_mapping": {"score": "ai_score"}}

    executor.execute(_make_input(config), db=None)

    assert fake_service.last_request.definition_id == "agent-123"
    assert '"score"' in fake_service.last_request.input
    assert fake_service.last_actor == {"organization_id": "org-1", "user_id": None, "roles": []}


def test_json_output_wrapped_in_code_fence_is_parsed() -> None:
    executor = _executor(
        _FakeAgentResponse(output='```json\n{"score": 9}\n```')
    )
    config = {"agent_id": "agent-123", "output_mapping": {"score": "ai_score"}}

    result = executor.execute(_make_input(config), db=None)

    assert result.success is True
    assert result.data.fields["ai_score"].value == 9


def test_non_json_output_returns_failed() -> None:
    executor = _executor(_FakeAgentResponse(output="Sorry, I cannot help with that."))
    config = {"agent_id": "agent-123", "output_mapping": {"score": "ai_score"}}

    result = executor.execute(_make_input(config), db=None)

    assert result.success is False
    assert result.data.outcome == "failed"


def test_outcome_field_routes_on_agent_decision() -> None:
    executor = _executor(
        _FakeAgentResponse(output='{"recommendation": "advance", "score": 8}')
    )
    config = {
        "agent_id": "agent-123",
        "output_mapping": {"score": "ai_score"},
        "outcome_field": "recommendation",
        "outcome_triggers": {"advance": "T_ADVANCE", "reject": "T_REJECT"},
    }

    result = executor.execute(_make_input(config), db=None)

    assert result.success is True
    assert result.data.outcome == "advance"
    assert result.data.fields["ai_score"].value == 8


def test_outcome_field_lists_allowed_values_in_prompt() -> None:
    executor = _executor(_FakeAgentResponse(output='{"recommendation": "advance"}'))
    fake_service = executor.agent_service
    config = {
        "agent_id": "agent-123",
        "output_mapping": {"recommendation": "ai_status"},
        "outcome_field": "recommendation",
        "outcome_triggers": {"advance": "T_ADVANCE", "reject": "T_REJECT"},
    }

    executor.execute(_make_input(config), db=None)

    prompt = fake_service.last_request.input
    assert "advance" in prompt and "reject" in prompt


def test_prompt_is_truncated_to_agent_request_limit() -> None:
    executor = _executor(_FakeAgentResponse(output='{"score": 5}'))
    fake_service = executor.agent_service
    config = {
        "agent_id": "agent-123",
        "output_mapping": {"score": "ai_score"},
        "prompt_instructions": "x" * 20_000,
    }

    executor.execute(_make_input(config), db=None)

    field = AgentRunRequest.model_fields["input"]
    max_length = getattr(field, "max_length", None)
    if max_length is None:
        for metadata in getattr(field, "metadata", ()):
            max_length = getattr(metadata, "max_length", None)
            if max_length is not None:
                break
    assert isinstance(max_length, int)
    assert len(fake_service.last_request.input) == max_length


def test_missing_outcome_field_value_returns_failed() -> None:
    executor = _executor(_FakeAgentResponse(output='{"score": 8}'))
    config = {
        "agent_id": "agent-123",
        "output_mapping": {"score": "ai_score"},
        "outcome_field": "recommendation",
        "outcome_triggers": {"advance": "T_ADVANCE"},
    }

    result = executor.execute(_make_input(config), db=None)

    assert result.success is False
    assert "recommendation" in result.message


def test_agent_waiting_for_approval_returns_failed() -> None:
    executor = _executor(_FakeAgentResponse(status="waiting_for_approval", output=None))
    config = {"agent_id": "agent-123", "output_mapping": {"score": "ai_score"}}

    result = executor.execute(_make_input(config), db=None)

    assert result.success is False
    assert "approval" in result.message.lower()


def test_missing_agent_id_returns_failed() -> None:
    executor = _executor(_FakeAgentResponse(output='{"score": 1}'))
    config = {"output_mapping": {"score": "ai_score"}}

    result = executor.execute(_make_input(config), db=None)

    assert result.success is False
    assert "agent_id" in result.message


def test_missing_output_mapping_returns_failed() -> None:
    executor = _executor(_FakeAgentResponse(output='{"score": 1}'))
    config = {"agent_id": "agent-123"}

    result = executor.execute(_make_input(config), db=None)

    assert result.success is False
    assert "output_mapping" in result.message


def test_unbound_agent_service_returns_failed() -> None:
    executor = AgentExecutor()  # agent_service never bound
    config = {"agent_id": "agent-123", "output_mapping": {"score": "ai_score"}}

    result = executor.execute(_make_input(config), db=None)

    assert result.success is False
    assert "agent runtime is not available" in result.message


def test_runtime_exception_returns_generic_failure_message() -> None:
    class _RaisingAgentService:
        def run_agent_for_actor(self, actor: dict[str, Any], request: Any) -> Any:
            _ = actor, request
            raise RuntimeError("secret backend detail")

    executor = AgentExecutor()
    executor.agent_service = _RaisingAgentService()
    config = {"agent_id": "agent-123", "output_mapping": {"score": "ai_score"}}

    result = executor.execute(_make_input(config), db=None)

    assert result.success is False
    assert result.message == "agent run failed"


def test_render_relations_batches_linked_entity_lookup() -> None:
    class _FakeQuery:
        def __init__(self, rows: list[object]) -> None:
            self._rows = rows

        def filter(self, *args: object) -> "_FakeQuery":
            _ = args
            return self

        def all(self) -> list[object]:
            return self._rows

    class _FakeDb:
        def __init__(self) -> None:
            self.entity_record_query_count = 0

        def query(self, model: Any) -> _FakeQuery:
            if model is EntityRelationModel:
                return _FakeQuery(
                    [
                        SimpleNamespace(to_entity_id="linked-1", relation_type="job"),
                        SimpleNamespace(to_entity_id="linked-2", relation_type="job"),
                    ]
                )
            if model is EntityRecordModel:
                self.entity_record_query_count += 1
                return _FakeQuery(
                    [
                        SimpleNamespace(entity_id="linked-1", data={"title": "Backend Engineer"}),
                        SimpleNamespace(entity_id="linked-2", data={"title": "Platform Engineer"}),
                    ]
                )
            raise AssertionError(f"unexpected model query: {model}")

    executor = AgentExecutor()
    fake_db = _FakeDb()

    rendered = executor._render_relations(fake_db, "org-1", "entity-1", ["job"])

    assert "Backend Engineer" in rendered
    assert "Platform Engineer" in rendered
    assert fake_db.entity_record_query_count == 1
