"""Persistence adapters for filehandler module."""

from __future__ import annotations

import base64
import hashlib
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import BIGINT, Boolean, Column, DateTime, Index, Integer, String, Text, and_
import sqlalchemy as sa
from sqlalchemy.sql import func
from sqlalchemy.types import JSON

from common.logger import logger
from database.manager import Base
from exceptions import NotFoundError, PersistenceError
from filehandler.models.interface import FileRecordStatus
from filehandler.models.request import (
    FileTypeCreateRequest,
    FileTypeUpdateRequest,
    FileUploadRequest,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _to_iso(value: datetime | None) -> str:
    if value is None:
        return _utc_now()
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC).isoformat()
    return value.isoformat()


@dataclass
class FileTypeRecord:
    """File type config record."""

    organization_id: str
    type_id: str
    display_name: str
    description: str
    folder: str
    allowed_extensions: list[str]
    max_size_mb: int
    is_active: bool
    is_system: bool
    version_control_enabled: bool = False
    is_preview_thumbnail: bool = False
    upload_contexts: list[dict[str, object]] | None = None
    agent_config: dict[str, object] | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class FileRecord:
    """File metadata record."""

    file_id: str
    organization_id: str
    type_id: str
    filename: str
    content_type: str
    size_bytes: int
    storage_key: str
    status: str
    uploaded_by: str
    owner_entity_id: str | None = None
    owner_entity_type: str | None = None
    content_hash: str | None = None
    storage_provider: str = "local"
    metadata: dict[str, object] = field(default_factory=dict)
    failure_reason: str | None = None
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)


@dataclass
class FileCreateResult:
    """Result of create_file — carries the record and whether it was a duplicate."""

    record: FileRecord
    deduplicated: bool


# region ORM Models
class FileTypeModel(Base):
    __tablename__ = "file_types"

    organization_id = Column(String(36), primary_key=True)
    type_id = Column(String(64), primary_key=True)
    display_name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    folder = Column(String(255), nullable=False)
    allowed_extensions = Column(JSON, nullable=False, default=list)
    max_size_mb = Column(Integer, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    is_system = Column(Boolean, nullable=False, default=False)
    metadata_json = Column("metadata", JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_file_types_org_active", "organization_id", "is_active"),)


class FileModel(Base):
    __tablename__ = "files"

    file_id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id = Column(String(36), nullable=False, index=True)
    type_id = Column(String(64), nullable=False, index=True)
    filename = Column(String(512), nullable=False)
    content_type = Column(String(255), nullable=False)
    size_bytes = Column(BIGINT, nullable=False)
    storage_key = Column(String(1024), nullable=False)
    status = Column(String(32), nullable=False, index=True)
    uploaded_by = Column(String(36), nullable=True)
    owner_entity_id = Column(String(36), nullable=True)
    owner_entity_type = Column(String(128), nullable=True)
    content_hash = Column(String(64), nullable=True)
    storage_provider = Column(String(32), nullable=True, server_default="local", default="local")
    metadata_json = Column("metadata", JSON, nullable=False, default=dict)
    failure_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ux_files_org_storage_key", "organization_id", "storage_key", unique=True),
        Index("ix_files_org_type_status", "organization_id", "type_id", "status"),
        Index("ix_files_org_created", "organization_id", "created_at"),
        Index(
            "ix_files_org_type_entity_created",
            "organization_id", "type_id", "owner_entity_id", "created_at",
        ),
        Index(
            "ix_files_org_entity_content_hash",
            "organization_id", "owner_entity_id", "content_hash",
            postgresql_where=sa.text("content_hash IS NOT NULL"),
        ),
    )


# endregion ORM Models


class FilehandlerModelService:
    """PostgreSQL persistence (or in-memory fallback) for file types and file metadata."""

    def __init__(self, database_service_manager: Any = None) -> None:
        self._use_memory = database_service_manager is None or not hasattr(
            database_service_manager, "postgres_db_service"
        )
        self.module_name = "filehandler"

        if self._use_memory:
            self._mem_file_types: dict[tuple[str, str], FileTypeRecord] = {}
            self._mem_files: dict[tuple[str, str], FileRecord] = {}
            self._mem_fs: dict[str, bytes] = {}
        else:
            self.database_service_manager = database_service_manager
            self.current_db = database_service_manager.postgres_db_service()
            self.current_db_engine = self.current_db.engine
            root = os.getenv("FILEHANDLER_LOCAL_STORAGE_ROOT", "/tmp/modular_filehandler")
            self._filesystem_root = Path(root)
            self._filesystem_root.mkdir(parents=True, exist_ok=True)

    def _filesystem_path(self, storage_key: str) -> Path:
        """SHA256 flat path — kept for callers that have not been migrated yet."""
        digest = hashlib.sha256(storage_key.encode("utf-8")).hexdigest()
        return self._filesystem_root / digest

    def _legacy_filesystem_path(self, storage_key: str) -> Path:
        """SHA256 hash path — fallback for files written before entity-organised storage."""
        digest = hashlib.sha256(storage_key.encode("utf-8")).hexdigest()
        return self._filesystem_root / digest

    def _new_filesystem_path(self, storage_key: str) -> Path:
        """Real subdirectory path — used for new entity-linked local file writes.

        Creates parent directories on first use so callers never have to mkdir
        themselves.
        """
        path = self._filesystem_root / storage_key
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _to_file_type_record(row: Any) -> FileTypeRecord:
        metadata = dict(row.metadata_json or {})
        upload_contexts = metadata.pop("_upload_contexts", None)
        agent_config = metadata.pop("_agent_config", None)
        return FileTypeRecord(
            organization_id=row.organization_id,
            type_id=row.type_id,
            display_name=row.display_name,
            description=str(row.description or ""),
            folder=row.folder,
            allowed_extensions=list(row.allowed_extensions or []),
            max_size_mb=int(row.max_size_mb),
            is_active=bool(row.is_active),
            is_system=bool(row.is_system),
            version_control_enabled=bool(metadata.get("version_control_enabled", False)),
            is_preview_thumbnail=bool(metadata.get("is_preview_thumbnail", False)),
            upload_contexts=upload_contexts,
            agent_config=agent_config,
            metadata=metadata,
        )

    @staticmethod
    def _to_file_record(row: Any) -> FileRecord:
        return FileRecord(
            file_id=row.file_id,
            organization_id=row.organization_id,
            type_id=row.type_id,
            filename=row.filename,
            content_type=row.content_type,
            size_bytes=int(row.size_bytes),
            storage_key=row.storage_key,
            status=row.status,
            uploaded_by=str(row.uploaded_by or ""),
            owner_entity_id=row.owner_entity_id,
            owner_entity_type=row.owner_entity_type,
            content_hash=row.content_hash,
            storage_provider=str(row.storage_provider or "local"),
            metadata=dict(row.metadata_json or {}),
            failure_reason=row.failure_reason,
            created_at=_to_iso(row.created_at),
            updated_at=_to_iso(row.updated_at),
        )

    def create_file_type(
        self, organization_id: str, request: FileTypeCreateRequest
    ) -> FileTypeRecord:
        is_thumbnail = bool(getattr(request, "is_preview_thumbnail", False))

        if self._use_memory:
            key = (organization_id, request.type_id)
            if key in self._mem_file_types:
                raise PersistenceError(f"File type '{request.type_id}' already exists")
            if is_thumbnail:
                for r in self._mem_file_types.values():
                    if r.organization_id == organization_id:
                        r.is_preview_thumbnail = False
                        r.metadata["is_preview_thumbnail"] = False
            record = FileTypeRecord(
                organization_id=organization_id,
                type_id=request.type_id,
                display_name=request.display_name,
                description=str(request.description or ""),
                folder=request.folder,
                allowed_extensions=[ext.lower() for ext in request.allowed_extensions],
                max_size_mb=request.max_size_mb,
                is_active=request.is_active,
                is_system=request.is_system,
                version_control_enabled=bool(request.version_control_enabled),
                is_preview_thumbnail=is_thumbnail,
                metadata={
                    **dict(request.metadata),
                    "version_control_enabled": bool(request.version_control_enabled),
                    "is_preview_thumbnail": is_thumbnail,
                },
            )
            self._mem_file_types[key] = record
            return record

        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                existing = (
                    db.query(FileTypeModel)
                    .filter(
                        and_(
                            FileTypeModel.organization_id == organization_id,
                            FileTypeModel.type_id == request.type_id,
                        )
                    )
                    .first()
                )
                if existing is not None:
                    raise PersistenceError(f"File type '{request.type_id}' already exists")

                if is_thumbnail:
                    self._clear_preview_thumbnail_flag_db(db, organization_id, except_type_id=request.type_id)

                row = FileTypeModel(
                    organization_id=organization_id,
                    type_id=request.type_id,
                    display_name=request.display_name,
                    description=request.description,
                    folder=request.folder,
                    allowed_extensions=[ext.lower() for ext in request.allowed_extensions],
                    max_size_mb=request.max_size_mb,
                    is_active=request.is_active,
                    is_system=request.is_system,
                    metadata_json={
                        **dict(request.metadata),
                        "version_control_enabled": bool(request.version_control_enabled),
                        "is_preview_thumbnail": is_thumbnail,
                        **({"_upload_contexts": request.upload_contexts} if request.upload_contexts is not None else {}),
                        **({"_agent_config": request.agent_config} if request.agent_config is not None else {}),
                    },
                )
                db.add(row)
                db.commit()
                db.refresh(row)
                return self._to_file_type_record(row)
        except PersistenceError:
            raise
        except Exception as exc:
            logger.debug("create_file_type persistence error: %s", exc)
            raise PersistenceError(f"Unable to create file type: {exc}") from exc

    def update_file_type(
        self, organization_id: str, type_id: str, request: FileTypeUpdateRequest
    ) -> FileTypeRecord:
        if self._use_memory:
            key = (organization_id, type_id)
            record = self._mem_file_types.get(key)
            if record is None:
                raise NotFoundError("file type not found")
            updates = request.model_dump(exclude_none=True)
            for field_name, value in updates.items():
                if field_name == "version_control_enabled":
                    record.metadata["version_control_enabled"] = bool(value)
                    record.version_control_enabled = bool(value)
                elif field_name == "is_preview_thumbnail":
                    if bool(value):
                        for r in self._mem_file_types.values():
                            if r.organization_id == organization_id and r.type_id != type_id:
                                r.is_preview_thumbnail = False
                                r.metadata["is_preview_thumbnail"] = False
                    record.is_preview_thumbnail = bool(value)
                    record.metadata["is_preview_thumbnail"] = bool(value)
                elif field_name == "metadata":
                    record.metadata = dict(value or {})
                else:
                    setattr(record, field_name, value)
            return record

        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                row = (
                    db.query(FileTypeModel)
                    .filter(
                        and_(
                            FileTypeModel.organization_id == organization_id,
                            FileTypeModel.type_id == type_id,
                        )
                    )
                    .first()
                )
                if row is None:
                    raise NotFoundError("file type not found")

                updates = request.model_dump(exclude_none=True)
                for field_name, value in updates.items():
                    if field_name == "version_control_enabled":
                        metadata = dict(row.metadata_json or {})
                        metadata["version_control_enabled"] = bool(value)
                        row.metadata_json = metadata
                        continue
                    if field_name == "is_preview_thumbnail":
                        if bool(value):
                            self._clear_preview_thumbnail_flag_db(db, organization_id, except_type_id=type_id)
                        metadata = dict(row.metadata_json or {})
                        metadata["is_preview_thumbnail"] = bool(value)
                        row.metadata_json = metadata
                        continue
                    if field_name in ("upload_contexts", "agent_config"):
                        metadata = dict(row.metadata_json or {})
                        metadata[f"_{field_name}"] = value
                        row.metadata_json = metadata
                        continue
                    if field_name == "metadata":
                        metadata = dict(value or {})
                        metadata["version_control_enabled"] = bool(
                            updates.get(
                                "version_control_enabled",
                                metadata.get("version_control_enabled", False),
                            )
                        )
                        # Preserve internal keys (_upload_contexts, _agent_config, etc.)
                        # written by earlier iterations of this loop.
                        existing = dict(row.metadata_json or {})
                        for k, v in existing.items():
                            if k.startswith("_"):
                                metadata.setdefault(k, v)
                        row.metadata_json = metadata
                    else:
                        setattr(row, field_name, value)
                db.commit()
                db.refresh(row)
                return self._to_file_type_record(row)
        except NotFoundError:
            raise
        except Exception as exc:
            logger.debug("update_file_type persistence error: %s", exc)
            raise PersistenceError(f"Unable to update file type: {exc}") from exc

    def get_file_type(self, organization_id: str, type_id: str) -> FileTypeRecord | None:
        if self._use_memory:
            return self._mem_file_types.get((organization_id, type_id))

        with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
            row = (
                db.query(FileTypeModel)
                .filter(
                    and_(
                        FileTypeModel.organization_id == organization_id,
                        FileTypeModel.type_id == type_id,
                    )
                )
                .first()
            )
            return self._to_file_type_record(row) if row else None

    def list_file_types(
        self, organization_id: str, active_only: bool = True
    ) -> list[FileTypeRecord]:
        if self._use_memory:
            records = [v for (org, _), v in self._mem_file_types.items() if org == organization_id]
            if active_only:
                records = [r for r in records if r.is_active]
            return sorted(records, key=lambda r: r.display_name)

        with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
            query = db.query(FileTypeModel).filter(FileTypeModel.organization_id == organization_id)
            if active_only:
                query = query.filter(FileTypeModel.is_active.is_(True))
            rows = query.order_by(FileTypeModel.display_name.asc()).all()
            return [self._to_file_type_record(row) for row in rows]

    def delete_file_type(self, organization_id: str, type_id: str) -> bool:
        if self._use_memory:
            key = (organization_id, type_id)
            record = self._mem_file_types.get(key)
            if record is None:
                return False
            if record.is_system:
                raise PersistenceError(f"Cannot delete system file type '{type_id}'")
            del self._mem_file_types[key]
            return True

        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                row = (
                    db.query(FileTypeModel)
                    .filter(
                        and_(
                            FileTypeModel.organization_id == organization_id,
                            FileTypeModel.type_id == type_id,
                        )
                    )
                    .first()
                )
                if row is None:
                    return False
                if row.is_system:
                    raise PersistenceError(f"Cannot delete system file type '{type_id}'")
                db.delete(row)
                db.commit()
                return True
        except PersistenceError:
            raise
        except Exception as exc:
            logger.debug("delete_file_type persistence error: %s", exc)
            raise PersistenceError(f"Unable to delete file type: {exc}") from exc

    @staticmethod
    def _clear_preview_thumbnail_flag_db(db: Session, organization_id: str, except_type_id: str) -> None:
        """Clear is_preview_thumbnail from all file types in the org except the given one."""
        rows = (
            db.query(FileTypeModel)
            .filter(
                and_(
                    FileTypeModel.organization_id == organization_id,
                    FileTypeModel.type_id != except_type_id,
                )
            )
            .all()
        )
        for r in rows:
            meta = dict(r.metadata_json or {})
            if meta.get("is_preview_thumbnail"):
                meta["is_preview_thumbnail"] = False
                r.metadata_json = meta

    def get_preview_thumbnail_file_type(self, organization_id: str) -> FileTypeRecord | None:
        """Return the single file type marked as preview thumbnail for this org, or None."""
        if self._use_memory:
            for r in self._mem_file_types.values():
                if r.organization_id == organization_id and r.is_preview_thumbnail:
                    return r
            return None

        with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
            rows = (
                db.query(FileTypeModel)
                .filter(FileTypeModel.organization_id == organization_id)
                .all()
            )
            for row in rows:
                meta = dict(row.metadata_json or {})
                if meta.get("is_preview_thumbnail"):
                    return self._to_file_type_record(row)
            return None

    def get_first_file_for_entity_type(
        self, organization_id: str, entity_id: str, type_id: str
    ) -> FileRecord | None:
        """Return the earliest non-deleted file uploaded for an entity of the given type."""
        if self._use_memory:
            candidates = [
                r for r in self._mem_files.values()
                if (
                    r.organization_id == organization_id
                    and r.owner_entity_id == entity_id
                    and r.type_id == type_id
                    and r.status != FileRecordStatus.DELETED.value
                )
            ]
            if not candidates:
                return None
            return min(candidates, key=lambda r: r.created_at)

        with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
            row = (
                db.query(FileModel)
                .filter(
                    and_(
                        FileModel.organization_id == organization_id,
                        FileModel.owner_entity_id == entity_id,
                        FileModel.type_id == type_id,
                        FileModel.status != FileRecordStatus.DELETED.value,
                    )
                )
                .order_by(FileModel.created_at.asc())
                .first()
            )
            return self._to_file_record(row) if row else None

    def get_first_files_for_entities_type(
        self, organization_id: str, entity_ids: set[str], type_id: str
    ) -> dict[str, FileRecord]:
        """Return the earliest matching file per entity in one persistence call."""
        if not entity_ids:
            return {}
        if self._use_memory:
            result: dict[str, FileRecord] = {}
            candidates = sorted(self._mem_files.values(), key=lambda record: record.created_at)
            for record in candidates:
                if (
                    record.organization_id == organization_id
                    and record.owner_entity_id in entity_ids
                    and record.type_id == type_id
                    and record.status != FileRecordStatus.DELETED.value
                ):
                    result.setdefault(str(record.owner_entity_id), record)
            return result

        with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
            rows = (
                db.query(FileModel)
                .filter(
                    FileModel.organization_id == organization_id,
                    FileModel.owner_entity_id.in_(entity_ids),
                    FileModel.type_id == type_id,
                    FileModel.status != FileRecordStatus.DELETED.value,
                )
                .order_by(FileModel.owner_entity_id.asc(), FileModel.created_at.asc())
                .all()
            )
            result: dict[str, FileRecord] = {}
            for row in rows:
                if row.owner_entity_id is not None:
                    result.setdefault(row.owner_entity_id, self._to_file_record(row))
            return result

    def seed_default_file_types(self, organization_id: str) -> int:
        defaults = [
            {
                "type_id": "generic_text",
                "display_name": "Generic Text",
                "description": "Text documents",
                "folder": "text_files",
                "allowed_extensions": [".txt", ".md", ".json"],
                "max_size_mb": 10,
                "is_active": True,
                "is_system": True,
                "metadata": {"llm_mode_default": "extract"},
            },
            {
                "type_id": "generic_document",
                "display_name": "Generic Document",
                "description": "PDF and office documents",
                "folder": "documents",
                "allowed_extensions": [
                    ".pdf",
                    ".doc",
                    ".docx",
                    ".xls",
                    ".xlsx",
                    ".csv",
                    ".png",
                    ".jpg",
                ],
                "max_size_mb": 20,
                "is_active": True,
                "is_system": True,
                "metadata": {"llm_mode_default": "full"},
            },
            {
                "type_id": "org_logo",
                "display_name": "Organization Logo",
                "description": "Organization branding logo image",
                "folder": "branding",
                "allowed_extensions": [".png", ".jpg", ".jpeg", ".svg", ".webp"],
                "max_size_mb": 5,
                "is_active": True,
                "is_system": True,
                "metadata": {},
            },
        ]

        created = 0
        for item in defaults:
            try:
                self.create_file_type(organization_id, FileTypeCreateRequest.model_validate(item))
                created += 1
            except PersistenceError:
                continue
        return created

    def create_file(
        self,
        organization_id: str,
        upload_request: FileUploadRequest,
        uploaded_by: str,
        file_bytes: bytes | None = None,
        storage_provider: str = "local",
        entity_type_slug: str | None = None,
    ) -> FileCreateResult:
        """Persist an uploaded file record and write bytes to the chosen storage backend."""
        if file_bytes is None:
            file_bytes = base64.b64decode(upload_request.content.encode("utf-8"), validate=False)
        content_hash = hashlib.sha256(file_bytes).hexdigest()

        if self._use_memory:
            # New record per upload with a unique filename (mirrors DB path).
            existing_names = {
                record.filename
                for record in self._mem_files.values()
                if record.organization_id == organization_id
                and record.owner_entity_id == upload_request.owner_entity_id
                and record.type_id == upload_request.type_id
                and record.status != FileRecordStatus.DELETED.value
            }
            upload_request = upload_request.model_copy(
                update={
                    "filename": self._next_available_filename(
                        upload_request.filename, existing_names
                    )
                }
            )

            row_id = str(uuid4())
            storage_key = self._build_storage_key(
                organization_id, upload_request, row_id, entity_type_slug
            )
            self._mem_fs[storage_key] = file_bytes
            record = FileRecord(
                file_id=row_id,
                organization_id=organization_id,
                type_id=upload_request.type_id,
                filename=upload_request.filename,
                content_type=upload_request.content_type,
                size_bytes=len(file_bytes),
                storage_key=storage_key,
                status=FileRecordStatus.UPLOADED.value,
                uploaded_by=uploaded_by,
                owner_entity_id=upload_request.owner_entity_id,
                owner_entity_type=upload_request.owner_entity_type,
                content_hash=content_hash,
                metadata=dict(upload_request.metadata),
            )
            self._mem_files[(organization_id, row_id)] = record
            return FileCreateResult(record=record, deduplicated=False)

        return self._create_file_db(
            organization_id, upload_request, uploaded_by, file_bytes, content_hash,
            storage_provider, entity_type_slug,
        )

    @staticmethod
    def _next_available_filename(filename: str, existing_names: set[str]) -> str:
        """Return filename or the next ``name (n).ext`` variant in its scope."""
        normalized_names = {name.casefold() for name in existing_names}
        if filename.casefold() not in normalized_names:
            return filename

        stem, extension = os.path.splitext(filename)
        numbered_match = re.fullmatch(r"(.*) \((\d+)\)", stem)
        base_stem = numbered_match.group(1) if numbered_match else stem
        suffix = 1
        while f"{base_stem} ({suffix}){extension}".casefold() in normalized_names:
            suffix += 1
        return f"{base_stem} ({suffix}){extension}"

    @staticmethod
    def _new_file_row(
        row_id: str,
        organization_id: str,
        upload_request: FileUploadRequest,
        uploaded_by: str,
        file_bytes: bytes,
        storage_key: str,
        content_hash: str,
        storage_provider: str = "local",
    ) -> FileModel:
        """Build an unpersisted FileModel row from an upload request."""
        return FileModel(
            file_id=row_id,
            organization_id=organization_id,
            type_id=upload_request.type_id,
            filename=upload_request.filename,
            content_type=upload_request.content_type,
            size_bytes=len(file_bytes),
            storage_key=storage_key,
            status=FileRecordStatus.UPLOADED.value,
            uploaded_by=uploaded_by,
            owner_entity_id=upload_request.owner_entity_id,
            owner_entity_type=upload_request.owner_entity_type,
            content_hash=content_hash,
            storage_provider=storage_provider,
            metadata_json=dict(upload_request.metadata),
        )

    @staticmethod
    def _build_storage_key(
        organization_id: str,
        upload_request: FileUploadRequest,
        row_id: str,
        entity_type_slug: str | None = None,
    ) -> str:
        """Build the storage key for a new file record."""
        folder_segment = f"/{upload_request.upload_folder}" if upload_request.upload_folder else ""
        if entity_type_slug and upload_request.owner_entity_id:
            return (
                f"{organization_id}/{entity_type_slug}/{upload_request.owner_entity_id}"
                f"/{upload_request.type_id}{folder_segment}/{row_id}_{upload_request.filename}"
            )
        return (
            f"{organization_id}/{upload_request.type_id}{folder_segment}/{row_id}/{upload_request.filename}"
        )

    def _discard_written_file(self, written_path: Path | None) -> None:
        """Delete the file we wrote to disk when its DB row was not persisted.

        Receives the exact path that was written so there is no ambiguity between
        legacy SHA256 paths and new real-directory paths.
        """
        if written_path is not None:
            written_path.unlink(missing_ok=True)

    def _create_file_db(
        self,
        organization_id: str,
        upload_request: FileUploadRequest,
        uploaded_by: str,
        file_bytes: bytes,
        content_hash: str,
        storage_provider: str = "local",
        entity_type_slug: str | None = None,
    ) -> FileCreateResult:
        """Write file bytes and insert a DB row; rolls back on any failure."""
        written_path: Path | None = None
        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                existing_names = {
                    name
                    for (name,) in db.query(FileModel.filename)
                    .filter(
                        FileModel.organization_id == organization_id,
                        FileModel.owner_entity_id == upload_request.owner_entity_id,
                        FileModel.type_id == upload_request.type_id,
                        FileModel.status != FileRecordStatus.DELETED.value,
                    )
                    .all()
                }
                upload_request = upload_request.model_copy(
                    update={
                        "filename": self._next_available_filename(
                            upload_request.filename, existing_names
                        )
                    }
                )

                row_id = str(uuid4())
                storage_key = self._build_storage_key(
                    organization_id, upload_request, row_id, entity_type_slug
                )

                if storage_provider == "local":
                    if entity_type_slug and upload_request.owner_entity_id:
                        written_path = self._new_filesystem_path(storage_key)
                    else:
                        written_path = self._legacy_filesystem_path(storage_key)
                    written_path.write_bytes(file_bytes)

                row = self._new_file_row(
                    row_id, organization_id, upload_request, uploaded_by,
                    file_bytes, storage_key, content_hash,
                    storage_provider=storage_provider,
                )
                db.add(row)
                db.commit()
                db.refresh(row)
            return FileCreateResult(record=self._to_file_record(row), deduplicated=False)
        except Exception as exc:
            logger.debug("create_file persistence error: %s", exc)
            self._discard_written_file(written_path)
            raise PersistenceError(f"Unable to create file: {exc}") from exc

    def get_file(
        self, organization_id: str, file_id: str, owner_entity_id: str | None = None
    ) -> FileRecord | None:
        if self._use_memory:
            record = self._mem_files.get((organization_id, file_id))
            if record is None:
                return None
            if owner_entity_id is not None and record.owner_entity_id != owner_entity_id:
                return None
            return record

        with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
            filters = [
                FileModel.organization_id == organization_id,
                FileModel.file_id == file_id,
            ]
            if owner_entity_id is not None:
                filters.append(FileModel.owner_entity_id == owner_entity_id)
            row = db.query(FileModel).filter(and_(*filters)).first()
            return self._to_file_record(row) if row else None

    def merge_file_metadata(
        self,
        organization_id: str,
        file_id: str,
        metadata: dict[str, object],
    ) -> FileRecord | None:
        if not metadata:
            return self.get_file(organization_id, file_id)

        if self._use_memory:
            record = self._mem_files.get((organization_id, file_id))
            if record is None:
                return None
            record.metadata = {**dict(record.metadata or {}), **dict(metadata)}
            record.updated_at = _utc_now()
            return record

        with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
            row = (
                db.query(FileModel)
                .filter(
                    and_(
                        FileModel.organization_id == organization_id,
                        FileModel.file_id == file_id,
                    )
                )
                .first()
            )
            if row is None:
                return None
            row.metadata_json = {**dict(row.metadata_json or {}), **dict(metadata)}
            row.updated_at = datetime.now(UTC)
            db.commit()
            db.refresh(row)
            return self._to_file_record(row)

    def get_file_by_id(self, file_id: str) -> FileRecord | None:
        """Fetch a file record by file_id alone (no org filter) — used by unauthenticated serve."""
        if self._use_memory:
            for (_, fid), record in self._mem_files.items():
                if fid == file_id:
                    return record
            return None

        with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
            row = db.query(FileModel).filter(FileModel.file_id == file_id).first()
            return self._to_file_record(row) if row else None

    def list_files(
        self,
        organization_id: str,
        type_id: str | None = None,
        status: str | None = None,
        owner_entity_id: str | None = None,
    ) -> list[FileRecord]:
        if self._use_memory:
            records = [v for (org, _), v in self._mem_files.items() if org == organization_id]
            if type_id:
                records = [r for r in records if r.type_id == type_id]
            if status:
                records = [r for r in records if r.status == status]
            else:
                records = [r for r in records if r.status != FileRecordStatus.DELETED.value]
            if owner_entity_id:
                records = [r for r in records if r.owner_entity_id == owner_entity_id]
            return sorted(records, key=lambda r: r.created_at)

        with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
            query = db.query(FileModel).filter(FileModel.organization_id == organization_id)
            if type_id:
                query = query.filter(FileModel.type_id == type_id)
            if status:
                query = query.filter(FileModel.status == status)
            else:
                query = query.filter(FileModel.status != FileRecordStatus.DELETED.value)
            if owner_entity_id:
                query = query.filter(FileModel.owner_entity_id == owner_entity_id)
            rows = query.order_by(FileModel.created_at.asc()).all()
            return [self._to_file_record(row) for row in rows]

    def delete_file(self, organization_id: str, file_id: str) -> bool:
        if self._use_memory:
            key = (organization_id, file_id)
            record = self._mem_files.get(key)
            if record is None:
                return False
            record.status = FileRecordStatus.DELETED.value
            record.updated_at = _utc_now()
            self._mem_fs.pop(record.storage_key, None)
            return True

        with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
            row = (
                db.query(FileModel)
                .filter(
                    and_(FileModel.organization_id == organization_id, FileModel.file_id == file_id)
                )
                .first()
            )
            if row is None:
                return False
            row.status = FileRecordStatus.DELETED.value
            row.updated_at = datetime.now(UTC)
            db.commit()
            new_path = self._filesystem_root / row.storage_key
            if new_path.exists():
                new_path.unlink(missing_ok=True)
            else:
                self._legacy_filesystem_path(row.storage_key).unlink(missing_ok=True)
            return True

    def get_filesystem_content_by_storage_key(self, storage_key: str) -> bytes | None:
        """Read file bytes by storage key; tries real subdirectory path first, then legacy SHA256."""
        if self._use_memory:
            return self._mem_fs.get(storage_key)

        new_path = self._filesystem_root / storage_key
        if new_path.exists():
            return new_path.read_bytes()

        legacy_path = self._legacy_filesystem_path(storage_key)
        if legacy_path.exists():
            return legacy_path.read_bytes()

        return None

    def get_file_by_storage_key(self, organization_id: str, storage_key: str) -> FileRecord | None:
        if self._use_memory:
            for (org, _), record in self._mem_files.items():
                if org == organization_id and record.storage_key == storage_key:
                    return record
            return None

        with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
            row = (
                db.query(FileModel)
                .filter(
                    and_(
                        FileModel.organization_id == organization_id,
                        FileModel.storage_key == storage_key,
                    )
                )
                .first()
            )
            return self._to_file_record(row) if row else None

    def set_file_storage_provider(
        self, organization_id: str, file_id: str, storage_provider: str
    ) -> None:
        if self._use_memory:
            record = self._mem_files.get((organization_id, file_id))
            if record is None:
                raise NotFoundError("file not found")
            record.storage_provider = storage_provider
            record.updated_at = _utc_now()
            return

        with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
            row = (
                db.query(FileModel)
                .filter(
                    and_(FileModel.organization_id == organization_id, FileModel.file_id == file_id)
                )
                .first()
            )
            if row is None:
                raise NotFoundError("file not found")
            row.storage_provider = storage_provider
            row.updated_at = datetime.now(UTC)
            db.commit()

    def set_file_status(
        self, organization_id: str, file_id: str, status: str, failure_reason: str | None = None
    ) -> None:
        if self._use_memory:
            record = self._mem_files.get((organization_id, file_id))
            if record is None:
                raise NotFoundError("file not found")
            record.status = status
            record.failure_reason = failure_reason
            record.updated_at = _utc_now()
            return

        with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
            row = (
                db.query(FileModel)
                .filter(
                    and_(FileModel.organization_id == organization_id, FileModel.file_id == file_id)
                )
                .first()
            )
            if row is None:
                raise NotFoundError("file not found")
            row.status = status
            row.failure_reason = failure_reason
            row.updated_at = datetime.now(UTC)
            db.commit()

    def set_file_owner(
        self,
        organization_id: str,
        file_id: str,
        owner_entity_id: str,
        owner_entity_type: str | None = None,
    ) -> None:
        """Attach an existing file to an entity (in place, no copy).

        Used when a file was uploaded before the entity existed (document-upload-driven
        entity creation) — the entity's own document list is filtered by owner_entity_id,
        so without this the file stays permanently invisible there.
        """
        if self._use_memory:
            record = self._mem_files.get((organization_id, file_id))
            if record is None:
                raise NotFoundError("file not found")
            record.owner_entity_id = owner_entity_id
            record.owner_entity_type = owner_entity_type
            record.updated_at = _utc_now()
            return

        with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
            row = (
                db.query(FileModel)
                .filter(
                    and_(FileModel.organization_id == organization_id, FileModel.file_id == file_id)
                )
                .first()
            )
            if row is None:
                raise NotFoundError("file not found")
            row.owner_entity_id = owner_entity_id
            row.owner_entity_type = owner_entity_type
            row.updated_at = datetime.now(UTC)
            db.commit()
