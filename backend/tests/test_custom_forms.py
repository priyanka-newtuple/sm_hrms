"""Resolving a record's custom forms.

The fakes here mirror the real signatures: `list_method_pins` returns
(state_key, method_id, version_id) tuples, `get_version` and
`list_version_fields` take keyword arguments, and `run_for_entity` returns
something shaped like a ConnectorCallResult. A fake that invents a method the
real class lacks is how this kind of wiring ships broken.
"""

from __future__ import annotations

from types import SimpleNamespace as NS

import pytest

from custom_forms.manager import (
    RESOLVED_STATE_KEY,
    RESOLVED_WORKFLOW_KEY,
    CustomFormsServiceManager,
)
from custom_forms.services.mapping import schema_without_values, value_key, values_from_sources
from exceptions import NotFoundError

ORG = "org-1"
MACHINE = "machine-1"
OTHER_MACHINE = "machine-2"
STATE = "Screening"
OTHER_STATE = "Review"
DYNAMIC_METHOD = "method-dynamic"
PLAIN_METHOD = "method-plain"

FORM = {
    "sections": [
        {
            "id": "s1",
            "title": "Certificate",
            "cells": [
                {"id": "cert_id", "label": "Certificate ID", "type": "text", "value": "CPCN-1"}
            ],
        }
    ],
    "calculations": {},
}


def _manager(
    *,
    pins: list[tuple[str, str, str]],
    fields_by_version: dict[str, list],
    connector_by_version: dict[str, str | None],
    call_result=None,
    on_call=None,
) -> CustomFormsServiceManager:
    calls: list[dict] = []

    def _run(**kwargs):
        calls.append(kwargs)
        if on_call is not None:
            return on_call(**kwargs)
        return call_result

    manager = CustomFormsServiceManager(
        workflow_db_model_service=NS(list_method_pins=lambda **kw: pins),
        method_library_db_model_service=NS(
            list_version_fields=lambda **kw: fields_by_version.get(kw["method_version_id"], []),
            get_version=lambda **kw: NS(connector_id=connector_by_version.get(kw["version_id"])),
        ),
        connectors_service_manager=NS(run_for_entity=_run),
    )
    manager.calls = calls
    return manager


def _ok(payload) -> NS:
    return NS(ok=True, response_json=payload, error=None)


def _resolved_on(machine: str, state: str) -> dict:
    return {**FORM, RESOLVED_WORKFLOW_KEY: machine, RESOLVED_STATE_KEY: state}


def test_a_pinned_method_with_a_connector_and_no_fields_is_dynamic() -> None:
    manager = _manager(
        pins=[(STATE, DYNAMIC_METHOD, "v1")],
        fields_by_version={"v1": []},
        connector_by_version={"v1": "connector-1"},
    )

    found = manager.connector_ids_for_state(
        organization_id=ORG, workflow_state_machine_id=MACHINE, state_key=STATE
    )

    assert found == {DYNAMIC_METHOD: "connector-1"}


def test_a_method_with_fields_is_not_dynamic() -> None:
    """Its fields already publish, so it must not also render a fetched form."""
    manager = _manager(
        pins=[(STATE, PLAIN_METHOD, "v2")],
        fields_by_version={"v2": [NS(field_key="notes")]},
        connector_by_version={"v2": "connector-1"},
    )

    assert (
        manager.connector_ids_for_state(
            organization_id=ORG, workflow_state_machine_id=MACHINE, state_key=STATE
        )
        == {}
    )


def test_a_method_without_a_connector_is_not_dynamic() -> None:
    manager = _manager(
        pins=[(STATE, PLAIN_METHOD, "v3")],
        fields_by_version={"v3": []},
        connector_by_version={"v3": None},
    )

    assert (
        manager.connector_ids_for_state(
            organization_id=ORG, workflow_state_machine_id=MACHINE, state_key=STATE
        )
        == {}
    )


def test_pins_for_other_states_are_ignored() -> None:
    manager = _manager(
        pins=[("Intake", DYNAMIC_METHOD, "v1")],
        fields_by_version={"v1": []},
        connector_by_version={"v1": "connector-1"},
    )

    assert (
        manager.connector_ids_for_state(
            organization_id=ORG, workflow_state_machine_id=MACHINE, state_key=STATE
        )
        == {}
    )


def test_a_missing_form_is_fetched_and_keyed_by_method() -> None:
    manager = _manager(
        pins=[(STATE, DYNAMIC_METHOD, "v1")],
        fields_by_version={"v1": []},
        connector_by_version={"v1": "connector-1"},
        call_result=_ok(FORM),
    )

    resolved = manager.resolve_for_record(
        organization_id=ORG,
        workflow_state_machine_id=MACHINE,
        state_key=STATE,
        entity_values={"identifier": "client166"},
        stored=None,
    )

    assert set(resolved) == {DYNAMIC_METHOD}
    assert resolved[DYNAMIC_METHOD]["sections"][0]["cells"][0]["id"] == "cert_id"


def test_a_form_already_stored_is_not_fetched_again() -> None:
    """Fetched once per record, as the old grid form instance was."""
    manager = _manager(
        pins=[(STATE, DYNAMIC_METHOD, "v1")],
        fields_by_version={"v1": []},
        connector_by_version={"v1": "connector-1"},
        call_result=_ok(FORM),
    )

    resolved = manager.resolve_for_record(
        organization_id=ORG,
        workflow_state_machine_id=MACHINE,
        state_key=STATE,
        entity_values={},
        stored={DYNAMIC_METHOD: FORM},
    )

    assert resolved is None
    assert manager.calls == []


def test_a_fetched_form_records_the_state_it_was_resolved_for() -> None:
    manager = _manager(
        pins=[(STATE, DYNAMIC_METHOD, "v1")],
        fields_by_version={"v1": []},
        connector_by_version={"v1": "connector-1"},
        call_result=_ok(FORM),
    )

    resolved = manager.resolve_for_record(
        organization_id=ORG,
        workflow_state_machine_id=MACHINE,
        state_key=STATE,
        entity_values={},
        stored=None,
    )

    assert resolved[DYNAMIC_METHOD][RESOLVED_WORKFLOW_KEY] == MACHINE
    assert resolved[DYNAMIC_METHOD][RESOLVED_STATE_KEY] == STATE


def test_a_form_stored_for_the_same_state_is_not_fetched_again() -> None:
    manager = _manager(
        pins=[(STATE, DYNAMIC_METHOD, "v1")],
        fields_by_version={"v1": []},
        connector_by_version={"v1": "connector-1"},
        call_result=_ok(FORM),
    )

    resolved = manager.resolve_for_record(
        organization_id=ORG,
        workflow_state_machine_id=MACHINE,
        state_key=STATE,
        entity_values={},
        stored={DYNAMIC_METHOD: _resolved_on(MACHINE, STATE)},
    )

    assert resolved is None
    assert manager.calls == []


def test_a_form_stored_for_another_state_is_fetched_again() -> None:
    """One method pinned to several states answers differently per state."""
    manager = _manager(
        pins=[(STATE, DYNAMIC_METHOD, "v1"), (OTHER_STATE, DYNAMIC_METHOD, "v1")],
        fields_by_version={"v1": []},
        connector_by_version={"v1": "connector-1"},
        call_result=_ok(FORM),
    )

    resolved = manager.resolve_for_record(
        organization_id=ORG,
        workflow_state_machine_id=MACHINE,
        state_key=OTHER_STATE,
        entity_values={},
        stored={DYNAMIC_METHOD: _resolved_on(MACHINE, STATE)},
    )

    assert len(manager.calls) == 1
    assert resolved[DYNAMIC_METHOD][RESOLVED_STATE_KEY] == OTHER_STATE


def test_another_states_form_is_dropped_when_its_refetch_fails() -> None:
    """Absent beats stale: the earlier state's form must not pass for this one."""
    manager = _manager(
        pins=[(STATE, DYNAMIC_METHOD, "v1"), (OTHER_STATE, DYNAMIC_METHOD, "v1")],
        fields_by_version={"v1": []},
        connector_by_version={"v1": "connector-1"},
        call_result=NS(ok=False, response_json=None, error="request timed out"),
    )

    resolved = manager.resolve_for_record(
        organization_id=ORG,
        workflow_state_machine_id=MACHINE,
        state_key=OTHER_STATE,
        entity_values={},
        stored={DYNAMIC_METHOD: _resolved_on(MACHINE, STATE)},
    )

    assert resolved == {}


def test_another_enrolments_form_is_left_alone() -> None:
    """Two workflows sharing one dynamic method keep the first form, as before."""
    manager = _manager(
        pins=[(OTHER_STATE, DYNAMIC_METHOD, "v1")],
        fields_by_version={"v1": []},
        connector_by_version={"v1": "connector-1"},
        call_result=_ok(FORM),
    )

    resolved = manager.resolve_for_record(
        organization_id=ORG,
        workflow_state_machine_id=OTHER_MACHINE,
        state_key=OTHER_STATE,
        entity_values={},
        stored={DYNAMIC_METHOD: _resolved_on(MACHINE, STATE)},
    )

    assert resolved is None
    assert manager.calls == []


def test_record_values_reach_the_connector_as_placeholders() -> None:
    """So one connector can ask the external system about this record."""
    manager = _manager(
        pins=[(STATE, DYNAMIC_METHOD, "v1")],
        fields_by_version={"v1": []},
        connector_by_version={"v1": "connector-1"},
        call_result=_ok(FORM),
    )

    manager.resolve_for_record(
        organization_id=ORG,
        workflow_state_machine_id=MACHINE,
        state_key=STATE,
        entity_values={"identifier": "client166", "rows": [1, 2], "blank": None},
        stored=None,
    )

    sent = manager.calls[0]["entity_values"]
    assert sent == {"identifier": "client166"}


def test_a_deleted_connector_leaves_the_form_absent_rather_than_failing_the_record() -> None:
    manager = _manager(
        pins=[(STATE, DYNAMIC_METHOD, "v1")],
        fields_by_version={"v1": []},
        connector_by_version={"v1": "connector-1"},
        on_call=lambda **kw: (_ for _ in ()).throw(NotFoundError("Connector not found")),
    )

    assert (
        manager.resolve_for_record(
            organization_id=ORG,
            workflow_state_machine_id=MACHINE,
            state_key=STATE,
            entity_values={},
            stored=None,
        )
        is None
    )


def test_an_unsuccessful_call_leaves_the_form_absent() -> None:
    """Transport failures come back as ok=False, never as an exception."""
    manager = _manager(
        pins=[(STATE, DYNAMIC_METHOD, "v1")],
        fields_by_version={"v1": []},
        connector_by_version={"v1": "connector-1"},
        call_result=NS(ok=False, response_json=None, error="request timed out"),
    )

    assert (
        manager.resolve_for_record(
            organization_id=ORG,
            workflow_state_machine_id=MACHINE,
            state_key=STATE,
            entity_values={},
            stored=None,
        )
        is None
    )


def test_a_programming_error_is_not_swallowed() -> None:
    """Best-effort covers persistence and connector failures, not real bugs."""
    manager = _manager(
        pins=[(STATE, DYNAMIC_METHOD, "v1")],
        fields_by_version={"v1": []},
        connector_by_version={"v1": "connector-1"},
        on_call=lambda **kw: (_ for _ in ()).throw(TypeError("bad call")),
    )

    with pytest.raises(TypeError):
        manager.resolve_for_record(
            organization_id=ORG,
            workflow_state_machine_id=MACHINE,
            state_key=STATE,
            entity_values={},
            stored=None,
        )


def test_an_invalid_response_is_rejected_rather_than_stored() -> None:
    """The validator is the only thing between an external system and the browser."""
    manager = _manager(
        pins=[(STATE, DYNAMIC_METHOD, "v1")],
        fields_by_version={"v1": []},
        connector_by_version={"v1": "connector-1"},
        call_result=_ok({"sections": "not a list"}),
    )

    assert (
        manager.resolve_for_record(
            organization_id=ORG,
            workflow_state_machine_id=MACHINE,
            state_key=STATE,
            entity_values={},
            stored=None,
        )
        is None
    )


def test_no_pins_means_no_work() -> None:
    manager = _manager(pins=[], fields_by_version={}, connector_by_version={})

    assert (
        manager.resolve_for_record(
            organization_id=ORG,
            workflow_state_machine_id=MACHINE,
            state_key=STATE,
            entity_values={},
            stored=None,
        )
        is None
    )
    assert manager.calls == []


# ── Reading a results body into data fields ────────────────────────────────


def _schema(rows: list[dict], columns: list[dict] | None = None) -> dict:
    return {
        "sections": [
            {
                "id": "block_3",
                "title": "Block 3",
                "cells": [
                    {
                        "id": "f_block_3",
                        "type": "table",
                        "label": "Block 3",
                        "source": "blocks.block_3",
                        "editable": True,
                        "table_config": {
                            "rows": rows,
                            "columns": columns
                            or [
                                {"id": "line", "type": "text", "readonly": True},
                                {"id": "description", "type": "text", "readonly": True},
                                {"id": "value", "type": "currency"},
                            ],
                        },
                    }
                ],
            }
        ],
        "calculations": {},
    }


def test_a_grid_answer_becomes_one_flat_data_key() -> None:
    schema = _schema([{"id": "301", "line": "301", "label": "Bad debt %"}])
    body = {"blocks": {"block_3": [{"line": "301", "value": 12.5}]}}

    values, unresolved = values_from_sources(schema, body)

    assert values == {"f_block_3__301__value": 12.5}
    assert unresolved == []


def test_the_key_never_uses_a_dot() -> None:
    """`$entity.<field>` and the source-path reader both split on dots."""
    assert value_key("f_block_3", "301", "value") == "f_block_3__301__value"
    assert "." not in value_key("f_block_3", "303.1a", "value").replace("303.1a", "")


def test_only_the_schemas_own_rows_are_read() -> None:
    """A body for another report cannot add rows or relabel the grid."""
    schema = _schema([{"id": "301", "line": "301", "label": "Bad debt %"}])
    body = {"blocks": {"block_3": [{"line": "113", "value": "q1"}]}}

    values, unresolved = values_from_sources(schema, body)

    assert values == {}
    assert unresolved == ["f_block_3:blocks.block_3"]


def test_a_readonly_column_is_never_written() -> None:
    schema = _schema([{"id": "301", "line": "301", "label": "Bad debt %"}])
    body = {"blocks": {"block_3": [{"line": "301", "description": "x", "value": 1.0}]}}

    values, _ = values_from_sources(schema, body)

    assert values == {"f_block_3__301__value": 1.0}


def test_a_value_someone_entered_is_left_alone() -> None:
    schema = _schema([{"id": "301", "line": "301", "label": "Bad debt %"}])
    body = {"blocks": {"block_3": [{"line": "301", "value": 12.5}]}}

    values, _ = values_from_sources(schema, body, {"f_block_3__301__value": 99.0})

    assert values == {}


def test_a_display_only_cell_is_skipped() -> None:
    schema = _schema([{"id": "301", "line": "301"}])
    schema["sections"][0]["cells"][0]["editable"] = False
    body = {"blocks": {"block_3": [{"line": "301", "value": 1}]}}

    assert values_from_sources(schema, body) == ({}, [])


def test_an_unresolvable_source_is_reported_not_written() -> None:
    schema = _schema([{"id": "301", "line": "301"}])

    values, unresolved = values_from_sources(schema, {"report": {}})

    assert values == {}
    assert unresolved == ["f_block_3:blocks.block_3"]


def test_a_fetched_form_is_stored_without_its_answers() -> None:
    """The schema column must not shadow the values in `data`."""
    fetched = {
        "sections": [
            {
                "id": "block_3",
                "cells": [
                    {
                        "id": "f_block_3",
                        "type": "table",
                        "value": [{"id": "301", "value": 12.5}],
                        "source": "blocks.block_3",
                        "config": {"table_config": {"rows": [{"id": "301", "value": 12.5}]}},
                    }
                ],
            }
        ]
    }

    stored = schema_without_values(fetched)

    cell = stored["sections"][0]["cells"][0]
    assert "value" not in cell
    assert "config" not in cell
    assert cell["table_config"]["rows"] == [{"id": "301"}]
