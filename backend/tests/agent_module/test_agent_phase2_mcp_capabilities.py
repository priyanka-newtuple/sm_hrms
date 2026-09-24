from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from agent.manager import AgentServiceManager
from agent.models.interface import AgentExecutionContext, RequestContext, RuntimeContext
from agent.models.request import AgentDefinitionCreate
from agent.services.capabilities import AgentCapabilityResolver
from exceptions import ValidationError
from mcp.db_models import (
    McpCapabilityConfigurationModel,
    McpCapabilityModel,
    McpModelService,
    McpServerConfigurationModel,
    McpServerPackageModel,
)
from mcp.models.request import McpCapabilityConfigurationUpdate
from mcp.services.registry import McpRegistryService
from tools.models.interface import ToolExecutionResult

from .fakes import InMemoryAgentModelServiceFake, StubLlmManager


@pytest.fixture
def mcp_model_service(sqlite_database_service_manager):
    McpServerPackageModel.metadata.create_all(
        sqlite_database_service_manager.postgres_db_service().engine,
        tables=[
            McpServerPackageModel.__table__,
            McpServerConfigurationModel.__table__,
            McpCapabilityModel.__table__,
            McpCapabilityConfigurationModel.__table__,
        ],
    )
    return McpModelService(sqlite_database_service_manager)


@pytest.fixture
def mcp_registry(mcp_model_service, tools_manager):
    return McpRegistryService(mcp_model_service, tools_manager)


def test_platform_mcp_package_seeds_internal_capabilities(admin_actor, mcp_registry):
    overview = mcp_registry.get_overview(
        AgentServiceManager(
            InMemoryAgentModelServiceFake(),
            llm_service_manager=StubLlmManager(),
        )._request_context(admin_actor)
    )

    assert [package.server_key for package in overview.packages] == ["platform_tools"]
    capabilities = {capability.capability_key: capability for capability in overview.capabilities}
    assert {"list_entity_types", "read_document", "add_stage_comment"} <= set(capabilities)
    assert capabilities["list_entity_types"].is_enabled is True
    assert capabilities["add_stage_comment"].is_mutating is True
    assert capabilities["add_stage_comment"].requires_approval is True


def test_agent_definition_rejects_disabled_capability(
    admin_actor,
    mcp_registry,
    tools_manager,
):
    context = AgentServiceManager(
        InMemoryAgentModelServiceFake(),
        llm_service_manager=StubLlmManager(),
    )._request_context(admin_actor)
    capability = next(
        item for item in mcp_registry.list_capabilities(context) if item.tool_id == "list_entity_types"
    )
    mcp_registry.update_capability_configuration(
        context,
        capability.id,
        McpCapabilityConfigurationUpdate(
            is_enabled=False,
            requires_approval=capability.requires_approval,
        ),
    )
    manager = AgentServiceManager(
        InMemoryAgentModelServiceFake(),
        tools_service_manager=tools_manager,
        mcp_registry_service=mcp_registry,
        llm_service_manager=StubLlmManager(),
    )

    with pytest.raises(Exception, match="enabled MCP capabilities"):
        manager.create_definition_for_actor(
            admin_actor,
            AgentDefinitionCreate(
                name="tool_user",
                display_name="Tool User",
                system_prompt="Use tools.",
                allowed_tools=[capability.id],
            ),
        )


def test_legacy_tool_name_normalizes_to_capability_id(
    admin_actor,
    mcp_registry,
    tools_manager,
):
    manager = AgentServiceManager(
        InMemoryAgentModelServiceFake(),
        tools_service_manager=tools_manager,
        mcp_registry_service=mcp_registry,
        llm_service_manager=StubLlmManager(),
    )
    created = manager.create_definition_for_actor(
        admin_actor,
        AgentDefinitionCreate(
            name="entity_lister",
            display_name="Entity Lister",
            system_prompt="List entity types.",
            allowed_tools=["list_entity_types"],
        ),
    )

    assert len(created.allowed_tools or []) == 1
    assert created.allowed_tools[0] != "list_entity_types"


def test_sdk_tool_returns_structured_error_payload_when_tool_execution_fails() -> None:
    class Registry:
        def list_enabled_capabilities(self, context, capability_ids):  # noqa: ANN001
            _ = context, capability_ids
            return [
                SimpleNamespace(
                    id="cap-create-entity",
                    tool_id="create_entity",
                    capability_key="entity.create",
                    description="Create entity",
                    input_schema={"type": "object"},
                )
            ]

        def validate_enabled_capability_ids(self, context, capability_ids):  # noqa: ANN001
            _ = context, capability_ids

    class Tools:
        def execute_tool(self, tool_name, arguments, context):  # noqa: ANN001
            _ = tool_name, arguments, context
            raise ValidationError("Identifier is required")

    resolver = AgentCapabilityResolver(Registry(), Tools())
    request_context = RequestContext(
        organization_id="org-1",
        user_id="admin-user",
        roles=["admin"],
        request_id="req-1",
    )
    execution_context = AgentExecutionContext(
        request=request_context,
        runtime=RuntimeContext(
            organization_id="org-1",
            user_id="admin-user",
            roles=["admin"],
            request_id="req-1",
        ),
    )

    sdk_tool = resolver.build_sdk_tools(
        request_context,
        ["cap-create-entity"],
        execution_context,
        run_id="run-1",
        session_id="session-1",
    )[0]

    raw_output = asyncio.run(
        sdk_tool.on_invoke_tool(
            None,
            json.dumps({"entity_type_id": "et-application", "data": {}}),
        )
    )
    output = json.loads(raw_output)

    assert output == {
        "success": False,
        "tool_name": "create_entity",
        "output": {},
        "error": "Identifier is required",
        "recoverable": True,
    }


def test_sdk_tool_returns_structured_success_payload_when_tool_execution_succeeds() -> None:
    class Registry:
        def list_enabled_capabilities(self, context, capability_ids):  # noqa: ANN001
            _ = context, capability_ids
            return [
                SimpleNamespace(
                    id="cap-list-entity-types",
                    tool_id="list_entity_types",
                    capability_key="entity.list_types",
                    description="List entity types",
                    input_schema={"type": "object"},
                )
            ]

        def validate_enabled_capability_ids(self, context, capability_ids):  # noqa: ANN001
            _ = context, capability_ids

    class Tools:
        def execute_tool(self, tool_name, arguments, context):  # noqa: ANN001
            _ = arguments, context
            return ToolExecutionResult(
                success=True,
                tool_name=tool_name,
                output={"items": [{"entity_type_id": "et-application"}]},
                duration_ms=7,
            )

    resolver = AgentCapabilityResolver(Registry(), Tools())
    request_context = RequestContext(organization_id="org-1", user_id="admin-user")
    execution_context = AgentExecutionContext(
        request=request_context,
        runtime=RuntimeContext(organization_id="org-1", user_id="admin-user"),
    )

    sdk_tool = resolver.build_sdk_tools(
        request_context,
        ["cap-list-entity-types"],
        execution_context,
        run_id="run-1",
        session_id=None,
    )[0]

    raw_output = asyncio.run(sdk_tool.on_invoke_tool(None, "{}"))
    output = json.loads(raw_output)

    assert output["success"] is True
    assert output["tool_name"] == "list_entity_types"
    assert output["output"] == {"items": [{"entity_type_id": "et-application"}]}
