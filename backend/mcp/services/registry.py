"""Registry service for the platform-shipped MCP server package."""

from __future__ import annotations

import uuid
from typing import Iterable

from agent.models.interface import RequestContext
from exceptions import NotFoundError, ValidationError
from mcp.models.interface import (
    McpCapabilityContract,
    McpCapabilityView,
    McpServerConfigurationContract,
    McpServerPackageContract,
)
from mcp.models.request import McpCapabilityConfigurationUpdate, McpServerConfigurationUpdate
from mcp.models.response import (
    McpCapabilityResponse,
    McpServerPackageResponse,
    McpToolingOverviewResponse,
)
from tools.models.interface import ToolDescriptorContract

PLATFORM_TOOLS_SERVER_KEY = "platform_tools"
PLATFORM_TOOLS_SERVER_ID = str(
    uuid.uuid5(uuid.NAMESPACE_URL, f"mcp-server-package:{PLATFORM_TOOLS_SERVER_KEY}")
)
CONNECTOR_TOOLS_SERVER_KEY = "connector_tools"
CONNECTOR_TOOLS_SERVER_ID = str(
    uuid.uuid5(uuid.NAMESPACE_URL, f"mcp-server-package:{CONNECTOR_TOOLS_SERVER_KEY}")
)
CAPABILITY_NAMESPACE = uuid.NAMESPACE_URL


class McpRegistryService:
    """Own packaged MCP capability metadata and org-level toggles."""

    def __init__(self, mcp_model_service, tools_service_manager) -> None:  # noqa: ANN001
        self.mcp_model_service = mcp_model_service
        self.tools_service_manager = tools_service_manager

    def ensure_platform_package_seeded(self) -> None:
        package = self.mcp_model_service.upsert_server_package(
            {
                "id": PLATFORM_TOOLS_SERVER_ID,
                "server_key": PLATFORM_TOOLS_SERVER_KEY,
                "name": "Platform Tools",
                "description": "Standard Newtuple MCP package for internal platform tools.",
                "version": "1",
                "is_platform_managed": True,
                "is_active": True,
                "metadata": {"source": "platform"},
            }
        )
        descriptors = self._seed_descriptors()
        for descriptor in descriptors:
            self.mcp_model_service.upsert_capability(
                self._capability_payload(package, descriptor)
            )

    def ensure_connector_package_seeded(self) -> McpServerPackageContract:
        """Ensure the Connector Tools server package exists in the MCP registry.

        Returns the upserted package contract. Connector-backed tools are
        registered under this package so the MCP runtime can discover them.
        """
        return self.mcp_model_service.upsert_server_package(
            {
                "id": CONNECTOR_TOOLS_SERVER_ID,
                "server_key": CONNECTOR_TOOLS_SERVER_KEY,
                "name": "Connector Tools",
                "description": "Organization connectors exposed as agent tools.",
                "version": "1",
                "is_platform_managed": False,
                "is_active": True,
                "metadata": {"source": "connectors"},
            }
        )

    def get_overview(self, context: RequestContext) -> McpToolingOverviewResponse:
        self.ensure_platform_package_seeded()
        self._sync_connector_capabilities(context)
        packages = self._visible_packages(context)
        return McpToolingOverviewResponse(
            packages=[self._package_response(context, package) for package in packages],
            capabilities=[
                McpCapabilityResponse.model_validate(item)
                for item in self.list_capabilities(context)
            ],
        )

    def update_server_configuration(
        self,
        context: RequestContext,
        package_id: str,
        request: McpServerConfigurationUpdate,
    ) -> McpServerPackageResponse:
        self.ensure_platform_package_seeded()
        package = self.mcp_model_service.get_server_package(package_id)
        if package is None or not package.is_active:
            raise NotFoundError("MCP server package not found")
        self.mcp_model_service.upsert_server_configuration(
            context.organization_id,
            package_id,
            {
                "is_enabled": request.is_enabled,
                "config": request.config,
                "actor_id": context.user_id,
            },
        )
        return self._package_response(context, package)

    def update_capability_configuration(
        self,
        context: RequestContext,
        capability_id: str,
        request: McpCapabilityConfigurationUpdate,
    ) -> McpCapabilityResponse:
        self.ensure_platform_package_seeded()
        self._sync_connector_capabilities(context)
        capability = self._capability_for_context(context, capability_id)
        if capability is None or not capability.is_active:
            raise NotFoundError("MCP capability not found")
        requires_approval = (
            capability.default_requires_approval
            if request.requires_approval is None
            else request.requires_approval
        )
        self.mcp_model_service.upsert_capability_configuration(
            context.organization_id,
            capability_id,
            {
                "is_enabled": request.is_enabled,
                "requires_approval": requires_approval,
                "config": request.config,
                "integration_ref": request.integration_ref,
                "actor_id": context.user_id,
            },
        )
        view = self._capability_view(context, capability)
        return McpCapabilityResponse.model_validate(view)

    def list_capabilities(self, context: RequestContext) -> list[McpCapabilityView]:
        self.ensure_platform_package_seeded()
        self._sync_connector_capabilities(context)
        capabilities = self._visible_capability_contracts(context)
        return [self._capability_view(context, capability) for capability in capabilities]

    def list_enabled_capabilities(
        self, context: RequestContext, capability_ids: list[str] | None = None
    ) -> list[McpCapabilityView]:
        requested = set(capability_ids or [])
        views = self.list_capabilities(context)
        if requested:
            views = [view for view in views if view.id in requested]
        return [
            view
            for view in views
            if view.package_enabled and view.is_enabled and view.is_active
        ]

    def validate_enabled_capability_ids(
        self, context: RequestContext, capability_ids: list[str]
    ) -> None:
        if not capability_ids:
            return
        requested = set(capability_ids)
        enabled = {view.id for view in self.list_enabled_capabilities(context, capability_ids)}
        missing = sorted(requested - enabled)
        if missing:
            raise ValidationError(
                "Agent tools must reference enabled MCP capabilities"
            )

    def get_tool_name(self, capability_id: str) -> str:
        capability = self.mcp_model_service.get_capability(capability_id)
        if capability is None:
            raise NotFoundError("MCP capability not found")
        return capability.tool_id

    def _visible_packages(
        self,
        context: RequestContext,
    ) -> list[McpServerPackageContract]:
        package_map = {
            package.id: package
            for package in self.mcp_model_service.list_server_packages(active_only=True)
        }
        visible_capabilities = self._visible_capability_contracts(context)
        package_ids = {capability.server_package_id for capability in visible_capabilities}
        return [package for package_id, package in package_map.items() if package_id in package_ids]

    def _visible_capability_contracts(
        self,
        context: RequestContext,
    ) -> list[McpCapabilityContract]:
        capabilities = self.mcp_model_service.list_capabilities(active_only=False)
        visible: list[McpCapabilityContract] = []
        for capability in capabilities:
            if not capability.is_active:
                continue
            metadata = dict(capability.metadata or {})
            if metadata.get("source") == "connector":
                if str(metadata.get("organization_id") or "") != context.organization_id:
                    continue
            visible.append(capability)
        return visible

    def _capability_for_context(
        self,
        context: RequestContext,
        capability_id: str,
    ) -> McpCapabilityContract | None:
        for capability in self._visible_capability_contracts(context):
            if capability.id == capability_id:
                return capability
        return None

    def _sync_connector_capabilities(self, context: RequestContext) -> None:
        package = self.ensure_connector_package_seeded()
        desired = {
            descriptor.name: descriptor
            for descriptor in self.tools_service_manager.list_connector_tool_descriptors(
                context.organization_id
            )
        }
        existing = [
            capability
            for capability in self.mcp_model_service.list_capabilities(package.id, active_only=False)
            if str((capability.metadata or {}).get("organization_id") or "") == context.organization_id
        ]

        for descriptor in desired.values():
            self.mcp_model_service.upsert_capability(
                self._connector_capability_payload(context, package, descriptor)
            )

        for capability in existing:
            if capability.tool_id in desired:
                continue
            self.mcp_model_service.upsert_capability(
                {
                    "id": capability.id,
                    "server_package_id": capability.server_package_id,
                    "capability_key": capability.capability_key,
                    "tool_id": capability.tool_id,
                    "display_name": capability.display_name,
                    "description": capability.description,
                    "input_schema": dict(capability.input_schema or {}),
                    "output_schema": capability.output_schema,
                    "category": capability.category,
                    "default_requires_approval": capability.default_requires_approval,
                    "default_is_mutating": capability.default_is_mutating,
                    "is_active": False,
                    "metadata": dict(capability.metadata or {}),
                }
            )

    def _package_response(
        self, context: RequestContext, package: McpServerPackageContract
    ) -> McpServerPackageResponse:
        config = self._server_config(context, package)
        return McpServerPackageResponse(
            id=package.id,
            server_key=package.server_key,
            name=package.name,
            description=package.description,
            version=package.version,
            is_platform_managed=package.is_platform_managed,
            is_active=package.is_active,
            is_enabled=config.is_enabled,
            config=config.config,
        )

    def _server_config(
        self, context: RequestContext, package: McpServerPackageContract
    ) -> McpServerConfigurationContract:
        existing = self.mcp_model_service.get_server_configuration(
            context.organization_id, package.id
        )
        if existing is not None:
            return existing
        return self.mcp_model_service.upsert_server_configuration(
            context.organization_id,
            package.id,
            {"is_enabled": True, "config": {}, "actor_id": context.user_id},
        )

    def _capability_view(
        self, context: RequestContext, capability: McpCapabilityContract
    ) -> McpCapabilityView:
        package = self.mcp_model_service.get_server_package(capability.server_package_id)
        if package is None:
            raise NotFoundError("MCP server package not found")
        server_config = self._server_config(context, package)
        config = self.mcp_model_service.get_capability_configuration(
            context.organization_id, capability.id
        )
        if config is None:
            config = self.mcp_model_service.upsert_capability_configuration(
                context.organization_id,
                capability.id,
                {
                    "is_enabled": self._default_capability_enabled(capability),
                    "requires_approval": capability.default_requires_approval,
                    "config": {},
                    "actor_id": context.user_id,
                },
            )
        return McpCapabilityView(
            id=capability.id,
            server_package_id=capability.server_package_id,
            capability_key=capability.capability_key,
            tool_id=capability.tool_id,
            display_name=capability.display_name,
            description=capability.description,
            input_schema=capability.input_schema,
            output_schema=capability.output_schema,
            category=capability.category,
            is_mutating=capability.default_is_mutating,
            requires_approval=config.requires_approval,
            package_enabled=server_config.is_enabled,
            is_enabled=config.is_enabled,
            is_active=capability.is_active and bool(package.is_active),
        )

    @staticmethod
    def _default_capability_enabled(capability: McpCapabilityContract) -> bool:
        return bool(capability.is_active and not capability.default_is_mutating)

    def _seed_descriptors(self) -> Iterable[ToolDescriptorContract]:
        # Which tools become MCP capabilities is decided by each tool's own
        # ``mcp_exposed`` flag in the canonical tools catalog, not by a list
        # maintained here.
        catalog = self.tools_service_manager.get_catalog().tools
        return [descriptor for descriptor in catalog if descriptor.mcp_exposed]

    @staticmethod
    def _capability_payload(
        package: McpServerPackageContract,
        descriptor: ToolDescriptorContract,
    ) -> dict[str, object]:
        is_mutating = descriptor.is_mutating
        return {
            "id": str(
                uuid.uuid5(
                    CAPABILITY_NAMESPACE,
                    f"mcp-capability:{package.server_key}:{descriptor.name}",
                )
            ),
            "server_package_id": package.id,
            "capability_key": descriptor.name,
            "tool_id": descriptor.name,
            "display_name": descriptor.display_name,
            "description": descriptor.description,
            "input_schema": descriptor.parameters,
            "output_schema": None,
            "category": descriptor.category,
            "default_requires_approval": is_mutating,
            "default_is_mutating": is_mutating,
            "is_active": True,
            "metadata": {"risk_level": descriptor.risk_level},
        }

    @staticmethod
    def _connector_capability_payload(
        context: RequestContext,
        package: McpServerPackageContract,
        descriptor: ToolDescriptorContract,
    ) -> dict[str, object]:
        is_mutating = descriptor.is_mutating
        return {
            "id": str(
                uuid.uuid5(
                    CAPABILITY_NAMESPACE,
                    f"mcp-capability:{package.server_key}:{context.organization_id}:{descriptor.name}",
                )
            ),
            "server_package_id": package.id,
            "capability_key": f"{context.organization_id}:{descriptor.name}",
            "tool_id": descriptor.name,
            "display_name": descriptor.display_name,
            "description": descriptor.description,
            "input_schema": descriptor.parameters,
            "output_schema": None,
            "category": descriptor.category,
            "default_requires_approval": is_mutating,
            "default_is_mutating": is_mutating,
            "is_active": True,
            "metadata": {
                "source": "connector",
                "organization_id": context.organization_id,
                "risk_level": descriptor.risk_level,
            },
        }
