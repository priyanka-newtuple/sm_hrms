"""manager layer for tenants."""

from __future__ import annotations

try:
    from common.enums import ModuleStatus
except ImportError:  # pragma: no cover - package import fallback
    from backend.modular_backend.common.enums import ModuleStatus

from tenants.models.response import OrganizationsStatusResponse


class TenantsServiceManager:
    """Generic tenants facade over organization capabilities."""

    def __init__(
        self,
        tenants_db_model_service,
        database_service_manager,
        config,
        tenants_service_manager=None,
        *dependencies,
    ) -> None:  # noqa: ANN001
        super().__init__()
        self.tenants_db_model_service = tenants_db_model_service
        self.db_model_service = tenants_db_model_service
        self.model_service = tenants_db_model_service
        self.database_service_manager = database_service_manager
        self.config = config
        self.dependencies = list(dependencies)
        self.tenants_service_manager = tenants_service_manager or self._resolve_tenants_service(
            dependencies
        )
        self.module_name = "tenants"
        self._started = False

    def start(self) -> None:
        self._started = True

    def stop(self) -> None:
        self._started = False

    def get_status(self) -> OrganizationsStatusResponse:
        if self.tenants_service_manager and hasattr(self.tenants_service_manager, "get_status"):
            status_response = self.tenants_service_manager.get_status()
            return OrganizationsStatusResponse(
                module=self.module_name,
                status=getattr(status_response, "status", ModuleStatus.READY.value),
                started=bool(getattr(status_response, "started", self._started)),
            )
        return OrganizationsStatusResponse(module=self.module_name, status=ModuleStatus.READY.value, started=self._started)

    @staticmethod
    def _resolve_tenants_service(dependencies: tuple[object, ...]) -> object | None:
        for dependency in dependencies:
            if hasattr(dependency, "get_status") and dependency.__class__.__name__ == "OrganizationsServiceManager":
                return dependency
        return None
