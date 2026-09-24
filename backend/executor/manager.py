"""Business orchestration for the shared executor runtime foundation."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from common.logger import logger
from exceptions import NotFoundError, ServiceError, ValidationError
from executor.executors.agent_run import AgentExecutor
from executor.executors.entity_activate_schedules import (
    EntityActivateSchedulesExecutor,
    EntityRunSchedulesOnceExecutor,
)
from executor.executors.entity_assign_user import EntityAssignUserExecutor
from executor.executors.entity_create_and_enroll import EntityCreateAndEnrollExecutor
from executor.executors.http_webhook import HttpWebhookExecutor
from executor.executors.receive_data import ReceiveDataExecutor
from executor.executors.send_email import SendEmailExecutor
from executor.executors.signal_fire import SignalExecutor
from executor.models.interface import ENTITY_ASSIGN_USER_ACTION_KIND
from executor.models.response import ExecutorCatalogResponse, ExecutorExecutionResponse

if TYPE_CHECKING:
    from executor.models.interface import (
        BaseExecutor,
        ExecutorBinding,
        ExecutorDefinition,
        ExecutorResponse,
    )
    from executor.models.request import ExecutorExecutionRequest
    from mail.manager import MailServiceManager


# ── Placeholder Resolution ────────────────────────────────────────────────────

_PLACEHOLDER_RE = re.compile(r"\$entity\.([a-zA-Z_][a-zA-Z0-9_]*)")


def resolve_config(config: dict[str, Any], entity_data: dict[str, Any]) -> dict[str, Any]:
    """Return config with all $entity.* placeholders replaced from entity_data."""
    return {key: _resolve_value(key, value, entity_data) for key, value in config.items()}


def _resolve_value(key: str, value: Any, entity_data: dict[str, Any]) -> Any:
    """Recursively resolve placeholders in strings, dicts, and lists."""
    if isinstance(value, str):
        return _resolve_string(key, value, entity_data)
    if isinstance(value, dict):
        return resolve_config(value, entity_data)
    if isinstance(value, list):
        return [_resolve_value(key, item, entity_data) for item in value]
    return value


def _resolve_string(key: str, value: str, entity_data: dict[str, Any]) -> str:
    """Replace all $entity.field_name occurrences in a string with their entity data values."""

    def _replacer(match: re.Match) -> str:
        field_name = match.group(1)
        if field_name not in entity_data:
            raise ValidationError(
                f"Placeholder '$entity.{field_name}' in config field '{key}' "
                f"does not exist on entity. Available fields: {sorted(entity_data.keys())}"
            )
        return str(entity_data[field_name])

    return _PLACEHOLDER_RE.sub(_replacer, value)


# ── Executor Registry ─────────────────────────────────────────────────────────

_EXECUTOR_CLASSES = [
    ReceiveDataExecutor,
    SendEmailExecutor,
    SignalExecutor,
    HttpWebhookExecutor,
    AgentExecutor,
    EntityCreateAndEnrollExecutor,
    EntityActivateSchedulesExecutor,
    EntityRunSchedulesOnceExecutor,
    EntityAssignUserExecutor,
]

# ── Service Manager ───────────────────────────────────────────────────────────


class ExecutorServiceManager:
    """Own executor registration, execution, and outcome-to-trigger resolution."""

    def __init__(
        self,
        _executor_db_model_service: object = None,
        _database_service_manager: object = None,
        _config: object = None,
        *_dependencies: object,
        _mail_service: MailServiceManager | None = None,
        _notifications_service: object | None = None,
        _filehandler_service: object | None = None,
    ) -> None:
        """Store executor dependencies and register default executors."""

        self._executors: dict[str, BaseExecutor] = {}
        self._database_service_manager = _database_service_manager
        self._executor_db_model_service = _executor_db_model_service
        self._filehandler_service = _filehandler_service

        if _mail_service and _database_service_manager:
            for executor_class in _EXECUTOR_CLASSES:
                kwargs: dict[str, object] = {
                    "mail_service": _mail_service,
                    "database_service_manager": _database_service_manager,
                    "config": _config,
                    "notifications_service": _notifications_service,
                }
                # AgentExecutor also reads entity files; the agent service is late-bound.
                if executor_class is AgentExecutor:
                    kwargs["filehandler_service"] = _filehandler_service
                executor = executor_class(**kwargs)
                self.register_executor(executor)

    def bind_agent_service(self, agent_service: object) -> None:
        """Late-bind the agent runtime into the AgentExecutor (built after this manager)."""
        executor = self._executors.get("agent_run")
        if executor is None:
            logger.warning(
                "bind_agent_service skipped because agent_run executor is not registered"
            )
            return
        executor.agent_service = agent_service

    def bind_entity_workflow_services(self, entities_service: object, workflow_service: object) -> None:
        """Late-bind managers required by scheduled entity creation."""
        executor = self._executors.get("entity.create_and_enroll")
        if isinstance(executor, EntityCreateAndEnrollExecutor):
            executor.bind_services(entities_service, workflow_service)

    def bind_schedules_service(self, schedules_service: object) -> None:
        """Late-bind the schedules domain into its workflow action executor."""
        for action_kind in ("entity.activate_schedules", "entity.run_schedules_once"):
            executor = self._executors.get(action_kind)
            if isinstance(executor, EntityActivateSchedulesExecutor):
                executor.bind_service(schedules_service)
        creation_executor = self._executors.get("entity.create_and_enroll")
        if isinstance(creation_executor, EntityCreateAndEnrollExecutor):
            creation_executor.bind_schedules_service(schedules_service)

    def bind_assign_user_services(self, entities_service: object, user_service: object) -> None:
        """Late-bind the managers the assign-user action needs."""
        executor = self._executors.get(ENTITY_ASSIGN_USER_ACTION_KIND)
        if isinstance(executor, EntityAssignUserExecutor):
            executor.bind_services(entities_service, user_service)

    def registered_action_kinds(self) -> frozenset[str]:
        """Every action kind this runtime can actually execute.

        Workflow publish validation reads this so a workflow cannot be published
        naming an action that would only fail later in the background worker.
        Returns the executable set, not the `action_definitions` catalogue: a
        kind listed in the catalogue but never registered still cannot run.
        """
        return frozenset(self._executors)

    def get_catalog(self) -> ExecutorCatalogResponse:
        """Return the currently registered executor catalog."""
        return ExecutorCatalogResponse(
            executors=[executor.definition for executor in self._executors.values()]
        )

    def register_executor(self, executor: BaseExecutor) -> ExecutorDefinition:
        """Register one executor implementation and return its definition."""
        definition = executor.definition
        executor_name = str(definition.name).strip()
        if not executor_name:
            raise ValidationError("executor definition name must be a non-empty string")
        self._executors[executor_name] = executor
        return definition

    def get_executor(self, executor_name: str) -> BaseExecutor:
        """Return one registered executor by name, raising NotFoundError if missing."""
        normalized_name = str(executor_name).strip()
        executor = self._executors.get(normalized_name)
        if executor is None:
            raise NotFoundError(f"Executor not found: {normalized_name}")
        return executor

    def execute_executor(
        self, request: ExecutorExecutionRequest, db: Any = None
    ) -> ExecutorExecutionResponse:
        """Execute one executor and optionally resolve its trigger mapping from the outcome."""
        try:
            executor = self.get_executor(request.executor_name)
            result = executor.execute(request.execution_input, db=db)
            self._validate_response(executor.definition, result)

            resolved_trigger = None
            if (request.binding is not None and result.success and not result.is_external_wait) or (
                request.binding is not None
                and result.success
                and result.is_external_wait
                and result.fire_trigger_immediately
            ):
                resolved_trigger = self.resolve_trigger_for_outcome(result, request.binding)

            return ExecutorExecutionResponse(
                executor=executor.definition,
                result=result,
                resolved_trigger=resolved_trigger,
            )
        except (NotFoundError, ValidationError, ServiceError):
            raise
        except Exception as exc:
            logger.error("execute_executor failed executor=%s error=%s", request.executor_name, exc)
            raise

    def resolve_trigger_for_outcome(
        self,
        result: ExecutorResponse,
        binding: ExecutorBinding,
    ) -> str | None:
        """Resolve one transition trigger for a successful business outcome.

        None means "route nowhere". Mapping outcomes to transitions is optional,
        so an outcome the author did not map is a design choice, not a fault —
        the worker records it as `ACTION_NO_TRIGGER` and carries on. This used
        to raise when *some* outcomes were mapped but not this one, which failed
        a run whose action had already succeeded; an action with more than one
        outcome could not be configured without mapping every branch.

        Nothing is lost by not raising: `_validate_response` has already checked
        the outcome against the executor's declared contract before this runs.
        """
        if not result.success:
            raise ValidationError("Cannot resolve trigger for unsuccessful executor response")

        outcome = str(result.data.outcome).strip()
        trigger = binding.outcome_triggers.get(outcome) if binding.outcome_triggers else None
        if trigger is None:
            logger.warning(
                "no trigger mapping for outcome=%s executor=%s — not routing",
                outcome,
                binding.executor_name,
            )
        return trigger

    @staticmethod
    def _validate_response(
        definition: ExecutorDefinition,
        result: ExecutorResponse,
    ) -> None:
        """Validate that the executor response outcome matches its declared contract."""
        outcome = str(result.data.outcome).strip()
        if not outcome:
            raise ServiceError("Executor response outcome must be a non-empty string")
        if not result.success:
            return
        if definition.dynamic_outcomes:
            return
        if outcome not in definition.supported_outcomes:
            logger.error(
                "executor=%s returned unsupported outcome=%s supported=%s",
                definition.name,
                outcome,
                definition.supported_outcomes,
            )
            raise ValidationError(
                f"Executor '{definition.name}' returned unsupported outcome '{outcome}'"
            )
