"""Unit tests for EntitiesServiceManager.get_form_config_definition.

Backs the `get_form_schema` MCP tool: agents call the tool to discover the
exact field *keys* an entity's ``data`` is stored under. These tests isolate
the field-merge/mapping logic by stubbing the DB-backed field fetch.
"""

from __future__ import annotations

from entities.manager import EntitiesServiceManager


def _bare_manager() -> EntitiesServiceManager:
    """Manager instance with no DB wiring, for testing pure mapping logic.

    ``get_form_config_definition`` only reaches ``_active_schema_fields_for_type_name``
    (stubbed in each test) plus module-level contract types, so we skip the
    DB-dependent ``__init__`` entirely.
    """
    return EntitiesServiceManager.__new__(EntitiesServiceManager)


def test_get_form_config_definition_maps_form_fields_to_keys(monkeypatch) -> None:
    """Merged form fields become a FormConfigContract keyed by the field key."""
    manager = _bare_manager()

    sample_fields = [
        {"field": "title", "type": "text", "required": True, "description": "Title"},
        {
            "field": "testingmultiselect",
            "type": "multi_select",
            "required": False,
            "enum_values": ["Low", "Medium", "High"],
            "description": "Priority",
        },
        # Duplicate key across two linked schemas — should be de-duplicated.
        {"field": "title", "type": "text", "required": True},
    ]
    monkeypatch.setattr(
        manager,
        "_active_schema_fields_for_type_name",
        lambda org, name: list(sample_fields),
    )

    config = manager.get_form_config_definition(
        organization_id="org-1", form_key="project_task"
    )

    assert config is not None
    assert config.form_key == "project_task"
    names = [f.name for f in config.fields]
    assert names == ["title", "testingmultiselect"]  # de-duplicated, order preserved
    priority = next(f for f in config.fields if f.name == "testingmultiselect")
    assert priority.field_type == "multi_select"
    assert priority.options == ("Low", "Medium", "High")


def test_get_form_config_definition_returns_none_without_fields(monkeypatch) -> None:
    """No configured fields → None (tool surfaces a not-found)."""
    manager = _bare_manager()
    monkeypatch.setattr(
        manager, "_active_schema_fields_for_type_name", lambda org, name: []
    )
    assert (
        manager.get_form_config_definition(organization_id="org-1", form_key="ghost")
        is None
    )
