"""Persistence helpers for action definitions."""

from __future__ import annotations

import os
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, Column, DateTime, String, Text, or_
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from database.manager import Base
from exceptions import PersistenceError

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


# ── SQLAlchemy Models ─────────────────────────────────────────────────────────


class ActionDefinitionModel(Base):
    """Catalog of available executor action types registered for the platform."""

    __tablename__ = "action_definitions"
    __table_args__ = (
        {
            "schema": f"{os.environ.get('POSTGRES_APP_SCHEMA', 'public')}_definitions",
            "extend_existing": True,
        },
    )

    definition_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), nullable=True)
    kind = Column(String(128), nullable=False)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    input_schema = Column(JSONB, nullable=False, default=dict)
    output_schema = Column(JSONB, nullable=False, default=dict)
    is_internal = Column(Boolean, nullable=False, server_default="false")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ── Model Service ─────────────────────────────────────────────────────────────


class ActionsModelService:
    """Persistence adapter for action definitions and action runs.

    Receives a per-request Session — no session management of its own.
    """

    module_name = "actions"

    def __init__(self, database_service_manager: Any = None) -> None:
        """Accept database_service_manager for interface compatibility; sessions are passed per call."""
        self.module_name = "actions"

    # ── Action Definitions ────────────────────────────────────────────────────

    def list_action_definitions(
        self, db: Session, org_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Return global + org-scoped action definitions ordered by kind, excluding internal ones."""
        try:
            query = db.query(ActionDefinitionModel).filter(
                ActionDefinitionModel.is_internal.is_(False)
            )
            if org_id:
                query = query.filter(
                    or_(
                        ActionDefinitionModel.organization_id.is_(None),
                        ActionDefinitionModel.organization_id == org_id,
                    )
                )
            rows = query.order_by(ActionDefinitionModel.kind.asc()).all()
            return [self._to_dict(row) for row in rows]
        except Exception as exc:
            raise PersistenceError(f"Unable to list action definitions: {exc}") from exc

    def get_action_definition_by_kind(self, db: Session, kind: str) -> dict[str, Any] | None:
        """Return a single action definition by its kind identifier, or None if not found."""
        try:
            row = db.query(ActionDefinitionModel).filter(ActionDefinitionModel.kind == kind).first()
            return self._to_dict(row) if row else None
        except Exception as exc:
            raise PersistenceError(f"Unable to get action definition: {exc}") from exc

    # ── Serializers ───────────────────────────────────────────────────────────

    @staticmethod
    def _to_dict(row: ActionDefinitionModel) -> dict[str, Any]:
        """Serialize an ActionDefinitionModel ORM row to a plain dict."""
        return {
            "definition_id": row.definition_id,
            "organization_id": row.organization_id,
            "kind": row.kind,
            "name": row.name,
            "description": row.description,
            "input_schema": row.input_schema,
            "output_schema": row.output_schema,
            "created_at": row.created_at,
        }
