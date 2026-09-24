"""Interface models and execution contracts for executors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Any

from pydantic import Field, model_validator

from common.data_model import BaseModel as PydanticBaseModel
from common.data_model import ExtendedStrEnum


class ValueKind(StrEnum):
    """Supported value kinds for executor inputs and outputs."""

    TEXT = "text"
    NUMBER = "number"
    BOOLEAN = "boolean"
    JSON = "json"
    FILE = "file"
    LIST = "list"
    NULL = "null"


ENTITY_ASSIGN_USER_ACTION_KIND = "entity.assign_user"


class AssignUserConfigKey(ExtendedStrEnum):
    """Keys a workflow author sets on an `entity.assign_user` action.

    A cross-module contract: the executor reads these at run time and workflow
    publish validation checks them, so both sides must change together.
    """

    ASSIGNMENT_TYPE = "assignment_type"
    USER_ID = "user_id"


class AssignUserAssignmentType(ExtendedStrEnum):
    """How an `entity.assign_user` action picks its target.

    `USER` takes a specific user chosen in the builder; `ORIGINATOR` resolves
    whoever created the record, which is only known at run time.
    """

    USER = "user"
    ORIGINATOR = "originator"


class AssignUserOutcome(ExtendedStrEnum):
    """Outcomes an `entity.assign_user` run can report.

    The first five are findings the action reports after doing its job: the
    record was assigned, it already held that person, or that person cannot
    take work. Authors route on them, and every mapping is optional.

    `FAILED` is not one of those. It marks a crash — a config the worker cannot
    read, an unreachable service — and is deliberately left out of
    `ROUTABLE_OUTCOMES`, because the engine's own failure policy owns that case.
    Advertising it as routable would offer a control that the failure policy
    overrides anyway.
    """

    ASSIGNED = "assigned"
    ALREADY_ASSIGNED = "already_assigned"
    ORIGINATOR_NOT_FOUND = "originator_not_found"
    USER_NOT_FOUND = "user_not_found"
    USER_SUSPENDED = "user_suspended"
    FAILED = "failed"


#: What the builder offers as routable, and what the executor declares.
ROUTABLE_ASSIGN_USER_OUTCOMES: tuple[AssignUserOutcome, ...] = tuple(
    outcome for outcome in AssignUserOutcome if outcome is not AssignUserOutcome.FAILED
)


def assign_user_config_problem(config: dict[str, Any]) -> str | None:
    """Describe what is wrong with an `entity.assign_user` config, or None if valid."""
    assignment_type = str(config.get(AssignUserConfigKey.ASSIGNMENT_TYPE) or "").strip()
    if not assignment_type:
        return "Choose who to assign — a user, or the record's creator."
    if assignment_type not in set(AssignUserAssignmentType):
        return f"Unknown assignment type '{assignment_type}'."
    has_user_id = bool(str(config.get(AssignUserConfigKey.USER_ID) or "").strip())
    if assignment_type == AssignUserAssignmentType.USER and not has_user_id:
        return "No user selected."
    if assignment_type == AssignUserAssignmentType.ORIGINATOR and has_user_id:
        return "Remove the selected user — the creator is used instead."
    return None


class FileValue(PydanticBaseModel):
    """Describe one file payload passed through an executor."""

    filename: str = Field(..., min_length=1)
    content_type: str = Field(..., min_length=1)
    path: str | None = None
    url: str | None = None
    size_bytes: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_location(self) -> FileValue:
        """Require at least one file location reference."""
        normalized_path = str(self.path).strip() if self.path is not None else ""
        normalized_url = str(self.url).strip() if self.url is not None else ""
        self.path = normalized_path or None
        self.url = normalized_url or None
        if self.path is None and self.url is None:
            raise ValueError("file values must include either a path or a url")
        return self


class ExecutorValue(PydanticBaseModel):
    """Wrap one typed executor value."""

    kind: ValueKind
    value: Any = None

    @model_validator(mode="after")
    def validate_value(self) -> ExecutorValue:
        """Validate that the payload matches the declared value kind."""
        if self.kind == ValueKind.TEXT and not isinstance(self.value, str):
            raise ValueError("text values must be strings")
        if self.kind == ValueKind.NUMBER and (
            isinstance(self.value, bool) or not isinstance(self.value, (int, float))
        ):
            raise ValueError("number values must be integers or floats")
        if self.kind == ValueKind.BOOLEAN and not isinstance(self.value, bool):
            raise ValueError("boolean values must be booleans")
        if self.kind == ValueKind.JSON and not isinstance(self.value, dict):
            raise ValueError("json values must be objects")
        if self.kind == ValueKind.LIST and not isinstance(self.value, list):
            raise ValueError("list values must be arrays")
        if self.kind == ValueKind.NULL and self.value is not None:
            raise ValueError("null values must be None")
        if self.kind == ValueKind.FILE:
            if isinstance(self.value, dict):
                self.value = FileValue.model_validate(self.value)
            if not isinstance(self.value, FileValue):
                raise ValueError("file values must be FileValue payloads")
        return self


class ExecutorInput(PydanticBaseModel):
    """Carry the normalized input payload for one executor run."""

    entity_id: str = Field(..., min_length=1)
    entity_type: str = Field(..., min_length=1)
    current_state: str = Field(..., min_length=1)
    fields: dict[str, ExecutorValue] = Field(default_factory=dict)
    # Context carries runtime-scoped values outside the primary business payload.
    context: dict[str, ExecutorValue] = Field(default_factory=dict)


class ExecutorData(PydanticBaseModel):
    """Carry structured executor output data."""

    outcome: str = Field(..., min_length=1)
    fields: dict[str, ExecutorValue] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)


class ExecutorResponse(PydanticBaseModel):
    """Represent one normalized executor response envelope."""

    success: bool
    data: ExecutorData
    message: str = ""
    error_code: str | None = None
    is_external_wait: bool = False
    fire_trigger_immediately: bool = False
    timeout_hours: int = 24


class ExecutorDefinition(PydanticBaseModel):
    """Describe one executor implementation registered in the runtime."""

    name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    supported_outcomes: list[str] = Field(default_factory=list, min_length=1)
    # When True, the executor may return outcomes beyond supported_outcomes (e.g. an
    # agent's decision routes the workflow), so outcome-contract validation is skipped.
    dynamic_outcomes: bool = False

    @model_validator(mode="after")
    def validate_supported_outcomes(self) -> ExecutorDefinition:
        """Ensure supported outcomes are non-empty unique strings."""
        normalized_outcomes: list[str] = []
        seen_outcomes: set[str] = set()
        for outcome in self.supported_outcomes:
            normalized_outcome = str(outcome).strip()
            if not normalized_outcome:
                raise ValueError("supported outcomes must be non-empty strings")
            if normalized_outcome in seen_outcomes:
                continue
            seen_outcomes.add(normalized_outcome)
            normalized_outcomes.append(normalized_outcome)
        self.supported_outcomes = normalized_outcomes
        return self


class BaseExecutor(ABC):
    """Abstract base contract for executor implementations."""

    @property
    @abstractmethod
    def definition(self) -> ExecutorDefinition:
        """Return the metadata that describes this executor."""

    @abstractmethod
    def execute(self, input_payload: ExecutorInput, db: Any = None) -> ExecutorResponse:
        """Execute business logic and return a normalized response."""


class ExecutorBinding(PydanticBaseModel):
    """Bind one executor to state-machine outcome-to-trigger routing."""

    executor_name: str = Field(..., min_length=1)
    outcome_triggers: dict[str, str] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def normalize_fields(self) -> ExecutorBinding:
        """Normalize the binding payload."""
        self.executor_name = str(self.executor_name).strip()
        normalized_outcome_triggers: dict[str, str] = {}
        for raw_outcome, raw_trigger in dict(self.outcome_triggers or {}).items():
            outcome = str(raw_outcome).strip()
            trigger = str(raw_trigger).strip()
            if not outcome:
                raise ValueError("outcome trigger keys must be non-empty strings")
            if not trigger:
                raise ValueError(
                    f"outcome trigger mapping for '{outcome}' must be a non-empty string"
                )
            normalized_outcome_triggers[outcome] = trigger
        self.outcome_triggers = normalized_outcome_triggers
        self.config = dict(self.config or {})
        return self
