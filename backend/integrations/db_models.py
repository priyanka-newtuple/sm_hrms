"""Persistence adapters for integrations."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast
from uuid import uuid4

from cryptography.fernet import Fernet
from sqlalchemy import Column, DateTime, Index, String, Text
from sqlalchemy.sql import func
from sqlalchemy.types import JSON

from database.manager import Base
from exceptions import PersistenceError

from .models.interface import (
    IntegrationDefinitionContract,
    OrganizationIntegrationContract,
    get_provider_definition,
    list_provider_definitions,
    normalize_capability,
    normalize_provider,
)

if TYPE_CHECKING:
    from datetime import datetime

    from database.manager import DatabaseServiceManager
    from integrations.models.request import ConnectIntegrationRequest, ScheduleCalendarEventRequest


class OrganizationIntegrationModel(Base):
    __tablename__ = "organization_integrations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id = Column(String(36), nullable=False, index=True)
    provider = Column(String(64), nullable=False, index=True)
    auth_type = Column(String(32), nullable=False)
    capabilities = Column(JSON, nullable=False, default=list)
    display_name = Column(String(128), nullable=True)
    status = Column(String(32), nullable=False, default="configured")
    config = Column(JSON, nullable=False, default=dict)
    encrypted_secret_config = Column(Text, nullable=True)
    secret_hints = Column(JSON, nullable=False, default=dict)
    validation_status = Column(String(16), nullable=True)
    last_validated_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_org_integrations_org_provider", "organization_id", "provider", unique=True),
    )


class IntegrationCapabilityDefaultModel(Base):
    __tablename__ = "integration_capability_defaults"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id = Column(String(36), nullable=False, index=True)
    capability = Column(String(32), nullable=False, index=True)
    provider = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index(
            "ix_integration_capability_defaults_org_capability",
            "organization_id",
            "capability",
            unique=True,
        ),
    )


@dataclass
class IntegrationAccountRecord:
    organization_id: str
    user_id: str
    provider: str
    provider_account_id: str
    scopes: list[str] = field(default_factory=list)
    connected: bool = True


@dataclass
class CalendarEventRecord:
    event_id: str
    organization_id: str
    user_id: str
    provider: str
    title: str
    starts_at: str
    ends_at: str
    attendees: list[str] = field(default_factory=list)
    entity_id: str | None = None


class IntegrationsModelService:
    """Persistence service for integration configuration and legacy event state."""

    def __init__(self, database_service_manager: DatabaseServiceManager) -> None:
        if database_service_manager is None or not hasattr(
            database_service_manager, "postgres_db_service"
        ):
            raise PersistenceError(
                "Database service manager is required for IntegrationsModelService"
            )

        self.database_manager = database_service_manager
        self.database_service_manager = database_service_manager
        self.current_db = database_service_manager.postgres_db_service()
        if self.current_db is None or getattr(self.current_db, "engine", None) is None:
            raise PersistenceError(
                "PostgreSQL database service is not configured for IntegrationsModelService"
            )

        self.current_db_engine = self.current_db.engine
        self.module_name = "integrations"
        self._accounts: dict[tuple[str, str, str], IntegrationAccountRecord] = {}
        self._events_by_org: dict[str, list[CalendarEventRecord]] = {}

    def list_definitions(self) -> list[IntegrationDefinitionContract]:
        return list_provider_definitions()

    def list_organization_integrations(
        self, organization_id: str
    ) -> list[OrganizationIntegrationContract]:
        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                rows = (
                    db.query(OrganizationIntegrationModel)
                    .filter(OrganizationIntegrationModel.organization_id == organization_id)
                    .order_by(OrganizationIntegrationModel.provider.asc())
                    .all()
                )
                return [self._to_contract(row) for row in rows]
        except Exception as exc:
            raise PersistenceError(f"Unable to list organization integrations: {exc}") from exc

    def get_organization_integration(
        self, organization_id: str, provider: str
    ) -> OrganizationIntegrationContract | None:
        normalized_provider = normalize_provider(provider)
        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                row = (
                    db.query(OrganizationIntegrationModel)
                    .filter(
                        OrganizationIntegrationModel.organization_id == organization_id,
                        OrganizationIntegrationModel.provider == normalized_provider,
                    )
                    .first()
                )
                return self._to_contract(row) if row else None
        except Exception as exc:
            raise PersistenceError(
                f"Unable to fetch integration {normalized_provider}: {exc}"
            ) from exc

    def upsert_organization_integration(
        self,
        organization_id: str,
        provider: str,
        *,
        display_name: str | None,
        config: dict[str, object],
        secrets: dict[str, object],
        status: str,
        validation_status: str | None,
        last_error: str | None,
        last_validated_at: datetime | None,
    ) -> OrganizationIntegrationContract:
        normalized_provider = normalize_provider(provider)
        definition = get_provider_definition(normalized_provider)
        encrypted_secret_config, secret_hints = self._encode_secrets(secrets)
        payload = dict(config or {})

        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                row = (
                    db.query(OrganizationIntegrationModel)
                    .filter(
                        OrganizationIntegrationModel.organization_id == organization_id,
                        OrganizationIntegrationModel.provider == normalized_provider,
                    )
                    .first()
                )
                if row is None:
                    row = OrganizationIntegrationModel(
                        organization_id=organization_id,
                        provider=normalized_provider,
                        auth_type=definition.auth_type,
                        capabilities=list(definition.capabilities),
                    )
                    db.add(row)

                row.display_name = display_name
                row.status = status
                row.auth_type = definition.auth_type
                row.capabilities = list(definition.capabilities)
                row.config = payload
                row.encrypted_secret_config = encrypted_secret_config
                row.secret_hints = secret_hints
                row.validation_status = validation_status
                row.last_error = last_error
                row.last_validated_at = last_validated_at

                db.flush()
                db.commit()
                db.refresh(row)
                return self._to_contract(row)
        except Exception as exc:
            raise PersistenceError(f"Unable to upsert organization integration: {exc}") from exc

    def delete_organization_integration(self, organization_id: str, provider: str) -> bool:
        normalized_provider = normalize_provider(provider)
        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                deleted = (
                    db.query(OrganizationIntegrationModel)
                    .filter(
                        OrganizationIntegrationModel.organization_id == organization_id,
                        OrganizationIntegrationModel.provider == normalized_provider,
                    )
                    .delete()
                )
                (
                    db.query(IntegrationCapabilityDefaultModel)
                    .filter(
                        IntegrationCapabilityDefaultModel.organization_id == organization_id,
                        IntegrationCapabilityDefaultModel.provider == normalized_provider,
                    )
                    .delete()
                )
                db.commit()
                return deleted > 0
        except Exception as exc:
            raise PersistenceError(f"Unable to delete organization integration: {exc}") from exc

    def list_capability_defaults(self, organization_id: str) -> dict[str, str]:
        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                rows = (
                    db.query(IntegrationCapabilityDefaultModel)
                    .filter(IntegrationCapabilityDefaultModel.organization_id == organization_id)
                    .all()
                )
                return {
                    str(cast("Any", row).capability): str(cast("Any", row).provider) for row in rows
                }
        except Exception as exc:
            raise PersistenceError(f"Unable to list capability defaults: {exc}") from exc

    def set_capability_default(self, organization_id: str, capability: str, provider: str) -> str:
        normalized_capability = normalize_capability(capability)
        normalized_provider = normalize_provider(provider)
        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                row = (
                    db.query(IntegrationCapabilityDefaultModel)
                    .filter(
                        IntegrationCapabilityDefaultModel.organization_id == organization_id,
                        IntegrationCapabilityDefaultModel.capability == normalized_capability,
                    )
                    .first()
                )
                if row is None:
                    row = IntegrationCapabilityDefaultModel(
                        organization_id=organization_id,
                        capability=normalized_capability,
                        provider=normalized_provider,
                    )
                    db.add(row)
                else:
                    row.provider = normalized_provider
                db.flush()
                db.commit()
                return str(cast("Any", row).provider)
        except Exception as exc:
            raise PersistenceError(f"Unable to set capability default: {exc}") from exc

    def get_decrypted_secrets(self, organization_id: str, provider: str) -> dict[str, object]:
        normalized_provider = normalize_provider(provider)
        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                row = (
                    db.query(OrganizationIntegrationModel)
                    .filter(
                        OrganizationIntegrationModel.organization_id == organization_id,
                        OrganizationIntegrationModel.provider == normalized_provider,
                    )
                    .first()
                )
                if row is None:
                    return {}
                return self._decode_secrets(cast("str | None", row.encrypted_secret_config))
        except Exception as exc:
            raise PersistenceError(f"Unable to decrypt integration secrets: {exc}") from exc

    def get_capability_credentials(
        self, organization_id: str, capability: str
    ) -> tuple[str | None, dict[str, object]]:
        normalized_capability = normalize_capability(capability)
        defaults = self.list_capability_defaults(organization_id)
        provider = defaults.get(normalized_capability)
        if provider is None:
            for integration in self.list_organization_integrations(organization_id):
                if normalized_capability in integration.capabilities:
                    provider = integration.provider
                    break
        if provider is None:
            return None, {}
        integration = self.get_organization_integration(organization_id, provider)
        if integration is None:
            return None, {}
        payload = dict(integration.config)
        payload.update(self.get_decrypted_secrets(organization_id, provider))
        return provider, payload

    def upsert_integration(self, request: ConnectIntegrationRequest) -> IntegrationAccountRecord:
        try:
            provider = normalize_provider(request.provider)
            key = (request.organization_id, request.user_id, provider)
            record = IntegrationAccountRecord(
                organization_id=request.organization_id,
                user_id=request.user_id,
                provider=provider,
                provider_account_id=request.provider_account_id,
                scopes=list(request.scopes),
                connected=True,
            )
            self._accounts[key] = record
            return record
        except Exception as exc:
            raise PersistenceError(f"Unable to upsert integration: {exc}") from exc

    def get_integration(
        self, organization_id: str, user_id: str, provider: str
    ) -> IntegrationAccountRecord | None:
        return self._accounts.get((organization_id, user_id, normalize_provider(provider)))

    def list_integrations(
        self, organization_id: str, user_id: str | None = None
    ) -> list[IntegrationAccountRecord]:
        rows: list[IntegrationAccountRecord] = []
        for (org_id, record_user_id, _), record in self._accounts.items():
            if org_id != organization_id:
                continue
            if user_id and record_user_id != user_id:
                continue
            rows.append(record)
        return sorted(rows, key=lambda row: (row.user_id, row.provider))

    def create_event(self, request: ScheduleCalendarEventRequest) -> CalendarEventRecord:
        try:
            record = CalendarEventRecord(
                event_id=str(uuid4()),
                organization_id=request.organization_id,
                user_id=request.user_id,
                provider=request.provider,
                title=request.title,
                starts_at=request.starts_at,
                ends_at=request.ends_at,
                attendees=list(request.attendees),
                entity_id=request.entity_id,
            )
            self._events_by_org.setdefault(request.organization_id, []).append(record)
            return record
        except Exception as exc:
            raise PersistenceError(f"Unable to create event: {exc}") from exc

    def list_events(
        self,
        organization_id: str,
        provider: str | None = None,
        user_id: str | None = None,
    ) -> list[CalendarEventRecord]:
        rows = self._events_by_org.get(organization_id, [])
        filtered: list[CalendarEventRecord] = []
        normalized_provider = normalize_provider(provider) if provider else None
        for row in rows:
            if normalized_provider and row.provider != normalized_provider:
                continue
            if user_id and row.user_id != user_id:
                continue
            filtered.append(row)
        return sorted(filtered, key=lambda row: (row.starts_at, row.event_id))

    def _to_contract(self, row: OrganizationIntegrationModel) -> OrganizationIntegrationContract:
        data = cast("Any", row)
        last_validated_at = data.last_validated_at
        return OrganizationIntegrationContract(
            organization_id=data.organization_id,
            provider=data.provider,
            auth_type=data.auth_type,
            capabilities=tuple(data.capabilities or []),
            display_name=data.display_name,
            status=data.status,
            config=dict(data.config or {}),
            secret_hints=dict(data.secret_hints or {}),
            validation_status=data.validation_status,
            last_validated_at=last_validated_at.isoformat() if last_validated_at else None,
            last_error=data.last_error,
        )

    def _encode_secrets(self, secrets: dict[str, object]) -> tuple[str | None, dict[str, str]]:
        normalized = {
            str(key): value for key, value in (secrets or {}).items() if value not in (None, "")
        }
        if not normalized:
            return None, {}

        enc = self._get_encryption_service()
        hints = {key: self._mask_secret(str(value)) for key, value in normalized.items()}
        encrypted_payload = enc.encrypt(
            json.dumps({key: str(value) for key, value in normalized.items()})
        )
        return encrypted_payload, hints

    def _decode_secrets(self, encrypted_secret_config: str | None) -> dict[str, object]:
        if not encrypted_secret_config:
            return {}
        enc = self._get_encryption_service()
        raw = enc.decrypt(encrypted_secret_config)
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            return {}
        return parsed

    @staticmethod
    def _mask_secret(value: str, prefix_len: int = 4, suffix_len: int = 4) -> str:
        if len(value) <= prefix_len + suffix_len:
            return "*" * len(value)
        return f"{value[:prefix_len]}...{value[-suffix_len:]}"

    @staticmethod
    def _get_encryption_service():
        try:
            from common.encryption import get_encryption_service

            return get_encryption_service()
        except Exception:
            secret = (
                os.getenv("MODULAR_INTEGRATIONS_SECRET_KEY")
                or os.getenv("CUSTOM_OAUTH_SECRET_KEY")
                or "modular-integrations-dev-key"
            )
            key_bytes = hashlib.sha256(secret.encode()).digest()
            fernet_key = base64.urlsafe_b64encode(key_bytes)

            class _FallbackEncryptionService:
                def __init__(self, key: bytes) -> None:
                    self._fernet = Fernet(key)

                def encrypt(self, plaintext: str) -> str:
                    return self._fernet.encrypt(plaintext.encode()).decode()

                def decrypt(self, ciphertext: str) -> str:
                    return self._fernet.decrypt(ciphertext.encode()).decode()

            return _FallbackEncryptionService(fernet_key)
