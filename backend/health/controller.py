"""Health controller."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status


class HealthRestController:
    def __init__(
        self,
        health_service_manager,
        database_service_manager=None,
        auth_service_manager=None,
    ) -> None:  # noqa: ANN001
        super().__init__()
        self.health_service_manager = health_service_manager
        self.database_service_manager = database_service_manager
        self.current_db = (
            database_service_manager.postgres_db_service()
            if database_service_manager and hasattr(database_service_manager, "postgres_db_service")
            else None
        )
        self.current_db_engine = getattr(self.current_db, "engine", None)
        self.auth_service_manager = auth_service_manager

    def prepare(self, app: APIRouter, security: Depends | None = None) -> None:
        """Prepare health endpoints."""
        @app.get("/health", status_code=status.HTTP_200_OK, tags=["health"])
        def health_endpoint() -> dict[str, str]:
            return self.health_service_manager.health()
