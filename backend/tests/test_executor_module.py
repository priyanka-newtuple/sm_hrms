from __future__ import annotations

from typing import Any

import pytest

from exceptions import NotFoundError, ValidationError
from executor.manager import ExecutorServiceManager, resolve_config
from executor.models.interface import (
    BaseExecutor,
    ExecutorBinding,
    ExecutorData,
    ExecutorDefinition,
    ExecutorInput,
    ExecutorResponse,
    ExecutorValue,
    FileValue,
    ValueKind,
)
from executor.models.request import ExecutorExecutionRequest


class _RejectedSampleExecutor(BaseExecutor):
    @property
    def definition(self) -> ExecutorDefinition:
        return ExecutorDefinition(
            name="rejected_sample",
            description="Return a business rejection outcome.",
            supported_outcomes=["rejected"],
        )

    def execute(self, input_payload: ExecutorInput, db: Any = None) -> ExecutorResponse:
        _ = input_payload
        return ExecutorResponse(
            success=True,
            message="Rejected by business rules",
            data=ExecutorData(outcome="rejected"),
        )


class _InvalidOutcomeExecutor(BaseExecutor):
    @property
    def definition(self) -> ExecutorDefinition:
        return ExecutorDefinition(
            name="invalid_outcome",
            description="Return an undeclared outcome for validation tests.",
            supported_outcomes=["approved"],
        )

    def execute(self, input_payload: ExecutorInput, db: Any = None) -> ExecutorResponse:
        _ = input_payload
        return ExecutorResponse(
            success=True,
            message="Unexpected business result",
            data=ExecutorData(outcome="unexpected"),
        )


def test_executor_value_validates_supported_payload_kinds() -> None:
    text_value = ExecutorValue(kind=ValueKind.TEXT, value="hello")
    number_value = ExecutorValue(kind=ValueKind.NUMBER, value=42)
    boolean_value = ExecutorValue(kind=ValueKind.BOOLEAN, value=True)
    json_value = ExecutorValue(kind=ValueKind.JSON, value={"score": 90})
    list_value = ExecutorValue(kind=ValueKind.LIST, value=["one", "two"])
    file_value = ExecutorValue(
        kind=ValueKind.FILE,
        value={
            "filename": "resume.pdf",
            "content_type": "application/pdf",
            "path": "/tmp/resume.pdf",
        },
    )
    null_value = ExecutorValue(kind=ValueKind.NULL, value=None)

    assert text_value.value == "hello"
    assert number_value.value == 42
    assert boolean_value.value is True
    assert json_value.value == {"score": 90}
    assert list_value.value == ["one", "two"]
    assert isinstance(file_value.value, FileValue)
    assert file_value.value.filename == "resume.pdf"
    assert null_value.value is None


def test_business_rejection_can_still_be_successful() -> None:
    manager = ExecutorServiceManager()
    manager.register_executor(_RejectedSampleExecutor())

    response = manager.execute_executor(
        ExecutorExecutionRequest(
            executor_name="rejected_sample",
            execution_input=ExecutorInput(
                entity_id="entity-1",
                entity_type="ATS.Application",
                current_state="SCREENING",
            ),
        )
    )

    assert response.result.success is True
    assert response.result.data.outcome == "rejected"
    assert response.result.message == "Rejected by business rules"


def test_register_and_fetch_executor_by_name() -> None:
    manager = ExecutorServiceManager()
    definition = manager.register_executor(_RejectedSampleExecutor())

    assert definition.name == "rejected_sample"
    assert manager.get_executor("rejected_sample").definition.name == "rejected_sample"


def test_missing_executor_raises_clear_error() -> None:
    manager = ExecutorServiceManager()

    with pytest.raises(NotFoundError, match="Executor not found: missing_executor"):
        manager.get_executor("missing_executor")


def test_bind_agent_service_logs_when_agent_executor_not_registered(monkeypatch) -> None:
    manager = ExecutorServiceManager()
    calls: list[str] = []

    def _fake_warning(message: str, *args: object, **kwargs: object) -> None:
        _ = args, kwargs
        calls.append(message)

    monkeypatch.setattr("executor.manager.logger.warning", _fake_warning)

    manager.bind_agent_service(object())

    assert calls == ["bind_agent_service skipped because agent_run executor is not registered"]


def test_executor_maps_outcome_to_trigger() -> None:
    manager = ExecutorServiceManager()
    manager.register_executor(_RejectedSampleExecutor())

    response = manager.execute_executor(
        ExecutorExecutionRequest(
            executor_name="rejected_sample",
            execution_input=ExecutorInput(
                entity_id="entity-1",
                entity_type="ATS.Application",
                current_state="SCREENING",
            ),
            binding=ExecutorBinding(
                executor_name="rejected_sample",
                outcome_triggers={"rejected": "reject"},
            ),
        )
    )

    assert response.result.success is True
    assert response.result.data.outcome == "rejected"
    assert response.resolved_trigger == "reject"


def test_unknown_outcome_fails_loudly() -> None:
    manager = ExecutorServiceManager()
    manager.register_executor(_InvalidOutcomeExecutor())

    with pytest.raises(
        ValidationError,
        match="Executor 'invalid_outcome' returned unsupported outcome 'unexpected'",
    ):
        manager.execute_executor(
            ExecutorExecutionRequest(
                executor_name="invalid_outcome",
                execution_input=ExecutorInput(
                    entity_id="entity-1",
                    entity_type="ATS.Application",
                    current_state="REVIEW",
                ),
            )
        )


def test_outcome_the_author_did_not_map_routes_nowhere_instead_of_failing() -> None:
    """A partly-mapped binding must not fail a run whose action succeeded.

    `approved` is mapped, `rejected` is not. Mapping is optional, so the
    unmapped outcome simply routes nowhere and the worker records it as
    `ACTION_NO_TRIGGER`.
    """
    manager = ExecutorServiceManager()
    manager.register_executor(_RejectedSampleExecutor())

    response = manager.execute_executor(
        ExecutorExecutionRequest(
            executor_name="rejected_sample",
            execution_input=ExecutorInput(
                entity_id="entity-1",
                entity_type="ATS.Application",
                current_state="SCREENING",
            ),
            binding=ExecutorBinding(
                executor_name="rejected_sample",
                outcome_triggers={"approved": "approve"},
            ),
        )
    )

    assert response.result.success is True
    assert response.result.data.outcome == "rejected"
    assert response.resolved_trigger is None


def test_empty_trigger_mapping_also_routes_nowhere() -> None:
    """Mapping nothing and mapping only other outcomes behave identically.

    The two used to diverge — an empty map returned None while a partial map
    raised — which is what made a multi-outcome action impossible to configure.
    """
    manager = ExecutorServiceManager()
    manager.register_executor(_RejectedSampleExecutor())

    response = manager.execute_executor(
        ExecutorExecutionRequest(
            executor_name="rejected_sample",
            execution_input=ExecutorInput(
                entity_id="entity-1",
                entity_type="ATS.Application",
                current_state="SCREENING",
            ),
            binding=ExecutorBinding(
                executor_name="rejected_sample",
                outcome_triggers={},
            ),
        )
    )

    assert response.result.success is True
    assert response.resolved_trigger is None


def test_technical_failure_with_binding_skips_trigger_resolution_cleanly() -> None:
    manager = _receive_data_manager()

    response = manager.execute_executor(
        ExecutorExecutionRequest(
            executor_name="form.receive_data",
            execution_input=ExecutorInput(
                entity_id="entity-1",
                entity_type="ATS.Application",
                current_state="SCREENING",
            ),
            binding=ExecutorBinding(
                executor_name="form.receive_data",
                outcome_triggers={"waiting": "wait"},
            ),
        )
    )

    assert response.result.success is False
    assert response.resolved_trigger is None


def test_executor_module_outcome_triggers_binding_resolves_correctly() -> None:
    manager = ExecutorServiceManager()
    manager.register_executor(_RejectedSampleExecutor())

    response = manager.execute_executor(
        ExecutorExecutionRequest(
            executor_name="rejected_sample",
            execution_input=ExecutorInput(
                entity_id="entity-compat",
                entity_type="ATS.Application",
                current_state="SCREENING",
            ),
            binding=ExecutorBinding(
                executor_name="rejected_sample",
                outcome_triggers={"rejected": "reject"},
            ),
        )
    )

    assert response.executor.name == "rejected_sample"
    assert response.result.data.outcome == "rejected"
    assert response.resolved_trigger == "reject"


def test_file_value_requires_path_or_url() -> None:
    with pytest.raises(ValueError, match="file values must include either a path or a url"):
        FileValue(
            filename="resume.pdf",
            content_type="application/pdf",
        )


def test_binding_rejects_blank_trigger_values() -> None:
    with pytest.raises(
        ValueError,
        match="outcome trigger mapping for 'approved' must be a non-empty string",
    ):
        ExecutorBinding(
            executor_name="sample_content_review",
            outcome_triggers={"approved": "   "},
        )


def test_execution_request_rejects_blank_executor_name() -> None:
    with pytest.raises(ValueError):
        ExecutorExecutionRequest(
            executor_name="   ",
            execution_input=ExecutorInput(
                entity_id="entity-1",
                entity_type="ATS.Application",
                current_state="DOC_REVIEW",
            ),
        )


def test_executor_definition_requires_supported_outcomes() -> None:
    with pytest.raises(ValueError):
        ExecutorDefinition(
            name="empty_outcomes",
            description="Invalid definition",
            supported_outcomes=[],
        )


def test_registry_is_shared_across_manager_instances() -> None:
    first_manager = ExecutorServiceManager()
    second_manager = ExecutorServiceManager()

    first_manager.register_executor(_RejectedSampleExecutor())

    assert second_manager.get_executor("rejected_sample").definition.name == "rejected_sample"


# ── resolve_config ─────────────────────────────────────────────────────────────


def test_resolve_config_replaces_entity_placeholders() -> None:
    config = {"to": "$entity.email", "subject": "Hello $entity.name"}
    entity_data = {"email": "user@example.com", "name": "Alice"}
    resolved = resolve_config(config, entity_data)
    assert resolved["to"] == "user@example.com"
    assert resolved["subject"] == "Hello Alice"


def test_resolve_config_handles_nested_dict() -> None:
    config = {"meta": {"recipient": "$entity.email"}}
    entity_data = {"email": "user@example.com"}
    resolved = resolve_config(config, entity_data)
    assert resolved["meta"]["recipient"] == "user@example.com"


def test_resolve_config_handles_list_values() -> None:
    config = {"recipients": ["$entity.email", "admin@example.com"]}
    entity_data = {"email": "user@example.com"}
    resolved = resolve_config(config, entity_data)
    assert resolved["recipients"] == ["user@example.com", "admin@example.com"]


def test_resolve_config_raises_for_missing_entity_field() -> None:
    config = {"to": "$entity.missing_field"}
    entity_data = {"email": "user@example.com"}
    with pytest.raises(ValidationError, match="does not exist on entity"):
        resolve_config(config, entity_data)


def test_resolve_config_leaves_non_placeholder_strings_unchanged() -> None:
    config = {"subject": "Hello World", "count": 42}
    resolved = resolve_config(config, {})
    assert resolved["subject"] == "Hello World"
    assert resolved["count"] == 42


# ── ReceiveDataExecutor ────────────────────────────────────────────────────────


def _receive_data_manager() -> ExecutorServiceManager:
    from executor.executors.receive_data import ReceiveDataExecutor
    manager = ExecutorServiceManager()
    manager.register_executor(ReceiveDataExecutor())
    return manager


def test_receive_data_executor_returns_waiting_with_form_id() -> None:
    manager = _receive_data_manager()
    response = manager.execute_executor(
        ExecutorExecutionRequest(
            executor_name="form.receive_data",
            execution_input=ExecutorInput(
                entity_id="entity-1",
                entity_type="ATS.Application",
                current_state="SCREENING",
                fields={"form_id": ExecutorValue(kind=ValueKind.TEXT, value="form-abc")},
            ),
        )
    )
    assert response.result.success is True
    assert response.result.data.outcome == "waiting"
    assert response.result.is_external_wait is True
    assert response.result.data.meta["form_id"] == "form-abc"


def test_receive_data_executor_fails_without_form_id() -> None:
    manager = _receive_data_manager()
    response = manager.execute_executor(
        ExecutorExecutionRequest(
            executor_name="form.receive_data",
            execution_input=ExecutorInput(
                entity_id="entity-1",
                entity_type="ATS.Application",
                current_state="SCREENING",
            ),
        )
    )
    assert response.result.success is False
    assert response.result.data.outcome in ("execution_failed", "failed")


def test_receive_data_executor_uses_custom_timeout() -> None:
    manager = _receive_data_manager()
    response = manager.execute_executor(
        ExecutorExecutionRequest(
            executor_name="form.receive_data",
            execution_input=ExecutorInput(
                entity_id="entity-1",
                entity_type="ATS.Application",
                current_state="SCREENING",
                fields={
                    "form_id": ExecutorValue(kind=ValueKind.TEXT, value="form-abc"),
                    "timeout_hours": ExecutorValue(kind=ValueKind.TEXT, value="48"),
                },
            ),
        )
    )
    assert response.result.success is True
    assert response.result.timeout_hours == 48


# ── SendEmailExecutor ──────────────────────────────────────────────────────────


class _FakeMailResult:
    success = True
    message = "ok"


class _FakeMailService:
    def send_email(self, **_kwargs: Any) -> _FakeMailResult:
        return _FakeMailResult()

    @property
    def email_config_model_service(self) -> None:
        return None


class _FailingMailService:
    def send_email(self, **_kwargs: Any) -> object:
        class _R:
            success = False
            message = "SMTP error"
        return _R()

    @property
    def email_config_model_service(self) -> None:
        return None


def _make_send_email_manager(mail_service: Any) -> ExecutorServiceManager:
    from executor.executors.send_email import SendEmailExecutor
    manager = ExecutorServiceManager()
    manager.register_executor(SendEmailExecutor(
        mail_service=mail_service,
        database_service_manager=None,
        config=None,
    ))
    return manager


def test_send_email_executor_returns_sent_on_success() -> None:
    manager = _make_send_email_manager(_FakeMailService())
    response = manager.execute_executor(
        ExecutorExecutionRequest(
            executor_name="mail.send_email",
            execution_input=ExecutorInput(
                entity_id="entity-1",
                entity_type="ATS.Application",
                current_state="SCREENING",
                fields={
                    "org_id": ExecutorValue(kind=ValueKind.TEXT, value="org-1"),
                    "to": ExecutorValue(kind=ValueKind.TEXT, value="user@example.com"),
                    "subject": ExecutorValue(kind=ValueKind.TEXT, value="Hello"),
                    "body_html": ExecutorValue(kind=ValueKind.TEXT, value="<p>Hi</p>"),
                },
            ),
        )
    )
    assert response.result.success is True
    assert response.result.data.outcome == "sent"


def test_send_email_executor_fails_without_required_fields() -> None:
    manager = _make_send_email_manager(_FakeMailService())
    response = manager.execute_executor(
        ExecutorExecutionRequest(
            executor_name="mail.send_email",
            execution_input=ExecutorInput(
                entity_id="entity-1",
                entity_type="ATS.Application",
                current_state="SCREENING",
                fields={
                    "org_id": ExecutorValue(kind=ValueKind.TEXT, value="org-1"),
                },
            ),
        )
    )
    assert response.result.success is False
    assert response.result.data.outcome in ("execution_failed", "failed")


def test_send_email_executor_returns_failed_when_mail_service_fails() -> None:
    manager = _make_send_email_manager(_FailingMailService())
    response = manager.execute_executor(
        ExecutorExecutionRequest(
            executor_name="mail.send_email",
            execution_input=ExecutorInput(
                entity_id="entity-1",
                entity_type="ATS.Application",
                current_state="SCREENING",
                fields={
                    "org_id": ExecutorValue(kind=ValueKind.TEXT, value="org-1"),
                    "to": ExecutorValue(kind=ValueKind.TEXT, value="user@example.com"),
                    "subject": ExecutorValue(kind=ValueKind.TEXT, value="Hello"),
                    "body_html": ExecutorValue(kind=ValueKind.TEXT, value="<p>Hi</p>"),
                },
            ),
        )
    )
    assert response.result.success is False
    assert response.result.data.outcome in ("execution_failed", "failed")
