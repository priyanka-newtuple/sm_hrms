"""Persistence adapters for platform-managed MCP packages and capabilities."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.sql import func
from sqlalchemy.types import JSON

from database.manager import Base
from exceptions import PersistenceError
from mcp.models.interface import (
    McpCapabilityConfigurationContract,
    McpCapabilityContract,
    McpServerConfigurationContract,
    McpServerPackageContract,
)


class McpServerPackageModel(Base):
    __tablename__ = "mcp_server_packages"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    server_key = Column(String(128), nullable=False, unique=True, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    version = Column(String(64), nullable=False, default="1")
    is_platform_managed = Column(Integer, nullable=False, default=1)
    is_active = Column(Integer, nullable=False, default=1)
    metadata_json = Column("metadata", JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class McpServerConfigurationModel(Base):
    __tablename__ = "mcp_server_configurations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id = Column(String(36), nullable=False, index=True)
    server_package_id = Column(
        String(36),
        ForeignKey("mcp_server_packages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_enabled = Column(Integer, nullable=False, default=1)
    config_json = Column(JSON, nullable=False, default=dict)
    created_by = Column(String(36), nullable=True)
    updated_by = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_mcp_server_config_org_package", "organization_id", "server_package_id", unique=True),
    )


class McpCapabilityModel(Base):
    __tablename__ = "mcp_capabilities"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    server_package_id = Column(
        String(36),
        ForeignKey("mcp_server_packages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    capability_key = Column(String(128), nullable=False)
    tool_id = Column(String(128), nullable=False)
    display_name = Column(String(128), nullable=False)
    description = Column(Text, nullable=False)
    input_schema = Column(JSON, nullable=False, default=dict)
    output_schema = Column(JSON, nullable=True)
    category = Column(String(64), nullable=False)
    default_requires_approval = Column(Integer, nullable=False, default=0)
    default_is_mutating = Column(Integer, nullable=False, default=0)
    is_active = Column(Integer, nullable=False, default=1)
    metadata_json = Column("metadata", JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_mcp_capabilities_package_key", "server_package_id", "capability_key", unique=True),
    )


class McpCapabilityConfigurationModel(Base):
    __tablename__ = "mcp_capability_configurations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id = Column(String(36), nullable=False, index=True)
    capability_id = Column(
        String(36),
        ForeignKey("mcp_capabilities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_enabled = Column(Integer, nullable=False, default=1)
    requires_approval = Column(Integer, nullable=False, default=0)
    config_json = Column(JSON, nullable=False, default=dict)
    integration_ref = Column(String(256), nullable=True)
    created_by = Column(String(36), nullable=True)
    updated_by = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_mcp_capability_config_org_capability", "organization_id", "capability_id", unique=True),
    )


class McpModelService:
    """Persist platform-managed MCP package configuration in PostgreSQL."""

    def __init__(self, database_service_manager) -> None:  # noqa: ANN001
        if database_service_manager is None or not hasattr(database_service_manager, "postgres_db_service"):
            raise PersistenceError("Database service manager is required for McpModelService")
        self.current_db = database_service_manager.postgres_db_service()
        if self.current_db is None or getattr(self.current_db, "engine", None) is None:
            raise PersistenceError("PostgreSQL database service is not configured for McpModelService")
        self.current_db_engine = self.current_db.engine

    def upsert_server_package(self, payload: dict[str, Any]) -> McpServerPackageContract:
        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                row = db.query(McpServerPackageModel).filter(McpServerPackageModel.server_key == payload["server_key"]).first()
                now = datetime.now(UTC)
                if row is None:
                    row = McpServerPackageModel(
                        id=str(payload["id"]),
                        server_key=str(payload["server_key"]),
                        name=str(payload["name"]),
                        description=payload.get("description"),
                        version=str(payload.get("version") or "1"),
                        is_platform_managed=1 if payload.get("is_platform_managed", True) else 0,
                        is_active=1 if payload.get("is_active", True) else 0,
                        metadata_json=dict(payload.get("metadata") or {}),
                        created_at=payload.get("created_at") or now,
                        updated_at=payload.get("updated_at") or now,
                    )
                    db.add(row)
                else:
                    row.name = str(payload["name"])
                    row.description = payload.get("description")
                    row.version = str(payload.get("version") or row.version)
                    row.is_platform_managed = 1 if payload.get("is_platform_managed", True) else 0
                    row.is_active = 1 if payload.get("is_active", True) else 0
                    row.metadata_json = dict(payload.get("metadata") or {})
                    row.updated_at = now
                db.commit()
                db.refresh(row)
                return McpServerPackageContract.model_validate(row)
        except Exception as exc:  # noqa: BLE001
            raise PersistenceError(f"Unable to upsert MCP server package: {exc}") from exc

    def upsert_capability(self, payload: dict[str, Any]) -> McpCapabilityContract:
        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                row = (
                    db.query(McpCapabilityModel)
                    .filter(
                        McpCapabilityModel.server_package_id == payload["server_package_id"],
                        McpCapabilityModel.capability_key == payload["capability_key"],
                    )
                    .first()
                )
                now = datetime.now(UTC)
                values = {
                    "tool_id": str(payload["tool_id"]),
                    "display_name": str(payload["display_name"]),
                    "description": str(payload["description"]),
                    "input_schema": dict(payload.get("input_schema") or {}),
                    "output_schema": payload.get("output_schema"),
                    "category": str(payload["category"]),
                    "default_requires_approval": 1 if payload.get("default_requires_approval", False) else 0,
                    "default_is_mutating": 1 if payload.get("default_is_mutating", False) else 0,
                    "is_active": 1 if payload.get("is_active", True) else 0,
                    "metadata_json": dict(payload.get("metadata") or {}),
                }
                if row is None:
                    row = McpCapabilityModel(
                        id=str(payload["id"]),
                        server_package_id=str(payload["server_package_id"]),
                        capability_key=str(payload["capability_key"]),
                        created_at=payload.get("created_at") or now,
                        updated_at=payload.get("updated_at") or now,
                        **values,
                    )
                    db.add(row)
                else:
                    for key, value in values.items():
                        setattr(row, key, value)
                    row.updated_at = now
                db.commit()
                db.refresh(row)
                return McpCapabilityContract.model_validate(row)
        except Exception as exc:  # noqa: BLE001
            raise PersistenceError(f"Unable to upsert MCP capability: {exc}") from exc

    def list_server_packages(self, active_only: bool = True) -> list[McpServerPackageContract]:
        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                query = db.query(McpServerPackageModel)
                if active_only:
                    query = query.filter(McpServerPackageModel.is_active == 1)
                rows = query.order_by(McpServerPackageModel.name.asc()).all()
                return [McpServerPackageContract.model_validate(row) for row in rows]
        except Exception as exc:  # noqa: BLE001
            raise PersistenceError(f"Unable to list MCP server packages: {exc}") from exc

    def get_server_package(self, package_id: str) -> McpServerPackageContract | None:
        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                row = db.query(McpServerPackageModel).filter(McpServerPackageModel.id == package_id).first()
                return McpServerPackageContract.model_validate(row) if row else None
        except Exception as exc:  # noqa: BLE001
            raise PersistenceError(f"Unable to fetch MCP server package: {exc}") from exc

    def get_server_configuration(self, organization_id: str, package_id: str) -> McpServerConfigurationContract | None:
        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                row = (
                    db.query(McpServerConfigurationModel)
                    .filter(
                        McpServerConfigurationModel.organization_id == organization_id,
                        McpServerConfigurationModel.server_package_id == package_id,
                    )
                    .first()
                )
                return McpServerConfigurationContract.model_validate(row) if row else None
        except Exception as exc:  # noqa: BLE001
            raise PersistenceError(f"Unable to fetch MCP server configuration: {exc}") from exc

    def upsert_server_configuration(self, organization_id: str, package_id: str, payload: dict[str, Any]) -> McpServerConfigurationContract:
        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                row = (
                    db.query(McpServerConfigurationModel)
                    .filter(
                        McpServerConfigurationModel.organization_id == organization_id,
                        McpServerConfigurationModel.server_package_id == package_id,
                    )
                    .first()
                )
                now = datetime.now(UTC)
                if row is None:
                    row = McpServerConfigurationModel(
                        id=str(payload.get("id") or uuid4()),
                        organization_id=organization_id,
                        server_package_id=package_id,
                        is_enabled=1 if payload.get("is_enabled", True) else 0,
                        config_json=dict(payload.get("config") or {}),
                        created_by=payload.get("actor_id"),
                        updated_by=payload.get("actor_id"),
                        created_at=now,
                        updated_at=now,
                    )
                    db.add(row)
                else:
                    row.is_enabled = 1 if payload.get("is_enabled", True) else 0
                    row.config_json = dict(payload.get("config") or {})
                    row.updated_by = payload.get("actor_id")
                    row.updated_at = now
                db.commit()
                db.refresh(row)
                return McpServerConfigurationContract.model_validate(row)
        except Exception as exc:  # noqa: BLE001
            raise PersistenceError(f"Unable to upsert MCP server configuration: {exc}") from exc

    def list_capabilities(self, package_id: str | None = None, active_only: bool = True) -> list[McpCapabilityContract]:
        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                query = db.query(McpCapabilityModel)
                if package_id:
                    query = query.filter(McpCapabilityModel.server_package_id == package_id)
                if active_only:
                    query = query.filter(McpCapabilityModel.is_active == 1)
                rows = query.order_by(McpCapabilityModel.display_name.asc()).all()
                return [McpCapabilityContract.model_validate(row) for row in rows]
        except Exception as exc:  # noqa: BLE001
            raise PersistenceError(f"Unable to list MCP capabilities: {exc}") from exc

    def get_capability(self, capability_id: str) -> McpCapabilityContract | None:
        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                row = db.query(McpCapabilityModel).filter(McpCapabilityModel.id == capability_id).first()
                return McpCapabilityContract.model_validate(row) if row else None
        except Exception as exc:  # noqa: BLE001
            raise PersistenceError(f"Unable to fetch MCP capability: {exc}") from exc

    def get_capability_configuration(self, organization_id: str, capability_id: str) -> McpCapabilityConfigurationContract | None:
        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                row = (
                    db.query(McpCapabilityConfigurationModel)
                    .filter(
                        McpCapabilityConfigurationModel.organization_id == organization_id,
                        McpCapabilityConfigurationModel.capability_id == capability_id,
                    )
                    .first()
                )
                return McpCapabilityConfigurationContract.model_validate(row) if row else None
        except Exception as exc:  # noqa: BLE001
            raise PersistenceError(f"Unable to fetch MCP capability configuration: {exc}") from exc

    def upsert_capability_configuration(self, organization_id: str, capability_id: str, payload: dict[str, Any]) -> McpCapabilityConfigurationContract:
        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                row = (
                    db.query(McpCapabilityConfigurationModel)
                    .filter(
                        McpCapabilityConfigurationModel.organization_id == organization_id,
                        McpCapabilityConfigurationModel.capability_id == capability_id,
                    )
                    .first()
                )
                now = datetime.now(UTC)
                if row is None:
                    row = McpCapabilityConfigurationModel(
                        id=str(payload.get("id") or uuid4()),
                        organization_id=organization_id,
                        capability_id=capability_id,
                        is_enabled=1 if payload.get("is_enabled", True) else 0,
                        requires_approval=1 if payload.get("requires_approval", False) else 0,
                        config_json=dict(payload.get("config") or {}),
                        integration_ref=payload.get("integration_ref"),
                        created_by=payload.get("actor_id"),
                        updated_by=payload.get("actor_id"),
                        created_at=now,
                        updated_at=now,
                    )
                    db.add(row)
                else:
                    row.is_enabled = 1 if payload.get("is_enabled", True) else 0
                    row.requires_approval = 1 if payload.get("requires_approval", False) else 0
                    row.config_json = dict(payload.get("config") or {})
                    row.integration_ref = payload.get("integration_ref")
                    row.updated_by = payload.get("actor_id")
                    row.updated_at = now
                db.commit()
                db.refresh(row)
                return McpCapabilityConfigurationContract.model_validate(row)
        except Exception as exc:  # noqa: BLE001
            raise PersistenceError(f"Unable to upsert MCP capability configuration: {exc}") from exc
