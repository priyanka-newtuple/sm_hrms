"""db_models layer for transcription."""

from __future__ import annotations


class TranscriptionModelService:
    """Placeholder DB model service for transcription."""

    def __init__(self, database_service_manager) -> None:  # noqa: ANN001
        super().__init__()
        self.database_manager = database_service_manager
        self.database_service_manager = database_service_manager
        self.current_db = (
            self.database_manager.postgres_db_service()
            if self.database_manager and hasattr(self.database_manager, "postgres_db_service")
            else None
        )
        self.current_db_engine = getattr(self.current_db, "engine", None)
        self.module_name = "transcription"

