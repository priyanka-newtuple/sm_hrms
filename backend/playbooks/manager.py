"""manager layer for playbooks."""

from __future__ import annotations

try:
    from common.enums import ModuleStatus
except ImportError:  # pragma: no cover - package import fallback
    from backend.modular_backend.common.enums import ModuleStatus

from playbooks.models.response import PlaybooksRuntimeStatusResponse


class PlaybooksServiceManager:
    """Generic playbooks facade over playbooks runtime capabilities."""

    def __init__(
        self,
        playbooks_db_model_service,
        database_service_manager,
        config,
        playbooks_service_manager=None,
        *dependencies,
    ) -> None:  # noqa: ANN001
        super().__init__()
        self.playbooks_db_model_service = playbooks_db_model_service
        self.db_model_service = playbooks_db_model_service
        self.model_service = playbooks_db_model_service
        self.database_service_manager = database_service_manager
        self.config = config
        self.dependencies = list(dependencies)
        self.playbooks_service_manager = playbooks_service_manager or self._resolve_runtime_service(
            dependencies
        )
        self.module_name = "playbooks"
        self._started = False

    def start(self) -> None:
        self._started = True

    def stop(self) -> None:
        self._started = False

    def get_status(self) -> PlaybooksRuntimeStatusResponse:
        if self.playbooks_service_manager and hasattr(self.playbooks_service_manager, "get_status"):
            status_response = self.playbooks_service_manager.get_status()
            return PlaybooksRuntimeStatusResponse(
                module=self.module_name,
                status=getattr(status_response, "status", ModuleStatus.READY.value),
                started=bool(getattr(status_response, "started", self._started)),
            )
        return PlaybooksRuntimeStatusResponse(module=self.module_name, status=ModuleStatus.READY.value, started=self._started)

    @staticmethod
    def _resolve_runtime_service(dependencies: tuple[object, ...]) -> object | None:
        for dependency in dependencies:
            if hasattr(dependency, "get_status") and dependency.__class__.__name__ == "PlaybooksRuntimeServiceManager":
                return dependency
        return None
