"""Business logic manager for comments."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from common.auth import actor_str
from common.enums import AuditMetadataType, ModuleStatus
from common.logger import logger
from comments.models.interface import MENTION_PATTERN, build_comment_link
from comments.models.request import CommentCreateRequest, CommentReplyRequest, CommentUpdateRequest
from comments.models.response import CommentListResponse, CommentResponse
from exceptions import AuthorizationError, NotFoundError, ServiceError, ValidationError

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from auth.models.response import AccessCheckResponse
    from comments.db_models import Comment, CommentModelService
    from common.protocols import BackgroundTaskScheduler
    from database.manager import DatabaseServiceManager


def parse_mentions(text: str) -> list[tuple[str, str, int]]:
    """Return [(full_name, user_id, position), ...] from @[Name](id) syntax."""
    return [(m.group(1), m.group(2), m.start()) for m in MENTION_PATTERN.finditer(text)]


class AuthAccessService(Protocol):
    def check_access(self, payload: dict[str, object]) -> AccessCheckResponse:
        """Return an authorization decision for the given payload."""
        ...


class MentionNotificationService(Protocol):
    def create_mention_notification(
        self,
        *,
        db: object | None = None,
        organization_id: str,
        recipient_id: str,
        entity_id: str,
        entity_type: str,
        entity_label: str = "",
        comment_id: str,
        comment_text: str,
        actor_id: str,
        actor_name: str = "",
        link: str | None = None,
        background_tasks: BackgroundTaskScheduler | None = None,
    ) -> object:
        """Create a notification for a mentioned user."""
        ...

    def create_comment_notification(
        self,
        *,
        db: object | None = None,
        organization_id: str,
        recipient_id: str,
        entity_id: str,
        entity_type: str,
        entity_label: str,
        comment_id: str,
        comment_text: str,
        actor_id: str,
        actor_name: str = "",
        link: str | None = None,
        background_tasks: BackgroundTaskScheduler | None = None,
    ) -> object:
        """Create a notification for the entity's assignee when a comment is made."""
        ...

    def create_reply_notification(
        self,
        *,
        db: object | None = None,
        organization_id: str,
        recipient_id: str,
        entity_id: str,
        entity_type: str,
        comment_id: str,
        parent_comment_text: str,
        reply_text: str,
        actor_id: str,
        actor_name: str = "",
        link: str | None = None,
        background_tasks: BackgroundTaskScheduler | None = None,
    ) -> object:
        """Create a notification for a top-level comment's author when someone replies to it."""
        ...

    def create_like_notification(
        self,
        *,
        db: object | None = None,
        organization_id: str,
        recipient_id: str,
        entity_id: str,
        entity_type: str,
        comment_id: str,
        comment_text: str,
        actor_id: str,
        actor_name: str = "",
        link: str | None = None,
        background_tasks: BackgroundTaskScheduler | None = None,
    ) -> object:
        """Create a notification for a comment's author when someone likes it."""
        ...


class CommentsServiceManager:
    """Comments orchestration service.

    Stateless — each method receives the per-request DB session as a parameter.
    Sessions are owned and closed by the controller.
    """

    def __init__(
        self,
        comment_model_service: CommentModelService,
        database_service_manager: DatabaseServiceManager | None,
        config: object | None,
        auth_service_manager: AuthAccessService | None = None,
        notifications_manager: MentionNotificationService | None = None,
        audit_events_service: object | None = None,
    ) -> None:
        self.db = comment_model_service
        self.database_service_manager = database_service_manager
        self.config = config
        self.module_name = "comments"
        self._started = False
        self.auth_service_manager = auth_service_manager
        self.notifications_manager = notifications_manager
        self.audit_events_service = audit_events_service

    def start(self) -> None:
        """Mark the comments module as started."""
        self._started = True

    def stop(self) -> None:
        """Mark the comments module as stopped."""
        self._started = False

    def get_status(self) -> dict[str, object]:
        """Return the current operational status of the comments module."""
        return {
            "module": self.module_name,
            "status": ModuleStatus.READY.value,
            "started": self._started,
        }

    def _require_comment_service(self) -> CommentModelService:
        """Return the comment model service, raising ServiceError if not configured."""
        if self.db is None:
            raise ServiceError("comment_model_service not configured")
        return self.db

    @staticmethod
    def _build_reply_aware_link(
        workflow_id: str | None, entity_id: str, comment_id: str, parent_id: str | None = None
    ) -> str | None:
        """Frontend link for a comment notification, aware that replies are
        lazy-loaded: if this event is about a reply (`parent_id` set), link
        at the parent's id instead, with `reply_id` set — a link straight to
        a reply's own id has nothing to scroll to until its parent's replies
        are expanded."""
        if not workflow_id:
            return None
        return build_comment_link(
            workflow_id, entity_id, parent_id or comment_id,
            reply_id=comment_id if parent_id else None,
        )

    def _replace_mention_notifications(
        self,
        db: Session,
        svc: CommentModelService,
        *,
        organization_id: str,
        entity_id: str,
        entity_type: str,
        entity_label: str,
        comment_id: str,
        comment_text: str,
        actor_id: str,
        actor_name: str,
        mentions: list[dict],
        workflow_id: str | None = None,
        parent_id: str | None = None,
        background_tasks: BackgroundTaskScheduler | None = None,
    ) -> None:
        if self.notifications_manager is None:
            return

        link = self._build_reply_aware_link(workflow_id, entity_id, comment_id, parent_id)

        try:
            svc.clear_mention_notifications(db, comment_id, organization_id)

            for mention in mentions:
                try:
                    self.notifications_manager.create_mention_notification(
                        db=db,
                        organization_id=organization_id,
                        recipient_id=mention["user_id"],
                        entity_id=entity_id,
                        entity_type=entity_type,
                        entity_label=entity_label,
                        comment_id=comment_id,
                        comment_text=comment_text,
                        actor_id=actor_id,
                        actor_name=actor_name,
                        link=link,
                        background_tasks=background_tasks,
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to create mention notification for %s: %s",
                        mention.get("user_id"),
                        exc,
                    )
        except Exception as exc:
            logger.warning("Failed to replace mention notifications: %s", exc)

    def _notify_reply_to_comment_author(
        self,
        db: Session,
        *,
        organization_id: str,
        entity_id: str,
        entity_type: str,
        parent_comment: Comment,
        comment_id: str,
        reply_text: str,
        actor_id: str,
        actor_name: str,
        already_notified_user_ids: set[str],
        workflow_id: str | None = None,
        background_tasks: BackgroundTaskScheduler | None = None,
    ) -> None:
        """Notify (and, if enabled, email) a top-level comment's author that
        someone replied to it — skipped when they wrote the reply themselves,
        or were already notified for this event via a higher-precedence
        reason (e.g. they were @mentioned in the same reply)."""
        recipient_id = parent_comment.author_id
        if self.notifications_manager is None or not recipient_id:
            return
        if recipient_id == actor_id or recipient_id in already_notified_user_ids:
            return

        link = self._build_reply_aware_link(workflow_id, entity_id, comment_id, parent_comment.id)

        try:
            self.notifications_manager.create_reply_notification(
                db=db,
                organization_id=organization_id,
                recipient_id=recipient_id,
                entity_id=entity_id,
                entity_type=entity_type,
                comment_id=comment_id,
                parent_comment_text=parent_comment.text,
                reply_text=reply_text,
                actor_id=actor_id,
                actor_name=actor_name,
                link=link,
                background_tasks=background_tasks,
            )
        except Exception as exc:
            logger.warning(
                "Failed to create reply notification for %s: %s", recipient_id, exc
            )

    def _notify_like_of_comment(
        self,
        db: Session,
        *,
        organization_id: str,
        entity_id: str,
        entity_type: str,
        comment_id: str,
        comment_text: str,
        comment_author_id: str | None,
        actor_id: str,
        actor_name: str,
        parent_id: str | None = None,
        workflow_id: str | None = None,
        background_tasks: BackgroundTaskScheduler | None = None,
    ) -> None:
        """Notify (and, if enabled, email) a comment's author that it was
        liked — skipped when liking your own comment. Fires on every
        not-liked -> liked transition; unlike never notifies, and a re-like
        after an unlike fires again (no cross-time dedup)."""
        if self.notifications_manager is None or not comment_author_id:
            return
        if comment_author_id == actor_id:
            return

        link = self._build_reply_aware_link(workflow_id, entity_id, comment_id, parent_id)

        try:
            self.notifications_manager.create_like_notification(
                db=db,
                organization_id=organization_id,
                recipient_id=comment_author_id,
                entity_id=entity_id,
                entity_type=entity_type,
                comment_id=comment_id,
                comment_text=comment_text,
                actor_id=actor_id,
                actor_name=actor_name,
                link=link,
                background_tasks=background_tasks,
            )
        except Exception as exc:
            logger.warning(
                "Failed to create like notification for %s: %s", comment_author_id, exc
            )

    def _notify_assignee_of_comment(
        self,
        db: Session,
        *,
        organization_id: str,
        entity_id: str,
        entity_type: str,
        entity_label: str,
        assignee_id: str | None,
        comment_id: str,
        comment_text: str,
        actor_id: str,
        actor_name: str,
        already_notified_user_ids: set[str],
        workflow_id: str | None = None,
        parent_id: str | None = None,
        background_tasks: BackgroundTaskScheduler | None = None,
    ) -> None:
        """Notify (and, if enabled, email) the entity's assignee that a comment
        was made — skipped when the assignee wrote the comment or was already
        notified for this event via a higher-precedence reason (mentioned, or
        is the parent comment's author on a reply)."""
        if self.notifications_manager is None or not assignee_id:
            return
        if assignee_id == actor_id or assignee_id in already_notified_user_ids:
            return

        link = self._build_reply_aware_link(workflow_id, entity_id, comment_id, parent_id)

        try:
            self.notifications_manager.create_comment_notification(
                db=db,
                organization_id=organization_id,
                recipient_id=assignee_id,
                entity_id=entity_id,
                entity_type=entity_type,
                entity_label=entity_label,
                comment_id=comment_id,
                comment_text=comment_text,
                actor_id=actor_id,
                actor_name=actor_name,
                link=link,
                background_tasks=background_tasks,
            )
        except Exception as exc:
            logger.warning(
                "Failed to create comment notification for assignee %s: %s",
                assignee_id,
                exc,
            )

    def create_comment(
        self,
        db: Session,
        actor: dict[str, object],
        entity_id: str,
        request: CommentCreateRequest,
        *,
        _prefetched_parent: Comment | None = None,
        background_tasks: BackgroundTaskScheduler | None = None,
    ) -> CommentResponse:
        """Create a new comment on an entity, resolving author and workflow-state context.

        Validates that the actor belongs to the correct organization and has write
        access. For role-restricted comments, ``visible_to_roles`` must be provided.

        ``_prefetched_parent`` is an internal optimization: reply_to_comment
        already fetches the parent to build the wrapped request, so it passes
        the row through here instead of making this method fetch it again.
        Not part of the public API — omit it for any other caller.

        ``background_tasks``, when given, defers every notification email
        this comment triggers (mention/reply/assignee) to run after the HTTP
        response instead of blocking it — see `notifications/manager.py`'s
        `_dispatch_send_email`.
        """
        try:
            svc = self._require_comment_service()
            author_id = self._require_actor_field(actor, "user_id")
            organization_id = self._require_actor_field(actor, "organization_id")
            self._authorize_actor_operation(actor, "comment", "write", organization_id)

            # TODO: visible_to_roles is currently a free-text list — replace with dynamic roles fetched from the roles service
            if request.visibility == "role_restricted" and not request.visible_to_roles:
                raise ValidationError(
                    "visible_to_roles must be a non-empty list of role names when visibility is 'role_restricted' "
                    "(e.g. [\"admin\", \"recruiter\"])"
                )

            parent_comment: Comment | None = None
            if request.parent_id:
                parent_comment = _prefetched_parent or svc.get(
                    db, request.parent_id, organization_id
                )
                if not parent_comment or parent_comment.entity_id != entity_id:
                    raise NotFoundError(f"Parent comment {request.parent_id} not found")
                if parent_comment.archived_at is not None:
                    raise ValidationError("Cannot reply to an archived comment")
                if parent_comment.parent_id is not None:
                    raise ValidationError(
                        "Cannot reply to a reply — only top-level comments can be replied to"
                    )
                # A reply must inherit the parent's visibility exactly — the
                # reply_to_comment wrapper already does this, but parent_id
                # is also settable on the generic create-comment endpoint, so
                # enforce it here too or a reply could be posted with looser
                # visibility than a role-restricted parent, leaking it.
                if (
                    request.visibility != parent_comment.visibility
                    or set(request.visible_to_roles or [])
                    != set(parent_comment.visible_to_roles or [])
                ):
                    raise ValidationError(
                        "A reply's visibility must match its parent comment's visibility"
                    )

            # A reply inherits its parent's workflow_id/state_id/state_name as
            # a snapshot, same as the parent's own values were snapshotted at
            # its creation — it must NOT re-validate current enrollment (the
            # entity may have since moved to a different workflow). Only skip
            # resolve_context's enrollment check for replies; a genuinely new
            # top-level comment with an explicit workflow_id still gets it.
            context = svc.resolve_context(
                db,
                organization_id=organization_id,
                entity_id=entity_id,
                actor_id=author_id,
                workflow_id=None if parent_comment else request.workflow_id,
            )

            # For a reply, workflow_id/state_id/state_name are inherited
            # straight from the parent's own snapshot (resolve_context skipped
            # re-resolving them above) rather than context's, which is None here.
            effective_workflow_id = parent_comment.workflow_id if parent_comment else context.workflow_id
            effective_state_id = parent_comment.state_id if parent_comment else context.state_id
            effective_state_name = parent_comment.state_name if parent_comment else context.state_name

            raw_mentions = parse_mentions(request.text)
            valid_mentions = [
                {"user_id": uid, "full_name": full_name, "position": position}
                for full_name, uid, position in raw_mentions
                if uid != author_id
            ]

            comment = svc.create(
                db,
                organization_id=organization_id,
                entity_id=entity_id,
                entity_type=context.entity_type,
                text=request.text,
                author_id=author_id,
                author_name=context.author_name,
                author_role=context.author_role,
                author_avatar_url=context.author_avatar_url,
                mentions=valid_mentions,
                workflow_id=effective_workflow_id,
                state_id=effective_state_id,
                state_name=effective_state_name,
                visibility=request.visibility,
                visible_to_roles=request.visible_to_roles,
                parent_id=request.parent_id,
            )

            self._replace_mention_notifications(
                db,
                svc,
                organization_id=organization_id,
                entity_id=entity_id,
                entity_type=context.entity_type,
                entity_label=context.entity_label,
                comment_id=comment.id,
                comment_text=request.text,
                actor_id=author_id,
                actor_name=context.author_name,
                mentions=valid_mentions,
                workflow_id=effective_workflow_id,
                parent_id=parent_comment.id if parent_comment else None,
                background_tasks=background_tasks,
            )

            # Notification dedup: at most one email per recipient for this
            # comment-creation event, precedence mention > reply > assignee.
            # Each stage adds its recipients before the next stage runs, so
            # someone hit by more than one reason still gets exactly one.
            notified_user_ids = {m["user_id"] for m in valid_mentions}

            if parent_comment is not None:
                self._notify_reply_to_comment_author(
                    db,
                    organization_id=organization_id,
                    entity_id=entity_id,
                    entity_type=context.entity_type,
                    parent_comment=parent_comment,
                    comment_id=comment.id,
                    reply_text=request.text,
                    actor_id=author_id,
                    actor_name=context.author_name,
                    already_notified_user_ids=notified_user_ids,
                    workflow_id=effective_workflow_id,
                    background_tasks=background_tasks,
                )
                if parent_comment.author_id:
                    notified_user_ids.add(parent_comment.author_id)

            self._notify_assignee_of_comment(
                db,
                organization_id=organization_id,
                entity_id=entity_id,
                entity_type=context.entity_type,
                entity_label=context.entity_label,
                assignee_id=context.assignee_id,
                comment_id=comment.id,
                comment_text=request.text,
                actor_id=author_id,
                actor_name=context.author_name,
                already_notified_user_ids=notified_user_ids,
                workflow_id=effective_workflow_id,
                parent_id=parent_comment.id if parent_comment else None,
                background_tasks=background_tasks,
            )

            self._emit_comment_event(
                "REPLY_CREATED" if parent_comment is not None else "COMMENT_CREATED",
                organization_id=organization_id,
                entity_id=entity_id,
                actor_id=author_id,
                comment=comment,
                db=db,
            )
            return CommentResponse.from_orm(comment, current_user_id=author_id)
        except (ValidationError, AuthorizationError, NotFoundError) as exc:
            logger.error("create_comment rejected: %s", exc)
            raise
        except Exception as exc:
            logger.exception("create_comment failed", extra={"exc_type": type(exc).__name__})
            raise ServiceError("Unable to create comment") from exc

    def reply_to_comment(
        self,
        db: Session,
        actor: dict[str, object],
        parent_comment_id: str,
        request: CommentReplyRequest,
        *,
        background_tasks: BackgroundTaskScheduler | None = None,
    ) -> CommentResponse:
        """Create a single-level reply to a top-level comment.

        Thin wrapper around create_comment: resolves the entity id and
        inherits visibility/workflow scoping from the parent so callers only
        need to send the reply text.
        """
        svc = self._require_comment_service()
        organization_id = self._require_actor_field(actor, "organization_id")
        actor_roles = set(actor.get("roles") or [])
        parent = svc.get(db, parent_comment_id, organization_id)
        if not parent:
            raise NotFoundError(f"Comment {parent_comment_id} not found")
        if not self._is_visible_to(parent, actor_roles):
            # Same as toggle_like/list_replies: a role-restricted parent the
            # actor's roles don't grant access to reads as not-found, not
            # forbidden — don't confirm it exists, and don't let them write
            # into a thread they can't even see.
            raise NotFoundError(f"Comment {parent_comment_id} not found")

        wrapped = CommentCreateRequest(
            text=request.text,
            visibility=parent.visibility,
            visible_to_roles=list(parent.visible_to_roles) if parent.visible_to_roles else None,
            workflow_id=parent.workflow_id,
            parent_id=parent_comment_id,
        )
        return self.create_comment(
            db,
            actor,
            parent.entity_id,
            wrapped,
            _prefetched_parent=parent,
            background_tasks=background_tasks,
        )

    def toggle_like(
        self,
        db: Session,
        actor: dict[str, object],
        comment_id: str,
        *,
        background_tasks: BackgroundTaskScheduler | None = None,
    ) -> CommentResponse:
        """Toggle the current actor's like on a comment.

        Notifies (and, if the org has enabled it, emails) the comment's
        author only on the not-liked -> liked transition — never on unlike,
        never when liking your own comment.
        """
        try:
            svc = self._require_comment_service()
            actor_id = self._require_actor_field(actor, "user_id")
            organization_id = self._require_actor_field(actor, "organization_id")
            self._authorize_actor_operation(actor, "comment", "write", organization_id)

            actor_roles = set(actor.get("roles") or [])
            comment = svc.get(db, comment_id, organization_id)
            if not comment:
                raise NotFoundError(f"Comment {comment_id} not found")
            if comment.archived_at is not None:
                raise ValidationError("Cannot like an archived comment")
            if not self._is_visible_to(comment, actor_roles):
                # Same as list_comments/list_replies: a role-restricted
                # comment the actor's roles don't grant access to reads as
                # not-found, not forbidden — don't confirm it exists.
                raise NotFoundError(f"Comment {comment_id} not found")

            # Only the actor's own display name/avatar are needed here — the
            # full resolve_context also looks up the entity + entity_type,
            # which toggling a like never uses.
            author_name, author_avatar_url = svc.resolve_actor_display(db, actor_id)

            updated, added = svc.toggle_like(
                db,
                comment_id,
                organization_id,
                user_id=actor_id,
                user_name=author_name,
                user_avatar_url=author_avatar_url,
            )

            if added:
                self._notify_like_of_comment(
                    db,
                    organization_id=organization_id,
                    entity_id=comment.entity_id,
                    entity_type=comment.entity_type,
                    comment_id=comment_id,
                    comment_text=comment.text,
                    comment_author_id=comment.author_id,
                    actor_id=actor_id,
                    actor_name=author_name,
                    parent_id=comment.parent_id,
                    workflow_id=comment.workflow_id,
                    background_tasks=background_tasks,
                )

            # Unlike notifications, this fires on both transitions (like AND
            # unlike) an unlike is a real, auditable event even though it
            # doesn't notify anyone.
            self._emit_comment_event(
                "COMMENT_LIKED" if added else "COMMENT_UNLIKED",
                organization_id=organization_id,
                entity_id=comment.entity_id,
                actor_id=actor_id,
                comment=updated,
                db=db,
            )

            # A reply's reply_count is always 0 (single-level threading) —
            # skip the query entirely rather than asking a question we
            # already know the answer to.
            reply_count = (
                0
                if comment.parent_id
                else svc.count_replies_for_parent(db, comment_id, organization_id, actor_roles=actor_roles)
            )
            return CommentResponse.from_orm(
                updated,
                reply_count=reply_count,
                current_user_id=actor_id,
            )
        except (ValidationError, AuthorizationError, NotFoundError) as exc:
            logger.error("toggle_like rejected: %s", exc)
            raise
        except Exception as exc:
            logger.exception("toggle_like failed", extra={"exc_type": type(exc).__name__})
            raise ServiceError("Unable to toggle like") from exc

    def list_comments_for_agent(
        self, actor: dict[str, object], entity_id: str, *, state_name: str | None = None
    ) -> CommentListResponse:
        """Session-owning wrapper around list_comments for non-HTTP callers."""
        with self.db.session_scope() as db:
            return self.list_comments(db, actor, entity_id, state_name=state_name)

    def create_comment_for_agent(
        self, actor: dict[str, object], entity_id: str, request: CommentCreateRequest
    ) -> CommentResponse:
        """Session-owning wrapper around create_comment for non-HTTP callers."""
        with self.db.session_scope() as db:
            return self.create_comment(db, actor, entity_id, request)

    def list_comments(
        self,
        db: Session,
        actor: dict[str, object],
        entity_id: str,
        *,
        state_name: str | None = None,
        include_archived: bool = False,
    ) -> CommentListResponse:
        """Return an entity's top-level comments, filtered by the actor's roles.

        Replies are NOT included here only `reply_count` is, computed from a
        lightweight column-only query (`count_replies_by_parent`), not by
        fetching every reply's full text/mentions/likes.
        """
        try:
            svc = self._require_comment_service()
            # user_id is only needed to compute liked_by_me — soft-optional
            # (not _require_actor_field) so a system/background actor with no
            # user_id (e.g. build_system_actor) can still list comments; they
            # just always see liked_by_me=False.
            actor_id = actor_str(actor, "user_id") or None
            organization_id = self._require_actor_field(actor, "organization_id")
            self._authorize_actor_operation(actor, "comment", "read", organization_id)
            actor_roles = set(actor.get("roles") or [])

            top_level_comments = svc.list_for_entity(
                db,
                entity_id=entity_id,
                organization_id=organization_id,
                state_name=state_name,
                include_archived=include_archived,
                top_level_only=True,
            )

            visible_comments = self._filter_visible(top_level_comments, actor_roles)

            reply_counts = svc.count_replies_by_parent(
                db, entity_id, organization_id, actor_roles=actor_roles
            )

            visible = [
                CommentResponse.from_orm(
                    c,
                    reply_count=reply_counts.get(c.id, 0),
                    current_user_id=actor_id,
                )
                for c in visible_comments
            ]

            return CommentListResponse(comments=visible, total=len(visible))
        except (ValidationError, AuthorizationError) as exc:
            logger.error("list_comments rejected: %s", exc)
            raise
        except Exception as exc:
            logger.exception("list_comments failed", extra={"exc_type": type(exc).__name__})
            raise ServiceError("Unable to list comments") from exc

    def list_replies(
        self,
        db: Session,
        actor: dict[str, object],
        comment_id: str,
        *,
        include_archived: bool = False,
    ) -> CommentListResponse:
        """Return the replies to one top-level comment, fetched on demand
        (e.g. when a user clicks "View N replies") rather than eagerly with
        the main comment list."""
        try:
            svc = self._require_comment_service()
            organization_id = self._require_actor_field(actor, "organization_id")
            self._authorize_actor_operation(actor, "comment", "read", organization_id)
            # Soft-optional, same reasoning as list_comments: only needed for
            # liked_by_me, shouldn't hard-fail a system/background actor.
            actor_id = actor_str(actor, "user_id") or None
            actor_roles = set(actor.get("roles") or [])

            parent = svc.get(db, comment_id, organization_id)
            if not parent:
                raise NotFoundError(f"Comment {comment_id} not found")
            # An archived or role-restricted-and-hidden parent's replies are
            # just as gone/hidden as the parent itself — return an empty list
            # rather than an error, matching how list_comments silently omits
            # both cases instead of surfacing them as failures.
            if parent.archived_at is not None or not self._is_visible_to(parent, actor_roles):
                return CommentListResponse(comments=[], total=0)

            replies = svc.list_replies(
                db, comment_id, organization_id, include_archived=include_archived
            )
            visible_replies = self._filter_visible(replies, actor_roles)

            responses = [
                CommentResponse.from_orm(c, reply_count=0, current_user_id=actor_id)
                for c in visible_replies
            ]
            return CommentListResponse(comments=responses, total=len(responses))
        except (ValidationError, AuthorizationError, NotFoundError) as exc:
            logger.error("list_replies rejected: %s", exc)
            raise
        except Exception as exc:
            logger.exception("list_replies failed", extra={"exc_type": type(exc).__name__})
            raise ServiceError("Unable to list replies") from exc

    @staticmethod
    def _is_visible_to(comment: Comment, actor_roles: set[str]) -> bool:
        """Whether a role-restricted comment's visible_to_roles grants this actor access."""
        if comment.visibility != "role_restricted":
            return True
        return bool(actor_roles.intersection(comment.visible_to_roles or []))

    @classmethod
    def _filter_visible(cls, comments: list[Comment], actor_roles: set[str]) -> list[Comment]:
        """Drop role-restricted comments the actor's roles don't grant access to."""
        visible = []
        for c in comments:
            if not cls._is_visible_to(c, actor_roles):
                logger.error(
                    "comment %s filtered: actor roles %s not in allowed roles %s",
                    c.id,
                    sorted(actor_roles),
                    sorted(c.visible_to_roles or []),
                )
                continue
            visible.append(c)
        return visible

    def update_comment(
        self,
        db: Session,
        actor: dict[str, object],
        comment_id: str,
        request: CommentUpdateRequest,
        *,
        background_tasks: BackgroundTaskScheduler | None = None,
    ) -> CommentResponse:
        """Edit the text of an existing comment.

        Only the original author may edit same rule as delete, no
        admin/owner/superadmin override, for consistency between the two.
        Archived comments cannot be edited. The previous text is appended to
        ``edit_history`` before the new text is persisted.
        """
        try:
            svc = self._require_comment_service()
            actor_id = self._require_actor_field(actor, "user_id")
            organization_id = self._require_actor_field(actor, "organization_id")
            actor_roles = set(actor.get("roles") or [])

            comment = svc.get(db, comment_id, organization_id)
            if not comment:
                raise NotFoundError(f"Comment {comment_id} not found")
            if comment.archived_at is not None:
                raise ValidationError("Cannot edit an archived comment")

            if comment.author_id != actor_id:
                raise AuthorizationError("Only the comment author can edit this comment")

            if not request.text.strip():
                raise ValidationError("Comment text cannot be empty")

            context = svc.resolve_context(
                db,
                organization_id=organization_id,
                entity_id=comment.entity_id,
                actor_id=actor_id,
                workflow_id=comment.workflow_id,
                state_id=comment.state_id,
            )

            raw_mentions = parse_mentions(request.text)
            valid_mentions = [
                {"user_id": uid, "full_name": full_name, "position": position}
                for full_name, uid, position in raw_mentions
                if uid != actor_id
            ]

            updated = svc.update_text(
                db,
                comment_id,
                organization_id,
                request.text,
                actor_id,
                context.author_name,
                mentions=valid_mentions,
            )

            self._replace_mention_notifications(
                db,
                svc,
                organization_id=organization_id,
                entity_id=comment.entity_id,
                entity_type=context.entity_type,
                entity_label=context.entity_label,
                comment_id=comment_id,
                comment_text=request.text,
                actor_id=actor_id,
                actor_name=context.author_name,
                mentions=valid_mentions,
                workflow_id=comment.workflow_id,
                parent_id=comment.parent_id,
                background_tasks=background_tasks,
            )

            self._emit_comment_event(
                "COMMENT_UPDATED",
                organization_id=organization_id,
                entity_id=comment.entity_id,
                actor_id=actor_id,
                comment=updated,
                db=db,
            )
            # A reply's reply_count is always 0 (single-level threading) —
            # skip the query entirely rather than asking a question we
            # already know the answer to.
            reply_count = (
                0
                if comment.parent_id
                else svc.count_replies_for_parent(db, comment_id, organization_id, actor_roles=actor_roles)
            )
            return CommentResponse.from_orm(
                updated,
                reply_count=reply_count,
                current_user_id=actor_id,
            )
        except (ValidationError, AuthorizationError, NotFoundError) as exc:
            logger.error("update_comment rejected: %s", exc)
            raise
        except Exception as exc:
            logger.exception("update_comment failed", extra={"exc_type": type(exc).__name__})
            raise ServiceError("Unable to update comment") from exc

    def archive_comment(
        self,
        db: Session,
        actor: dict[str, object],
        comment_id: str,
    ) -> None:
        """Soft-delete a comment by setting its ``archived_at`` timestamp.

        Only the comment's original author may archive it. Already-archived
        comments raise ``ValidationError`` to prevent duplicate operations.
        """
        try:
            svc = self._require_comment_service()
            actor_id = self._require_actor_field(actor, "user_id")
            organization_id = self._require_actor_field(actor, "organization_id")

            comment = svc.get(db, comment_id, organization_id)
            if not comment:
                raise NotFoundError(f"Comment {comment_id} not found")
            if comment.archived_at is not None:
                raise ValidationError("Comment already archived")

            if comment.author_id != actor_id:
                raise AuthorizationError("Only the comment author can delete this comment")

            svc.archive(db, comment_id, organization_id, archived_by=actor_id)

            try:
                svc.clear_mention_notifications(db, comment_id, organization_id)
            except Exception as exc:
                logger.warning("Failed to delete mention notifications for comment %s: %s", comment_id, exc)

            self._emit_comment_event(
                "REPLY_ARCHIVED" if comment.parent_id else "COMMENT_ARCHIVED",
                organization_id=organization_id,
                entity_id=comment.entity_id,
                actor_id=actor_id,
                comment=comment,
                db=db,
            )

        except (ValidationError, AuthorizationError, NotFoundError) as exc:
            logger.error("archive_comment rejected: %s", exc)
            raise
        except Exception as exc:
            logger.exception("archive_comment failed", extra={"exc_type": type(exc).__name__})
            raise ServiceError("Unable to archive comment") from exc

    def _authorize_actor_operation(
        self,
        actor: dict[str, object],
        resource: str,
        action: str,
        organization_id: str,
    ) -> None:
        """Assert that the actor is allowed to perform ``action`` on ``resource``.

        Raises ``AuthorizationError`` if the actor's organization differs from
        ``organization_id`` or if the injected auth service denies the request.
        When no auth service is configured the organization scope check is the
        only guard applied.
        """
        actor_organization_id = self._require_actor_field(actor, "organization_id")
        if organization_id != actor_organization_id:
            raise AuthorizationError("Forbidden organization scope")

    def _emit_comment_event(
        self,
        event_type: str,
        *,
        organization_id: str,
        entity_id: str,
        actor_id: str,
        comment: object,
        db: Session | None = None,
    ) -> None:
        """Best-effort write to audit_events. Never raises."""
        if self.audit_events_service is None:
            return
        try:
            entity_type_name = (
                self.db.entity_type_name_by_id(
                    db,
                    organization_id=organization_id,
                    entity_type_id=getattr(comment, "entity_type", None),
                )
                if db is not None
                else None
            )
            text = getattr(comment, "text", "") or ""
            self.audit_events_service.emit_audit_event(
                organization_id=organization_id,
                metadata_type=AuditMetadataType.ENTITY,
                entity_id=entity_id,
                entity_type=entity_type_name,
                event_type=event_type,
                actor_type="user",
                actor_id=actor_id,
                user_id=actor_id,
                source="api",
                event_metadata={
                    "comment_id": getattr(comment, "id", None),
                    "parent_id": getattr(comment, "parent_id", None),
                    "content_preview": text[:100],
                    "is_internal": getattr(comment, "visibility", None) == "internal",
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("emit_comment_event failed: %s", exc)

    @staticmethod
    def _require_actor_field(actor: dict[str, object], field_name: str) -> str:
        """Extract a required string field from the actor dict, raising ``ValidationError`` if absent."""
        value = actor_str(actor, field_name)
        if not value:
            raise ValidationError(f"Missing actor field: {field_name}")
        return value
