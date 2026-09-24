"""Persistence for connectors (DB-backed with in-memory fallback). Secrets encrypted at rest."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from common.encryption import EncryptionService, get_encryption_service
from common.logger import logger
from connectors.models.interface import ConnectorContract, ConnectorStatus
from connectors.models.request import ConnectorCreateRequest, ConnectorUpdateRequest
from database.manager import Base
from exceptions import PersistenceError

class ConnectorModel(Base):
    """SQLAlchemy model for the connectors table. Stores outbound HTTP API connector definitions."""

    __tablename__ = "connectors"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id = Column(String(36), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    entity_types = Column(JSONB, nullable=True)
    base_url = Column(String(512), nullable=False)
    method = Column(String(8), nullable=False, default="POST")
    path = Column(String(512), nullable=False, default="")
    headers = Column(JSONB, nullable=False, default=dict)
    query_params = Column(JSONB, nullable=False, default=dict)
    content_type = Column(String(64), nullable=False, default="application/json")
    body_template = Column(JSONB, nullable=True)
    auth_type = Column(String(32), nullable=False, default="none")
    auth_config = Column(JSONB, nullable=False, default=dict)
    encrypted_secret_config = Column(Text, nullable=True)
    secret_hints = Column(JSONB, nullable=False, default=dict)
    response_mapping = Column(JSONB, nullable=False, default=dict)
    success_when = Column(JSONB, nullable=False, default=dict)
    expose_as_tool = Column(Integer, nullable=False, default=0)
    status = Column(String(32), nullable=False, default=ConnectorStatus.CONFIGURED)
    validation_status = Column(String(16), nullable=True)
    last_validated_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    archived_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )



@dataclass
class ConnectorRecord:
    """In-memory fallback record mirroring ConnectorModel."""

    id: str
    organization_id: str
    name: str
    base_url: str
    method: str
    path: str
    content_type: str
    auth_type: str
    status: str
    headers: dict[str, Any] = field(default_factory=dict)
    query_params: dict[str, Any] = field(default_factory=dict)
    body_template: Any = None
    auth_config: dict[str, Any] = field(default_factory=dict)
    encrypted_secret_config: str | None = None
    secret_hints: dict[str, str] = field(default_factory=dict)
    response_mapping: dict[str, str] = field(default_factory=dict)
    success_when: dict[str, Any] = field(default_factory=dict)
    expose_as_tool: bool = False
    validation_status: str | None = None
    last_validated_at: datetime | None = None
    last_error: str | None = None
    archived_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    entity_types: list[str] | None = None


class ConnectorsModelService:
    """Persistence service for connectors (DB-backed with in-memory fallback)."""

    def __init__(self, database_service_manager: Any) -> None:
        self.database_service_manager = database_service_manager
        self.current_db = (
            database_service_manager.postgres_db_service()
            if database_service_manager and hasattr(database_service_manager, "postgres_db_service")
            else None
        )
        self.module_name = "connectors"
        self._connectors: dict[str, ConnectorRecord] = {}

    def _use_memory(self) -> bool:
        return self.current_db is None

    def _session(self) -> Session:
        if not self.current_db:
            raise PersistenceError("Database service manager unavailable")
        return self.current_db.get_db_session()

    # ── Create ────────────────────────────────────────────────────────────────

    def create_connector(
        self, *, organization_id: str, request: ConnectorCreateRequest
    ) -> ConnectorContract:
        """Persist a new connector for an organization, encrypting any provided secrets."""
        try:
            encrypted, hints = self._encode_secrets(request.secrets)
            values = self._values_from_create(request, encrypted, hints)
            if self._use_memory():
                return self._create_memory(organization_id, values)
            return self._create_db(organization_id, values)
        except PersistenceError as exc:
            logger.error(f"create_connector failed org={organization_id} name={request.name}: {exc}")
            raise
        except Exception as exc:
            logger.exception(f"create_connector failed org={organization_id} name={request.name}")
            raise PersistenceError(f"Unable to create connector: {exc}") from exc

    def _create_memory(self, organization_id: str, values: dict[str, Any]) -> ConnectorContract:
        now = datetime.now(UTC)
        record = ConnectorRecord(
            id=str(uuid4()),
            organization_id=organization_id,
            status=ConnectorStatus.CONFIGURED,
            created_at=now,
            updated_at=now,
            **values,
        )
        self._connectors[record.id] = record
        return self._to_contract(record)

    def _create_db(self, organization_id: str, values: dict[str, Any]) -> ConnectorContract:
        session = self._session()
        model = ConnectorModel(
            organization_id=organization_id, status=ConnectorStatus.CONFIGURED, **values
        )
        session.add(model)
        session.commit()
        session.refresh(model)
        return self._to_contract(model)

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_connector(self, connector_id: str, organization_id: str) -> ConnectorContract | None:
        """Return one active connector scoped to the organization, or None."""
        try:
            if self._use_memory():
                record = self._connectors.get(connector_id)
                if not record or record.organization_id != organization_id or record.archived_at:
                    return None
                return self._to_contract(record)
            model = self._get_active_model(self._session(), connector_id, organization_id)
            return self._to_contract(model) if model else None
        except Exception as exc:
            logger.exception(f"get_connector failed id={connector_id} org={organization_id}")
            raise PersistenceError(f"Unable to get connector: {exc}") from exc

    def list_connectors(
        self, organization_id: str, entity_type: str | None = None
    ) -> list[ConnectorContract]:
        """Return all active connectors for an organization, optionally filtered by entity type."""
        try:
            if self._use_memory():
                return self._list_memory(organization_id, entity_type)
            return self._list_db(organization_id, entity_type)
        except Exception as exc:
            logger.exception(f"list_connectors failed org={organization_id}")
            raise PersistenceError(f"Unable to list connectors: {exc}") from exc

    def _list_memory(
        self, organization_id: str, entity_type: str | None
    ) -> list[ConnectorContract]:
        rows = [
            record
            for record in self._connectors.values()
            if record.organization_id == organization_id
            and record.archived_at is None
            and (entity_type is None or entity_type in (record.entity_types or []))
        ]
        rows.sort(key=lambda record: record.name.lower())
        return [self._to_contract(record) for record in rows]

    def _list_db(self, organization_id: str, entity_type: str | None) -> list[ConnectorContract]:
        session = self._session()
        query = session.query(ConnectorModel).filter(
            ConnectorModel.organization_id == organization_id,
            ConnectorModel.archived_at.is_(None),
        )
        if entity_type is not None:
            query = query.filter(ConnectorModel.entity_types.contains([entity_type]))
        models = query.order_by(ConnectorModel.name.asc()).all()
        return [self._to_contract(model) for model in models]

    def get_decrypted_secrets(self, connector_id: str, organization_id: str) -> dict[str, str]:
        """Return the decrypted secret payload for one active connector (used by the executor)."""
        try:
            if self._use_memory():
                record = self._connectors.get(connector_id)
                if not record or record.organization_id != organization_id or record.archived_at:
                    return {}
                return self._decode_secrets(record.encrypted_secret_config)
            model = self._get_active_model(self._session(), connector_id, organization_id)
            return self._decode_secrets(model.encrypted_secret_config) if model else {}
        except Exception as exc:
            logger.exception(f"get_decrypted_secrets failed id={connector_id} org={organization_id}")
            raise PersistenceError(f"Unable to read connector secrets: {exc}") from exc

    # ── Update / delete ─────────────────────────────────────────────────────────

    def update_connector(
        self, *, connector_id: str, organization_id: str, request: ConnectorUpdateRequest
    ) -> ConnectorContract | None:
        """Apply provided fields to an active connector; re-encrypt secrets if supplied."""
        try:
            updates = self._values_from_update(request)
            if self._use_memory():
                return self._update_memory(connector_id, organization_id, updates, request.status)
            return self._update_db(connector_id, organization_id, updates, request.status)
        except PersistenceError as exc:
            logger.error(f"update_connector failed id={connector_id} org={organization_id}: {exc}")
            raise
        except Exception as exc:
            logger.exception(f"update_connector failed id={connector_id} org={organization_id}")
            raise PersistenceError(f"Unable to update connector: {exc}") from exc

    def _update_memory(
        self, connector_id: str, organization_id: str, updates: dict[str, Any], status: str | None
    ) -> ConnectorContract | None:
        record = self._connectors.get(connector_id)
        if not record or record.organization_id != organization_id or record.archived_at:
            return None
        for key, value in updates.items():
            setattr(record, key, value)
        if status is not None:
            record.status = status
        record.updated_at = datetime.now(UTC)
        return self._to_contract(record)

    def _update_db(
        self, connector_id: str, organization_id: str, updates: dict[str, Any], status: str | None
    ) -> ConnectorContract | None:
        session = self._session()
        model = self._get_active_model(session, connector_id, organization_id)
        if model is None:
            return None
        for key, value in updates.items():
            setattr(model, key, value)
        if status is not None:
            model.status = status
        session.commit()
        session.refresh(model)
        return self._to_contract(model)

    def delete_connector(self, connector_id: str, organization_id: str) -> bool:
        """Soft-delete a connector by marking it archived. Returns True if a row was archived."""
        try:
            now = datetime.now(UTC)
            if self._use_memory():
                record = self._connectors.get(connector_id)
                if not record or record.organization_id != organization_id or record.archived_at:
                    return False
                record.archived_at = now
                record.updated_at = now
                return True
            session = self._session()
            model = self._get_active_model(session, connector_id, organization_id)
            if model is None:
                return False
            model.archived_at = now
            session.commit()
            return True
        except Exception as exc:
            logger.exception(f"delete_connector failed id={connector_id} org={organization_id}")
            raise PersistenceError(f"Unable to delete connector: {exc}") from exc

    def record_validation(
        self, *, connector_id: str, organization_id: str, ok: bool, error: str | None
    ) -> None:
        """Persist the outcome of a connector test on the record."""
        try:
            now = datetime.now(UTC)
            validation_status = "valid" if ok else "invalid"
            if self._use_memory():
                record = self._connectors.get(connector_id)
                if record and record.organization_id == organization_id:
                    record.validation_status = validation_status
                    record.last_validated_at = now
                    record.last_error = error
                return
            session = self._session()
            model = self._get_active_model(session, connector_id, organization_id)
            if model is not None:
                model.validation_status = validation_status
                model.last_validated_at = now
                model.last_error = error
                session.commit()
        except Exception as exc:
            logger.exception(f"record_validation failed id={connector_id} org={organization_id}")
            raise PersistenceError(f"Unable to record connector validation: {exc}") from exc

    def name_exists(self, organization_id: str, name: str) -> bool:
        """Return whether an active connector with this name already exists for the org."""
        try:
            if self._use_memory():
                return any(
                    record.organization_id == organization_id
                    and record.archived_at is None
                    and record.name.lower() == name.strip().lower()
                    for record in self._connectors.values()
                )
            session = self._session()
            exists = (
                session.query(ConnectorModel)
                .filter(
                    ConnectorModel.organization_id == organization_id,
                    ConnectorModel.archived_at.is_(None),
                    func.lower(ConnectorModel.name) == name.strip().lower(),
                )
                .first()
            )
            return exists is not None
        except Exception as exc:
            logger.exception(f"name_exists failed org={organization_id} name={name}")
            raise PersistenceError(f"Unable to check connector name: {exc}") from exc

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _get_active_model(
        session: Session, connector_id: str, organization_id: str
    ) -> ConnectorModel | None:
        return (
            session.query(ConnectorModel)
            .filter(
                ConnectorModel.id == connector_id,
                ConnectorModel.organization_id == organization_id,
                ConnectorModel.archived_at.is_(None),
            )
            .first()
        )

    @staticmethod
    def _values_from_create(
        request: ConnectorCreateRequest, encrypted: str | None, hints: dict[str, str]
    ) -> dict[str, Any]:
        return {
            "name": request.name,
            "entity_types": list(request.entity_types),
            "base_url": request.base_url,
            "method": request.method,
            "path": request.path,
            "headers": dict(request.headers),
            "query_params": dict(request.query_params),
            "content_type": request.content_type,
            "body_template": request.body_template,
            "auth_type": request.auth_type,
            "auth_config": dict(request.auth_config),
            "encrypted_secret_config": encrypted,
            "secret_hints": hints,
            "response_mapping": dict(request.response_mapping),
            "success_when": dict(request.success_when),
            "expose_as_tool": int(request.expose_as_tool),
        }

    def _values_from_update(self, request: ConnectorUpdateRequest) -> dict[str, Any]:
        """Return only the fields the caller provided. Secrets/status are handled separately."""
        # exclude_unset → only fields present in the request; secrets re-encrypted; status set by caller.
        values = request.model_dump(exclude_unset=True, exclude={"secrets", "status"})
        if "expose_as_tool" in values:
            values["expose_as_tool"] = int(values["expose_as_tool"])
        if request.secrets is not None:
            encrypted, hints = self._encode_secrets(request.secrets)
            values["encrypted_secret_config"] = encrypted
            values["secret_hints"] = hints
        return values

    def _encode_secrets(self, secrets: dict[str, str]) -> tuple[str | None, dict[str, str]]:
        normalized = {
            str(key): str(value)
            for key, value in (secrets or {}).items()
            if value not in (None, "")
        }
        if not normalized:
            return None, {}
        enc = self._encryption_service()
        hints = {key: _mask(value) for key, value in normalized.items()}
        return enc.encrypt(json.dumps(normalized)), hints

    def _decode_secrets(self, encrypted_secret_config: str | None) -> dict[str, str]:
        if not encrypted_secret_config:
            return {}
        raw = self._encryption_service().decrypt(encrypted_secret_config)
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _encryption_service():
        """Return the shared encryption service, with a logged dev fallback when unconfigured."""
        try:
            return get_encryption_service()
        except ValueError:
            logger.error("connectors: ENCRYPTION_KEY not configured — using dev fallback key")
            return EncryptionService("connectors-dev-fallback-key")

    @staticmethod
    def _to_contract(obj: ConnectorModel | ConnectorRecord) -> ConnectorContract:
        return ConnectorContract(
            id=obj.id,
            organization_id=obj.organization_id,
            name=obj.name,
            entity_types=list(obj.entity_types or []),
            base_url=obj.base_url,
            method=obj.method,
            path=obj.path or "",
            headers=dict(obj.headers or {}),
            query_params=dict(obj.query_params or {}),
            content_type=obj.content_type,
            body_template=obj.body_template,
            auth_type=obj.auth_type,
            auth_config=dict(obj.auth_config or {}),
            secret_hints=dict(obj.secret_hints or {}),
            response_mapping=dict(obj.response_mapping or {}),
            success_when=dict(obj.success_when or {}),
            expose_as_tool=bool(obj.expose_as_tool),
            status=obj.status,
            validation_status=obj.validation_status,
            last_validated_at=_iso(obj.last_validated_at),
            last_error=obj.last_error,
            created_at=_iso(obj.created_at),
            updated_at=_iso(obj.updated_at),
        )


def _mask(value: str, prefix_len: int = 4, suffix_len: int = 4) -> str:
    """Return a masked display hint for a secret value."""
    if len(value) <= prefix_len + suffix_len:
        return "*" * len(value)
    return f"{value[:prefix_len]}...{value[-suffix_len:]}"


def _iso(value: datetime | None) -> str | None:
    """Return an ISO-8601 string for a datetime, or None."""
    return value.isoformat() if value else None
