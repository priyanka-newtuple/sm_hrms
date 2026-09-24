"""Executor: wait for external form data submission."""

from __future__ import annotations

from typing import Any

from executor.executors.base import fail, get_field
from executor.models.interface import (
    BaseExecutor,
    ExecutorData,
    ExecutorDefinition,
    ExecutorInput,
    ExecutorResponse,
)

_DEFAULT_TIMEOUT_HOURS = 24


class ReceiveDataExecutor(BaseExecutor):
    """Pause the workflow and wait for an external form submission."""

    def __init__(
        self,
        mail_service: Any = None,
        database_service_manager: Any = None,
        config: Any = None,
        notifications_service: Any = None,
    ) -> None:
        pass

    @property
    def definition(self) -> ExecutorDefinition:
        return ExecutorDefinition(
            name="form.receive_data",
            description="Pause the workflow and wait for the entity's form to be submitted.",
            supported_outcomes=["waiting", "received", "failed"],
        )

    def execute(self, input_payload: ExecutorInput, db: Any = None) -> ExecutorResponse:
        fields = input_payload.fields
        form_id = get_field(fields, "form_id")

        if not form_id:
            return fail("missing required field: form_id")

        timeout_hours_raw = get_field(fields, "timeout_hours")
        try:
            timeout_hours = int(timeout_hours_raw) if timeout_hours_raw else _DEFAULT_TIMEOUT_HOURS
        except ValueError:
            timeout_hours = _DEFAULT_TIMEOUT_HOURS

        return ExecutorResponse(
            success=True,
            message="Waiting for form submission",
            is_external_wait=True,
            timeout_hours=timeout_hours,
            data=ExecutorData(
                outcome="waiting",
                fields={},
                meta={"form_id": form_id, "entity_id": input_payload.entity_id},
            ),
        )
