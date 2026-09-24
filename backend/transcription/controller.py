"""controller layer for transcription."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from .models.response import TranscriptionStatusResponse


class TranscriptionRestController:
    """Placeholder REST controller for transcription."""

    def __init__(
        self,
        transcription_service_manager,
        database_service_manager=None,
        auth_service_manager=None,
    ) -> None:  # noqa: ANN001
        super().__init__()
        self.transcription_service_manager = transcription_service_manager
        self.service_manager = transcription_service_manager
        self.database_service_manager = database_service_manager
        self.current_db = (
            database_service_manager.postgres_db_service()
            if database_service_manager and hasattr(database_service_manager, "postgres_db_service")
            else None
        )
        self.current_db_engine = getattr(self.current_db, "engine", None)
        self.auth_service_manager = auth_service_manager

    def prepare(self, app: APIRouter, security: Depends | None = None) -> None:
        """Prepare transcription endpoints."""
        @app.get(
            "/transcription/status",
            status_code=status.HTTP_200_OK,
            tags=["transcription"],
            response_model=TranscriptionStatusResponse,
        )
        def status_endpoint() -> TranscriptionStatusResponse:
            return self.transcription_service_manager.get_status()
