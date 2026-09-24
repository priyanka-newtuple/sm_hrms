"""Manager facade for platform-managed MCP capabilities."""

from __future__ import annotations

from agent.models.interface import RequestContext
from common.auth import actor_str
from exceptions import ServiceError, ValidationError
from mcp.models.request import McpCapabilityConfigurationUpdate, McpServerConfigurationUpdate
from mcp.models.response import (
    McpCapabilityResponse,
    McpServerPackageResponse,
    McpToolingOverviewResponse,
)
from mcp.services import McpRegistryService

ActorContext = dict[str, object]


class McpServiceManager:
    """Coordinate MCP package configuration APIs."""

    def __init__(
        self,
        mcp_model_service,
        database_service_manager=None,
        config=None,
        tools_service_manager=None,
        auth_service_manager=None,
    ) -> None:
        _ = database_service_manager, config, auth_service_manager
        if mcp_model_service is None:
            raise ServiceError("mcp persistence dependency is not configured")
        if tools_service_manager is None:
            raise ServiceError("tools dependency is required for MCP registry")
        self.registry_service = McpRegistryService(
            mcp_model_service,
            tools_service_manager,
        )

    def get_tooling_overview_for_actor(self, actor: ActorContext) -> McpToolingOverviewResponse:
        return self.registry_service.get_overview(self._request_context(actor))

    def update_server_configuration_for_actor(
        self,
        actor: ActorContext,
        package_id: str,
        request: McpServerConfigurationUpdate,
    ) -> McpServerPackageResponse:
        return self.registry_service.update_server_configuration(
            self._request_context(actor), package_id, request
        )

    def update_capability_configuration_for_actor(
        self,
        actor: ActorContext,
        capability_id: str,
        request: McpCapabilityConfigurationUpdate,
    ) -> McpCapabilityResponse:
        return self.registry_service.update_capability_configuration(
            self._request_context(actor), capability_id, request
        )

    def _request_context(self, actor: ActorContext) -> RequestContext:
        organization_id = self._require_actor_field(actor, "organization_id")
        roles_value = actor.get("roles")
        roles = [str(role) for role in roles_value] if isinstance(roles_value, list) else []
        return RequestContext(
            organization_id=organization_id,
            user_id=actor_str(actor, "user_id") or None,
            roles=roles,
            request_id=actor_str(actor, "request_id") or None,
            source="api",
        )

    @staticmethod
    def _require_actor_field(actor: ActorContext, field_name: str) -> str:
        value = actor_str(actor, field_name)
        if not value:
            raise ValidationError(f"Missing actor field: {field_name}")
        return value

