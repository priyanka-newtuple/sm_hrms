"""manager layer for transcription."""

from __future__ import annotations

try:
    from common.enums import ModuleStatus
except ImportError:  # pragma: no cover - package import fallback
    from backend.modular_backend.common.enums import ModuleStatus

from .models.response import TranscriptionStatusResponse


class TranscriptionServiceManager:
    """Placeholder service manager for transcription."""

    def __init__(
        self,
        transcription_db_model_service,
        database_service_manager,
        config,
        identity_access_service_manager=None,
        *dependencies,
    ) -> None:  # noqa: ANN001
        super().__init__()
        self.transcription_db_model_service = transcription_db_model_service
        self.db_model_service = transcription_db_model_service
        self.model_service = transcription_db_model_service
        self.database_service_manager = database_service_manager
        self.config = config
        self.dependencies = list(dependencies)
        self.identity_access_service_manager = identity_access_service_manager
        self.module_name = "transcription"
        self._started = False

    def start(self) -> None:
        self._started = True

    def stop(self) -> None:
        self._started = False

    def get_status(self) -> TranscriptionStatusResponse:
        return TranscriptionStatusResponse(
            module=self.module_name,
            status=ModuleStatus.READY.value,
            started=self._started,
        )
