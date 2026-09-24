"""Relationship execution service for entity records."""

from __future__ import annotations

from typing import TYPE_CHECKING

from common.logger import logger
from entities.models.interface import IDENTIFIER_FIELD_KEY, RelationType
from entities.models.request import EntityRelationCreateRequest
from entities.models.response import (
    EntityRecordResponse,
    EntityRelationListResponse,
    EntityRelationResponse,
    RelatedEntityFileGroupResponse,
    RelatedEntityFileListResponse,
    RelatedEntityFileResponse,
)
from exceptions import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ServiceError,
    ValidationError,
)

if TYPE_CHECKING:
    from entities.manager import EntitiesServiceManager


class RelationshipsService:
    """Own relationship execution while the manager remains the public facade."""

    RELATED_FILES_METADATA_KEY = "related_files"
    SNAPSHOT_FILE_METADATA_KEY = "related_file_snapshot"

    def __init__(self, manager: EntitiesServiceManager) -> None:
        self.manager = manager
        self.db = manager.db_model_service

    @staticmethod
    def _related_files_config(metadata: dict[str, object] | None) -> dict[str, object] | None:
        raw = dict(metadata or {}).get(RelationshipsService.RELATED_FILES_METADATA_KEY)
        if not isinstance(raw, dict) or not bool(raw.get("enabled")):
            return None
        return raw

    @staticmethod
    def _file_type_allowed(file_type_id: str, config: dict[str, object] | None) -> bool:
        raw = (config or {}).get("include_file_type_ids")
        if not isinstance(raw, list) or not raw:
            return True
        return file_type_id in {str(item) for item in raw if str(item).strip()}

    @staticmethod
    def _entity_label(record: EntityRecordResponse) -> str:
        data = dict(record.data or {})
        for key in (IDENTIFIER_FIELD_KEY, "name", "title", "display_name"):
            value = data.get(key)
            if value is not None and str(value).strip():
                return str(value)
        return record.entity_id

    def _snapshot_metadata(
        self,
        *,
        source_entity_id: str,
        source_entity_type_id: str,
        source_file_id: str,
        relation_def_id: str,
    ) -> dict[str, object]:
        return {
            self.SNAPSHOT_FILE_METADATA_KEY: True,
            "source_entity_id": source_entity_id,
            "source_entity_type_id": source_entity_type_id,
            "source_file_id": source_file_id,
            "relation_def_id": relation_def_id,
        }

    def copy_snapshot_files_for_relation(
        self,
        *,
        organization_id: str,
        actor_id: str,
        from_entity_id: str,
        to_entity_id: str,
        relation_type: str,
    ) -> None:
        """Best-effort copy for configured SNAPSHOT related files."""
        filehandler = self.manager.filehandler_service_manager
        if relation_type != RelationType.SNAPSHOT.value or filehandler is None:
            return
        source = self.manager.get_entity_record(
            organization_id=organization_id, entity_id=from_entity_id
        )
        target = self.manager.get_entity_record(
            organization_id=organization_id, entity_id=to_entity_id
        )
        if source is None or target is None:
            return
        declaration = self.db.get_active_relation_declaration_for_pair(
            organization_id=organization_id,
            from_entity_type_id=source.entity_type_id,
            to_entity_type_id=target.entity_type_id,
        )
        if declaration is None or declaration.relation_type != RelationType.SNAPSHOT:
            return
        config = self._related_files_config(dict(declaration.relation_metadata or {}))
        if config is None:
            return

        files = filehandler.db_model_service.list_files(
            organization_id, owner_entity_id=from_entity_id
        )
        for file_record in files:
            if not self._file_type_allowed(file_record.type_id, config):
                continue
            if bool(dict(file_record.metadata or {}).get(self.SNAPSHOT_FILE_METADATA_KEY)):
                continue
            try:
                filehandler.copy_file_to_entity(
                    organization_id,
                    actor_id,
                    source_file_id=file_record.file_id,
                    target_entity_id=to_entity_id,
                    metadata=self._snapshot_metadata(
                        source_entity_id=from_entity_id,
                        source_entity_type_id=source.entity_type_id,
                        source_file_id=file_record.file_id,
                        relation_def_id=declaration.relation_def_id,
                    ),
                )
            except Exception:
                logger.warning(
                    "snapshot related file copy failed",
                    extra={
                        "source_entity_id": from_entity_id,
                        "target_entity_id": to_entity_id,
                        "source_file_id": file_record.file_id,
                    },
                    exc_info=True,
                )

    def copy_snapshot_files_for_entity(
        self,
        *,
        organization_id: str,
        target_entity_id: str,
        actor_id: str,
    ) -> None:
        if self.manager.filehandler_service_manager is None:
            return
        relations = self.db.list_entity_relations_for_entity(
            organization_id=organization_id,
            entity_id=target_entity_id,
            direction="in",
            relation_type=RelationType.SNAPSHOT.value,
        )
        for relation in relations:
            self.copy_snapshot_files_for_relation(
                organization_id=organization_id,
                actor_id=actor_id,
                from_entity_id=relation.from_entity_id,
                to_entity_id=relation.to_entity_id,
                relation_type=relation.relation_type,
            )

    def create_for_actor(
        self,
        actor: dict[str, object],
        entity_id: str,
        request: EntityRelationCreateRequest,
    ) -> EntityRelationResponse:
        """Create relation between two entities after RBAC check and tenant pre-flight."""
        organization_id = request.organization_id or self.manager._require_actor_field(
            actor, "organization_id"
        )
        self.manager._authorize_actor_operation(
            actor, "entity_relation", "write", organization_id
        )
        if request.from_entity_id != entity_id:
            raise ValidationError(
                f"path entity_id '{entity_id}' must match from_entity_id '{request.from_entity_id}'"
            )
        normalized = EntityRelationCreateRequest(
            organization_id=organization_id,
            from_entity_id=request.from_entity_id,
            to_entity_id=request.to_entity_id,
            relation_type=request.relation_type,
            relation_metadata=(
                dict(request.relation_metadata) if request.relation_metadata is not None else None
            ),
        )
        try:
            existing = self.db.entity_records_exist_in_org(
                organization_id=organization_id,
                entity_ids=[normalized.from_entity_id, normalized.to_entity_id],
            )
            missing = [
                eid
                for eid in (normalized.from_entity_id, normalized.to_entity_id)
                if eid not in existing
            ]
            if missing:
                raise ValidationError(
                    f"entity record(s) {missing} not found in organization '{organization_id}'"
                )
            record = self.db.create_entity_relation(normalized)
            self.copy_snapshot_files_for_relation(
                organization_id=organization_id,
                actor_id=str(actor.get("user_id") or "system"),
                from_entity_id=record.from_entity_id,
                to_entity_id=record.to_entity_id,
                relation_type=record.relation_type,
            )
            return self.manager._entity_relation_response(record)
        except (ConflictError, ValidationError, AuthorizationError, NotFoundError):
            raise
        except ValueError as exc:
            logger.debug("create_entity_relation_for_actor ValueError: %s", exc)
            raise ValidationError(str(exc)) from exc
        except Exception as exc:
            logger.debug("create_entity_relation_for_actor failed: %s", exc)
            raise ServiceError(f"Unable to create entity relation: {exc}") from exc

    def list_for_actor(
        self,
        actor: dict[str, object],
        entity_id: str,
        direction: str = "both",
        relation_type: str | None = None,
    ) -> EntityRelationListResponse:
        """List relations for an entity after RBAC check."""
        organization_id = self.manager._require_actor_field(actor, "organization_id")
        self.manager._authorize_actor_operation(
            actor, "entity_relation", "read", organization_id
        )
        try:
            records = self.db.list_entity_relations_for_entity(
                organization_id=organization_id,
                entity_id=entity_id,
                direction=direction,
                relation_type=relation_type,
            )
            items = [self.manager._entity_relation_response(record) for record in records]
            return EntityRelationListResponse(
                organization_id=organization_id, entity_id=entity_id, items=items
            )
        except (ValidationError, AuthorizationError, NotFoundError):
            raise
        except Exception as exc:
            logger.debug("list_entity_relations_for_actor failed: %s", exc)
            raise ServiceError(f"Unable to list entity relations: {exc}") from exc

    def delete_for_actor(
        self,
        actor: dict[str, object],
        relation_id: str,
    ) -> EntityRelationResponse:
        """Delete a relation by id after RBAC check."""
        organization_id = self.manager._require_actor_field(actor, "organization_id")
        self.manager._authorize_actor_operation(
            actor, "entity_relation", "write", organization_id
        )
        try:
            record = self.db.delete_entity_relation(
                organization_id=organization_id, relation_id=relation_id
            )
            if record is None:
                raise NotFoundError(f"entity relation '{relation_id}' not found")
            return self.manager._entity_relation_response(record)
        except (ValidationError, AuthorizationError, NotFoundError):
            raise
        except Exception as exc:
            logger.debug("delete_entity_relation_for_actor failed: %s", exc)
            raise ServiceError(f"Unable to delete entity relation: {exc}") from exc

    def list_related_files_for_actor(
        self,
        actor: dict[str, object],
        entity_id: str,
    ) -> RelatedEntityFileListResponse:
        """List read-only files exposed by configured incoming relation declarations."""
        organization_id = self.manager._require_actor_field(actor, "organization_id")
        self.manager._authorize_actor_operation(actor, "file", "read", organization_id)
        target = self.manager.get_entity_record_for_actor(actor, entity_id, organization_id)
        filehandler = self.manager.filehandler_service_manager
        if filehandler is None:
            return RelatedEntityFileListResponse(
                organization_id=organization_id, entity_id=entity_id
            )

        declarations = self.db.get_active_relation_declarations_by_to_type(
            organization_id=organization_id,
            to_entity_type_id=target.entity_type_id,
        )
        enabled: dict[str, tuple[object, dict[str, object]]] = {}
        for declaration in declarations:
            config = self._related_files_config(dict(declaration.relation_metadata or {}))
            if config is not None:
                enabled[declaration.relation_def_id] = (declaration, config)
        if not enabled:
            return RelatedEntityFileListResponse(
                organization_id=organization_id,
                entity_id=entity_id,
                configured=False,
            )

        groups: dict[tuple[str, str], RelatedEntityFileGroupResponse] = {}

        def add_file(
            source: EntityRecordResponse,
            declaration,
            config: dict[str, object],
            file_record,
        ) -> None:
            if not self._file_type_allowed(file_record.type_id, config):
                return
            source_label = self._entity_label(source)
            group_key = (source.entity_id, declaration.relation_def_id)
            group = groups.get(group_key)
            if group is None:
                group = RelatedEntityFileGroupResponse(
                    source_entity_id=source.entity_id,
                    source_entity_type_id=source.entity_type_id,
                    source_entity_label=source_label,
                    relation_type=declaration.relation_type,
                    relation_def_id=declaration.relation_def_id,
                    files=[],
                )
                groups[group_key] = group
            group.files.append(
                RelatedEntityFileResponse(
                    file_id=file_record.file_id,
                    type_id=file_record.type_id,
                    filename=file_record.filename,
                    content_type=file_record.content_type,
                    size_bytes=file_record.size_bytes,
                    storage_key=file_record.storage_key,
                    status=file_record.status,
                    uploaded_by=file_record.uploaded_by,
                    owner_entity_id=file_record.owner_entity_id,
                    owner_entity_type=file_record.owner_entity_type,
                    storage_provider=getattr(file_record, "storage_provider", "local"),
                    metadata=dict(file_record.metadata or {}),
                    created_at=file_record.created_at,
                    updated_at=file_record.updated_at,
                    relation_type=declaration.relation_type,
                    relation_def_id=declaration.relation_def_id,
                    source_entity_id=source.entity_id,
                    source_entity_type_id=source.entity_type_id,
                    source_entity_label=source_label,
                )
            )

        incoming = self.db.list_entity_relations_for_entity(
            organization_id=organization_id,
            entity_id=entity_id,
            direction="in",
        )
        active_snapshot_sources: set[tuple[str, str]] = set()
        for relation in incoming:
            source = self.manager.get_entity_record(
                organization_id=organization_id, entity_id=relation.from_entity_id
            )
            if source is None:
                continue
            matches = [
                (declaration, config)
                for declaration, config in enabled.values()
                if declaration.from_entity_type_id == source.entity_type_id
                and declaration.relation_type.value == relation.relation_type
            ]
            if not matches:
                continue
            try:
                guarded_source = self.manager.guard_read(
                    actor, organization_id, source.entity_type_id, source
                )
            except AuthorizationError:
                continue
            for declaration, config in matches:
                if declaration.relation_type == RelationType.SNAPSHOT:
                    active_snapshot_sources.add(
                        (relation.from_entity_id, declaration.relation_def_id)
                    )
                    continue
                if declaration.relation_type != RelationType.REFERENCE:
                    continue
                files = filehandler.db_model_service.list_files(
                    organization_id, owner_entity_id=relation.from_entity_id
                )
                for file_record in files:
                    if bool(dict(file_record.metadata or {}).get(self.SNAPSHOT_FILE_METADATA_KEY)):
                        continue
                    add_file(guarded_source, declaration, config, file_record)

        snapshot_files = filehandler.db_model_service.list_files(
            organization_id, owner_entity_id=entity_id
        )
        for file_record in snapshot_files:
            metadata = dict(file_record.metadata or {})
            if not bool(metadata.get(self.SNAPSHOT_FILE_METADATA_KEY)):
                continue
            relation_def_id = str(metadata.get("relation_def_id") or "")
            enabled_pair = enabled.get(relation_def_id)
            if enabled_pair is None:
                continue
            declaration, config = enabled_pair
            if declaration.relation_type != RelationType.SNAPSHOT:
                continue
            source_entity_id = str(metadata.get("source_entity_id") or "")
            if (source_entity_id, relation_def_id) not in active_snapshot_sources:
                continue
            source = self.manager.get_entity_record(
                organization_id=organization_id, entity_id=source_entity_id
            )
            if source is None:
                continue
            try:
                guarded_source = self.manager.guard_read(
                    actor, organization_id, source.entity_type_id, source
                )
            except AuthorizationError:
                continue
            add_file(guarded_source, declaration, config, file_record)

        group_list = list(groups.values())
        for group in group_list:
            group.files.sort(key=lambda item: item.created_at, reverse=True)
        group_list.sort(key=lambda group: group.source_entity_label.lower())
        return RelatedEntityFileListResponse(
            organization_id=organization_id,
            entity_id=entity_id,
            configured=True,
            count=sum(len(group.files) for group in group_list),
            groups=group_list,
        )
