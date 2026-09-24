"""timer_duration is a frontend-recorded elapsed-seconds entity field."""

from __future__ import annotations

import pytest

from entities.models.request import EntityRecordUpdateRequest
from workflow.models.interface import (
    EntityField,
    EntityFieldType,
    PreflightFieldRequirement,
    RequiredField,
    Transition,
)
from workflow.services import (
    DefinitionAnalysisService,
    SimulationService,
    TransitionEvaluationService,
)

TIMER_FIELD = "elapsed_seconds"


def test_entity_update_contract_preserves_a_frontend_recorded_duration() -> None:
    request = EntityRecordUpdateRequest(data={TIMER_FIELD: 90})

    assert request.data == {TIMER_FIELD: 90}


def test_a_timer_field_is_never_typed_directly() -> None:
    assert EntityField(field=TIMER_FIELD, type=EntityFieldType.TIMER_DURATION).editable is False
    assert (
        EntityField(field=TIMER_FIELD, type=EntityFieldType.TIMER_DURATION, editable=True).editable
        is False
    )


def test_a_timer_field_preserves_its_required_setting() -> None:
    assert (
        EntityField(
            field=TIMER_FIELD, type=EntityFieldType.TIMER_DURATION, required=True
        ).required
        is True
    )


def test_a_timer_field_cannot_declare_a_default() -> None:
    from pydantic import ValidationError as PydanticValidationError

    with pytest.raises(PydanticValidationError, match="cannot declare a default"):
        EntityField(field=TIMER_FIELD, type=EntityFieldType.TIMER_DURATION, default=30)


def test_a_dry_run_synthesizes_a_plausible_elapsed_value() -> None:
    field = EntityField(
        field=TIMER_FIELD, type=EntityFieldType.TIMER_DURATION, nullable=False
    )
    assert SimulationService(
        TransitionEvaluationService(), DefinitionAnalysisService()
    ).default_value_for_field(field, prefer_concrete=True) == 0


def test_the_field_type_is_registered_under_the_catalogue_code() -> None:
    assert EntityFieldType.TIMER_DURATION == "timer_duration"


def _transition_with_required_timer() -> Transition:
    return Transition(
        key="run_to_review",
        trigger="finish",
        label="Finish",
        to_state="review",
        **{"from": "run"},
        required_fields=[RequiredField(field=TIMER_FIELD, required=True, type="timer_duration")],
    )


def _evaluate(data: dict, inputs: dict | None = None):
    """Evaluate the timer transition through the guard/required-field service."""
    return TransitionEvaluationService().evaluate(_transition_with_required_timer(), data, inputs or {})


def test_a_missing_frontend_recorded_duration_blocks_the_transition() -> None:
    blocked, _guards, missing = _evaluate({})

    assert blocked
    assert [item.field for item in missing] == [TIMER_FIELD]


def test_a_frontend_recorded_duration_lets_the_transition_through() -> None:
    blocked, _guards, missing = _evaluate({TIMER_FIELD: 90})

    assert blocked == []
    assert missing == []


def test_a_zero_second_duration_still_counts_as_recorded() -> None:
    blocked, _guards, missing = _evaluate({TIMER_FIELD: 0})

    assert blocked == []
    assert missing == []


def test_a_non_integer_duration_does_not_satisfy_the_requirement() -> None:
    blocked, _guards, missing = _evaluate({TIMER_FIELD: "ninety"})

    assert blocked
    assert [item.field for item in missing] == [TIMER_FIELD]


def test_transition_inputs_keep_the_pre_existing_required_field_contract() -> None:
    """Timer storage does not alter the existing transition-input merge behavior."""
    blocked, _guards, missing = _evaluate({}, {TIMER_FIELD: 90})

    assert blocked == []
    assert missing == []
    assert isinstance(PreflightFieldRequirement, type)
