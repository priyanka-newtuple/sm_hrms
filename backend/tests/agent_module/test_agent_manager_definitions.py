from __future__ import annotations

import pytest

from agent.models.request import AgentConstraints, AgentDefinitionCreate, AgentDefinitionUpdate
from exceptions import ValidationError

from .factories import TOOL_ID


def test_list_definitions_seeds_defaults(agent_manager, agent_repo_fake, admin_actor) -> None:
    assert agent_repo_fake.definitions == {}

    rows = agent_manager.list_definitions_for_actor(admin_actor)

    assert any(item.name == "recruitment_assistant" for item in rows)
    assert any(item.name == "platform_readonly_assistant" for item in rows)
    assert agent_repo_fake.definitions


def test_get_definition_resolves_seeded_built_in_by_id(agent_manager, agent_repo_fake, admin_actor) -> None:
    definitions = agent_manager.list_definitions_for_actor(admin_actor)
    built_in = next(item for item in definitions if item.name == "recruitment_assistant")

    resolved = agent_manager.get_definition_for_actor(admin_actor, built_in.definition_id)

    assert resolved.name == "recruitment_assistant"
    assert resolved.display_name == "Recruitment Assistant"
    assert agent_repo_fake.definitions
    assert "get_entity" not in (resolved.allowed_tools or [])
    assert "update_entity" not in (resolved.allowed_tools or [])


def test_create_definition_rejects_duplicate_names(agent_manager, admin_actor) -> None:
    request = AgentDefinitionCreate(
        name="custom_agent",
        display_name="Custom Agent",
        description="Custom agent",
        system_prompt="You are a helpful testing agent.",
        allowed_tools=[TOOL_ID],
        constraints=AgentConstraints(max_iterations=5, require_approval=[]),
        suggestions=[],
        is_active=True,
    )

    created = agent_manager.create_definition_for_actor(admin_actor, request)
    assert created.name == "custom_agent"

    with pytest.raises(ValidationError, match="already exists"):
        agent_manager.create_definition_for_actor(admin_actor, request)


def test_update_definition_rejects_non_uuid_tool_references(agent_manager, agent_repo_fake, admin_actor) -> None:
    definition = agent_repo_fake.create_definition(
        "org-1",
        {
            "name": "custom_agent",
            "display_name": "Custom Agent",
            "description": "Custom agent",
            "system_prompt": "You are a helpful testing agent.",
            "allowed_tools": [TOOL_ID],
            "constraints": {"max_iterations": 5, "require_approval": []},
            "suggestions": [],
            "is_active": True,
        },
    )

    with pytest.raises(ValidationError, match="stable UUIDs"):
        agent_manager.update_definition_for_actor(
            admin_actor,
            definition.definition_id,
            AgentDefinitionUpdate(
                display_name="Custom Agent",
                description="Custom agent",
                system_prompt="You are a helpful testing agent.",
                allowed_tools=["list_entity_types", "get_entity", "update_entity"],
                constraints=AgentConstraints(max_iterations=5, require_approval=[]),
                suggestions=[],
                is_active=True,
            ),
        )
