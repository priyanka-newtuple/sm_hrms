from __future__ import annotations

import pytest

from exceptions import PersistenceError


def test_definition_crud_lookup_and_active_filter(agent_db_model_service) -> None:
    alpha = agent_db_model_service.create_definition(
        "org-1",
        {
            "name": "alpha_agent",
            "display_name": "Alpha Agent",
            "description": "Alpha definition",
            "system_prompt": "You are alpha agent.",
            "allowed_tools": ["list_entity_types"],
            "constraints": {"max_iterations": 3, "require_approval": []},
            "suggestions": [],
            "is_active": False,
        },
    )
    beta = agent_db_model_service.create_definition(
        "org-1",
        {
            "name": "beta_agent",
            "display_name": "Beta Agent",
            "description": "Beta definition",
            "system_prompt": "You are beta agent.",
            "allowed_tools": None,
            "constraints": {"max_iterations": 4, "require_approval": []},
            "suggestions": [],
            "is_active": True,
        },
    )

    fetched = agent_db_model_service.get_definition(alpha.definition_id, "org-1")
    assert fetched is not None
    assert fetched.name == "alpha_agent"

    by_name = agent_db_model_service.get_definition_by_name("org-1", "beta_agent")
    assert by_name is not None
    assert by_name.definition_id == beta.definition_id

    active_rows = agent_db_model_service.list_definitions("org-1", active_only=True)
    all_rows = agent_db_model_service.list_definitions("org-1", active_only=False)
    assert [item.name for item in active_rows] == ["beta_agent"]
    assert [item.display_name for item in all_rows] == ["Alpha Agent", "Beta Agent"]

    updated = agent_db_model_service.update_definition(
        alpha.definition_id,
        "org-1",
        {"is_active": True, "allowed_tools": ["list_entity_types", "get_entity"]},
    )
    assert updated is not None
    assert updated.is_active is True
    assert updated.allowed_tools == ["list_entity_types", "get_entity"]

    deleted = agent_db_model_service.delete_definition(beta.definition_id, "org-1")
    assert deleted is True
    assert agent_db_model_service.get_definition(beta.definition_id, "org-1") is None


def test_definition_create_respects_explicit_identifier_and_rejects_duplicates(agent_db_model_service) -> None:
    created = agent_db_model_service.create_definition(
        "org-1",
        {
            "definition_id": "fixed-definition-id",
            "name": "unique_agent",
            "display_name": "Unique Agent",
            "description": "Unique definition",
            "system_prompt": "You are unique agent.",
            "allowed_tools": [],
            "constraints": {"max_iterations": 2, "require_approval": []},
            "suggestions": [],
        },
    )
    assert created.definition_id == "fixed-definition-id"

    with pytest.raises(PersistenceError):
        agent_db_model_service.create_definition(
            "org-1",
            {
                "name": "unique_agent",
                "display_name": "Duplicate Agent",
                "description": "Duplicate definition",
                "system_prompt": "You are duplicate agent.",
                "allowed_tools": [],
                "constraints": {"max_iterations": 2, "require_approval": []},
                "suggestions": [],
            },
        )
