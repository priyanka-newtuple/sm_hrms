"""Persistence adapters for the comments module.

Owns the Comment SQLAlchemy model and the CommentModelService DB operations.
Each method receives the per-request DB session as a parameter. `session_scope`
is the one exception, for callers that have no request to inherit a session from.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB

from common.logger import logger
from database.manager import Base
from entities.db_models import EntityRecordModel, EntityStateRuntimeModel, EntityTypeModel
from entities.models.interface import IDENTIFIER_FIELD_KEY
from workflow.db_models import WorkflowStateMachineModel
from exceptions import PersistenceError, ServiceError, ValidationError
from notifications.db_models import Notification
from user.db_models import User

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.orm import Session


def _runtime_schema() -> str:
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    return f"{app_schema}_runtime"


# ── SQLAlchemy Models ─────────────────────────────────────────────────────────


class Comment(Base):
    """Persisted comment attached to an entity, optionally scoped to a workflow state."""

    __tablename__ = "comments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id = Column(String(36), nullable=False, index=True)
    entity_id = Column(String(36), nullable=False, index=True)
    entity_type = Column(String(128), nullable=False)
    workflow_id = Column(String(36), nullable=True)
    state_id = Column(String(36), nullable=True)
    state_name = Column(String(128), nullable=True)
    text = Column(Text, nullable=False)
    mentions = Column(JSONB, nullable=False, default=list)
    edit_history = Column(JSONB, nullable=False, default=list)
    author_id = Column(String(36), nullable=True)
    author_name = Column(String(256), nullable=False)
    author_role = Column(String(64), nullable=True)
    author_avatar_url = Column(String(2048), nullable=True)
    parent_id = Column(String(36), nullable=True)
    likes = Column(JSONB, nullable=False, default=list)
    visibility = Column(String(32), nullable=False, default="all")
    visible_to_roles = Column(JSONB, nullable=True)
    is_edited = Column(Boolean, nullable=False, default=False)
    edited_at = Column(DateTime(timezone=True), nullable=True)
    archived_at = Column(DateTime(timezone=True), nullable=True)
    archived_by = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_comments_entity_org", "entity_id", "organization_id"),
        Index("ix_comments_entity_workflow_state", "entity_id", "workflow_id", "state_id"),
        Index("ix_comments_active", "entity_id", "archived_at"),
        Index("ix_comments_author", "author_id"),
        Index("ix_comments_created", "created_at"),
        Index("ix_comments_parent_id", "parent_id"),
        {"schema": _runtime_schema()},
    )


@dataclass(frozen=True)
class CommentContext:
    """Resolved entity / author / workflow context required to persist a comment."""

    entity_type: str
    entity_label: str
    assignee_id: str | None
    author_name: str
    author_role: str | None
    author_avatar_url: str | None
    state_id: str | None
    state_name: str | None
    workflow_id: str | None


# ── CommentModelService ───────────────────────────────────────────────────────


class CommentModelService:
    """DB operations for comments.

    Receives a per-request Session — no session management of its own.
    """

    module_name = "comments"

    def __init__(self, database_service_manager: Any = None) -> None:
        self.module_name = "comments"
        self.database_service_manager = database_service_manager

    @contextmanager
    def session_scope(self) -> Iterator[Session]:
        """Yield a session for callers that own none, committing on success.

        Controllers pass their request session to every other method here. Agents
        and workers have no request, so the persistence layer opens one for them
        rather than pushing DB handling up into a calling module. Commit and
        rollback live here too, so a caller never writes half a change.
        """
        if self.database_service_manager is None:
            logger.error("comments session_scope: database manager dependency is not configured")
            raise ServiceError("database manager dependency is not configured")
        session = self.database_service_manager.postgres_db_service().get_db_session()
        try:
            yield session
            session.commit()
        except Exception:
            logger.exception("comments session_scope: rolling back after failure")
            session.rollback()
            raise
        finally:
            session.close()

    # ── Context resolution ────────────────────────────────────────────────────

    @staticmethod
    def resolve_actor_display(db: Session, actor_id: str) -> tuple[str, str | None]:
        """Resolve just a user's display name/avatar (one query) — lighter
        than resolve_context for callers that don't need entity/entity_type
        context at all, e.g. toggling a like."""
        user = db.query(User).filter(User.id == actor_id).first()
        name = str(user.full_name) if user else actor_id
        avatar_url = (
            str(user.avatar_url) if user and getattr(user, "avatar_url", None) else None
        )
        return name, avatar_url

    @staticmethod
    def entity_type_name_by_id(
        db: Session, *, organization_id: str, entity_type_id: str | None
    ) -> str | None:
        """Name for an entity type id. Comment rows store the id, while readers
        that resolve a record's workflow need the name."""
        if not entity_type_id:
            return None
        row = (
            db.query(EntityTypeModel)
            .filter(
                EntityTypeModel.entity_type_id == entity_type_id,
                EntityTypeModel.organization_id == organization_id,
            )
            .first()
        )
        return str(row.name) if row else None

    @staticmethod
    def resolve_context(
        db: Session,
        *,
        organization_id: str,
        entity_id: str,
        actor_id: str,
        workflow_id: str | None = None,
        state_id: str | None = None,
    ) -> CommentContext:
        """Resolve entity, author, and (optional) workflow state details via ORM."""
        try:
            entity = (
                db.query(EntityRecordModel)
                .filter(
                    EntityRecordModel.entity_id == entity_id,
                    EntityRecordModel.organization_id == organization_id,
                )
                .first()
            )
            if not entity:
                raise PersistenceError(f"Entity {entity_id} not found")
            entity_type = str(entity.entity_type_id)
            entity_type_row = (
                db.query(EntityTypeModel)
                .filter(
                    EntityTypeModel.entity_type_id == entity.entity_type_id,
                    EntityTypeModel.organization_id == organization_id,
                )
                .first()
            )
            entity_type_name = str(entity_type_row.name) if entity_type_row else entity_type
            entity_label = str((entity.data or {}).get(IDENTIFIER_FIELD_KEY) or entity_type_name)
            assignee_id = str(entity.assignee_id) if entity.assignee_id else None

            user = db.query(User).filter(User.id == actor_id).first()
            author_name = str(user.full_name) if user else actor_id
            author_role = str(user.role) if user and getattr(user, "role", None) else None
            author_avatar_url = (
                str(user.avatar_url) if user and getattr(user, "avatar_url", None) else None
            )

            resolved_state_id: str | None = None
            state_name: str | None = None
            resolved_workflow_id: str | None = workflow_id
            if workflow_id:
                # Single query: find enrollment under any version of the same
                # workflow family using a subquery — avoids multiple round-trips.
                machine_name_subquery = (
                    db.query(WorkflowStateMachineModel.machine_name)
                    .filter(WorkflowStateMachineModel.id == workflow_id)
                    .scalar_subquery()
                )
                version_ids_subquery = (
                    db.query(WorkflowStateMachineModel.id)
                    .filter(
                        WorkflowStateMachineModel.machine_name == machine_name_subquery,
                        WorkflowStateMachineModel.organization_id == organization_id,
                    )
                    .scalar_subquery()
                )
                enrollment = (
                    db.query(EntityStateRuntimeModel)
                    .filter(
                        EntityStateRuntimeModel.entity_id == entity_id,
                        EntityStateRuntimeModel.workflow_id.in_(version_ids_subquery),
                        EntityStateRuntimeModel.organization_id == organization_id,
                    )
                    .first()
                )
                if not enrollment:
                    raise ValidationError(
                        f"Entity {entity_id} not enrolled in workflow {workflow_id}"
                    )
                if state_id and state_id != enrollment.state_id:
                    raise ValidationError("state_id does not match workflow enrollment")
                resolved_state_id = str(enrollment.state_id)
                state_name = str(enrollment.current_state)
                resolved_workflow_id = str(enrollment.workflow_id)
            elif state_id:
                raise ValidationError("state_id requires workflow_id")

            return CommentContext(
                entity_type=entity_type,
                entity_label=entity_label,
                assignee_id=assignee_id,
                author_name=author_name,
                author_role=author_role,
                author_avatar_url=author_avatar_url,
                state_id=resolved_state_id,
                state_name=state_name,
                workflow_id=resolved_workflow_id,
            )
        except (PersistenceError, ValidationError):
            raise
        except Exception as exc:
            logger.error("Unable to resolve comment context: %s", exc)
            raise PersistenceError(f"Unable to resolve comment context: {exc}") from exc

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def create(
        self,
        db: Session,
        *,
        organization_id: str,
        entity_id: str,
        entity_type: str,
        text: str,
        author_id: str | None,
        author_name: str,
        author_role: str | None = None,
        author_avatar_url: str | None = None,
        mentions: list[dict] | None = None,
        workflow_id: str | None = None,
        state_id: str | None = None,
        state_name: str | None = None,
        visibility: str = "all",
        visible_to_roles: list[str] | None = None,
        parent_id: str | None = None,
    ) -> Comment:
        try:
            record = Comment(
                organization_id=organization_id,
                entity_id=entity_id,
                entity_type=entity_type,
                text=text,
                author_id=author_id,
                author_name=author_name,
                author_role=author_role,
                author_avatar_url=author_avatar_url,
                mentions=mentions or [],
                workflow_id=workflow_id,
                state_id=state_id,
                state_name=state_name,
                visibility=visibility,
                visible_to_roles=visible_to_roles,
                parent_id=parent_id,
            )
            db.add(record)
            db.commit()
            db.refresh(record)
            return record
        except Exception as exc:
            logger.error("Unable to create comment: %s", exc)
            db.rollback()
            raise PersistenceError(f"Unable to create comment: {exc}") from exc

    def get(self, db: Session, comment_id: str, organization_id: str) -> Comment | None:
        try:
            return (
                db.query(Comment)
                .filter(Comment.id == comment_id, Comment.organization_id == organization_id)
                .first()
            )
        except Exception as exc:
            logger.error("Unable to get comment: %s", exc)
            raise PersistenceError(f"Unable to get comment: {exc}") from exc

    def list_for_entity(
        self,
        db: Session,
        entity_id: str,
        organization_id: str,
        *,
        state_id: str | None = None,
        state_name: str | None = None,
        include_archived: bool = False,
        top_level_only: bool = False,
    ) -> list[Comment]:
        """List an entity's comments.

        ``top_level_only`` excludes replies entirely — used for the main
        comments list, which only needs `reply_count` per comment (computed
        separately via `count_replies_by_parent`) rather than every reply's
        full text/mentions/likes. Keeps the initial payload light; replies
        are fetched on demand via `list_replies` when the user expands them.
        """
        try:
            query = db.query(Comment).filter(
                Comment.entity_id == entity_id,
                Comment.organization_id == organization_id,
            )
            if state_id is not None:
                query = query.filter(Comment.state_id == state_id)
            if state_name is not None:
                query = query.filter(Comment.state_name == state_name)
            if not include_archived:
                query = query.filter(Comment.archived_at.is_(None))
            if top_level_only:
                query = query.filter(Comment.parent_id.is_(None))
            return query.order_by(Comment.created_at.asc()).all()
        except Exception as exc:
            logger.error("Unable to list comments: %s", exc)
            raise PersistenceError(f"Unable to list comments: {exc}") from exc

    def list_replies(
        self,
        db: Session,
        parent_id: str,
        organization_id: str,
        *,
        include_archived: bool = False,
    ) -> list[Comment]:
        """List the replies to one top-level comment, oldest first."""
        try:
            query = db.query(Comment).filter(
                Comment.parent_id == parent_id,
                Comment.organization_id == organization_id,
            )
            if not include_archived:
                query = query.filter(Comment.archived_at.is_(None))
            return query.order_by(Comment.created_at.asc()).all()
        except Exception as exc:
            logger.error("Unable to list replies: %s", exc)
            raise PersistenceError(f"Unable to list replies: {exc}") from exc

    def count_replies_by_parent(
        self,
        db: Session,
        entity_id: str,
        organization_id: str,
        *,
        actor_roles: set[str] | None = None,
    ) -> dict[str, int]:
        """Non-archived reply counts, keyed by parent_id, for one entity's comments.

        Only fetches (parent_id, visibility, visible_to_roles) — not full
        reply bodies — and applies the same role-restricted visibility check
        as `list_for_entity`'s filtering, so a role-restricted reply the
        actor can't see never inflates a visible count (would otherwise leak
        that hidden content exists).
        """
        try:
            rows = (
                db.query(Comment.parent_id, Comment.visibility, Comment.visible_to_roles)
                .filter(
                    Comment.entity_id == entity_id,
                    Comment.organization_id == organization_id,
                    Comment.parent_id.isnot(None),
                    Comment.archived_at.is_(None),
                )
                .all()
            )
            roles = actor_roles or set()
            counts: dict[str, int] = {}
            for parent_id, visibility, visible_to_roles in rows:
                if visibility == "role_restricted" and not roles.intersection(
                    visible_to_roles or []
                ):
                    continue
                counts[parent_id] = counts.get(parent_id, 0) + 1
            return counts
        except Exception as exc:
            logger.error("Unable to count replies: %s", exc)
            raise PersistenceError(f"Unable to count replies: {exc}") from exc

    def count_replies_for_parent(
        self,
        db: Session,
        parent_id: str,
        organization_id: str,
        *,
        actor_roles: set[str] | None = None,
    ) -> int:
        """Same visibility-aware reply count as `count_replies_by_parent`, but
        scoped to ONE parent — for single-comment callers (toggle_like,
        update_comment) that don't need every reply in the whole entity."""
        try:
            rows = (
                db.query(Comment.visibility, Comment.visible_to_roles)
                .filter(
                    Comment.parent_id == parent_id,
                    Comment.organization_id == organization_id,
                    Comment.archived_at.is_(None),
                )
                .all()
            )
            roles = actor_roles or set()
            count = 0
            for visibility, visible_to_roles in rows:
                if visibility == "role_restricted" and not roles.intersection(
                    visible_to_roles or []
                ):
                    continue
                count += 1
            return count
        except Exception as exc:
            logger.error("Unable to count replies for parent: %s", exc)
            raise PersistenceError(f"Unable to count replies for parent: {exc}") from exc

    def update_text(
        self,
        db: Session,
        comment_id: str,
        organization_id: str,
        new_text: str,
        actor_id: str,
        actor_name: str,
        mentions: list[dict] | None = None,
    ) -> Comment:
        try:
            comment = (
                db.query(Comment)
                .filter(Comment.id == comment_id, Comment.organization_id == organization_id)
                .with_for_update()
                .first()
            )
            if not comment:
                logger.error("update_text: comment %s not found", comment_id)
                raise PersistenceError(f"Comment {comment_id} not found")
            history_entry = {
                "previous_text": comment.text,
                "edited_at": datetime.now(UTC).isoformat(),
                "edited_by_id": actor_id,
                "edited_by_name": actor_name,
            }
            comment.edit_history = list(comment.edit_history or []) + [history_entry]
            comment.text = new_text
            if mentions is not None:
                comment.mentions = mentions
            comment.is_edited = True
            comment.edited_at = datetime.now(UTC)
            db.commit()
            db.refresh(comment)
            return comment
        except PersistenceError:
            db.rollback()
            raise
        except Exception as exc:
            logger.error("Unable to update comment: %s", exc)
            db.rollback()
            raise PersistenceError(f"Unable to update comment: {exc}") from exc

    def toggle_like(
        self,
        db: Session,
        comment_id: str,
        organization_id: str,
        *,
        user_id: str,
        user_name: str,
        user_avatar_url: str | None,
    ) -> tuple[Comment, bool]:
        """Add or remove ``user_id``'s like on a comment.

        Returns the updated comment and ``True`` if this call added a like
        (not-liked → liked), ``False`` if it removed one.
        """
        try:
            comment = (
                db.query(Comment)
                .filter(Comment.id == comment_id, Comment.organization_id == organization_id)
                .with_for_update()
                .first()
            )
            if not comment:
                logger.error("toggle_like: comment %s not found", comment_id)
                raise PersistenceError(f"Comment {comment_id} not found")

            existing = list(comment.likes or [])
            already_liked = any(like.get("user_id") == user_id for like in existing)
            if already_liked:
                comment.likes = [like for like in existing if like.get("user_id") != user_id]
                added = False
            else:
                comment.likes = [
                    *existing,
                    {
                        "user_id": user_id,
                        "user_name": user_name,
                        "user_avatar_url": user_avatar_url,
                        "liked_at": datetime.now(UTC).isoformat(),
                    },
                ]
                added = True

            db.commit()
            db.refresh(comment)
            return comment, added
        except PersistenceError:
            db.rollback()
            raise
        except Exception as exc:
            logger.error("Unable to toggle like on comment: %s", exc)
            db.rollback()
            raise PersistenceError(f"Unable to toggle like on comment: {exc}") from exc

    # ── Mention notifications ─────────────────────────────────────────────────

    @staticmethod
    def clear_mention_notifications(
        db: Session,
        comment_id: str,
        organization_id: str,
    ) -> None:
        """Delete all mention notifications for a comment."""
        try:
            db.query(Notification).filter(
                Notification.source_type == "comment",
                Notification.source_id == comment_id,
                Notification.organization_id == organization_id,
            ).delete(synchronize_session=False)
            db.commit()
        except Exception as exc:
            logger.error("Unable to clear mention notifications: %s", exc)
            db.rollback()
            raise PersistenceError(f"Unable to clear mention notifications: {exc}") from exc

    def archive(
        self,
        db: Session,
        comment_id: str,
        organization_id: str,
        archived_by: str,
    ) -> Comment:
        try:
            comment = (
                db.query(Comment)
                .filter(Comment.id == comment_id, Comment.organization_id == organization_id)
                .with_for_update()
                .first()
            )
            if not comment:
                logger.error("archive: comment %s not found", comment_id)
                raise PersistenceError(f"Comment {comment_id} not found")
            comment.archived_at = datetime.now(UTC)
            comment.archived_by = archived_by
            db.commit()
            db.refresh(comment)
            return comment
        except PersistenceError:
            db.rollback()
            raise
        except Exception as exc:
            logger.error("Unable to archive comment: %s", exc)
            db.rollback()
            raise PersistenceError(f"Unable to archive comment: {exc}") from exc
