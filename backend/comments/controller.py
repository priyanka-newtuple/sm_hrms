"""Comments REST controller module."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Request, status

from comments.models.request import CommentCreateRequest, CommentReplyRequest, CommentUpdateRequest
from comments.models.response import CommentListResponse, CommentResponse
from common.auth import require_permission
from common.deps import get_db
from common.logger import logger, tracer
from common.utils import raise_http_error

if TYPE_CHECKING:
    from fastapi.params import Depends as DependsParam

    from auth.manager import AuthServiceManager
    from comments.manager import CommentsServiceManager
    from database.manager import DatabaseServiceManager

CommentReadActor = Annotated[dict[str, object], Depends(require_permission("comment", "read"))]
CommentWriteActor = Annotated[dict[str, object], Depends(require_permission("comment", "write"))]


class CommentsRestController:
    """Implements comments REST controller."""

    def __init__(
        self,
        comments_service_manager: CommentsServiceManager,
        database_service_manager: DatabaseServiceManager,
        auth_service_manager: AuthServiceManager,
    ) -> None:
        super().__init__()
        self.manager = comments_service_manager
        self.database_service_manager = database_service_manager
        self.auth_service_manager = auth_service_manager

    @staticmethod
    def _route_dependencies(security: DependsParam | None) -> list[DependsParam] | None:
        """Wrap security dependency in a list, or return None if no security is configured."""
        return [security] if security else None

    @staticmethod
    def _error_context(request_id: str, operation: str) -> dict[str, str]:
        """Build a structured error context dict for logging and HTTP error responses."""
        return {
            "request_id": request_id,
            "controller": "CommentsRestController",
            "operation": operation,
        }

    def prepare(self, app: APIRouter, security: DependsParam | None = None) -> None:
        """Prepare the comments REST controller."""
        route_dependencies = self._route_dependencies(security)

        @app.get(
            "/comments/status",
            status_code=status.HTTP_200_OK,
            tags=["comments"],
            dependencies=route_dependencies,
        )
        def status_endpoint(request: Request):
            """Return the health status of the comments service."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("CommentsController.status"):
                try:
                    logger.info("comments status requested", extra={"request_id": request_id})
                    return self.manager.get_status()
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "status"))

        @app.post(
            "/entities/{entity_id}/comments",
            response_model=CommentResponse,
            status_code=status.HTTP_201_CREATED,
            tags=["comments"],
            dependencies=route_dependencies,
        )
        def create_entity_comment_endpoint(
            request: Request,
            entity_id: str,
            payload: CommentCreateRequest,
            actor: CommentWriteActor,
            background_tasks: BackgroundTasks,
            db: Any = Depends(get_db),
        ):
            """Create a new comment on an entity, optionally scoped to a workflow state."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("CommentsController.create_entity_comment"):
                try:
                    logger.info("comments create", extra={"request_id": request_id})
                    return self.manager.create_comment(
                        db, actor, entity_id, payload, background_tasks=background_tasks
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "create_entity_comment"))

        @app.get(
            "/entities/{entity_id}/comments",
            response_model=CommentListResponse,
            status_code=status.HTTP_200_OK,
            tags=["comments"],
            dependencies=route_dependencies,
        )
        def list_entity_comments_endpoint(
            request: Request,
            entity_id: str,
            actor: CommentReadActor,
            state_name: str | None = None,
            include_archived: bool = False,
            db: Any = Depends(get_db),
        ):
            """List all comments for an entity, with an optional state filter."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("CommentsController.list_entity_comments"):
                try:
                    logger.info("comments list", extra={"request_id": request_id})
                    return self.manager.list_comments(
                        db,
                        actor,
                        entity_id,
                        state_name=state_name,
                        include_archived=include_archived,
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "list_entity_comments"))

        @app.post(
            "/comments/{comment_id}/replies",
            response_model=CommentResponse,
            status_code=status.HTTP_201_CREATED,
            tags=["comments"],
            dependencies=route_dependencies,
        )
        def reply_to_comment_endpoint(
            request: Request,
            comment_id: str,
            payload: CommentReplyRequest,
            actor: CommentWriteActor,
            background_tasks: BackgroundTasks,
            db: Any = Depends(get_db),
        ):
            """Reply to a top-level comment. Entity id and visibility are inherited from the parent."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("CommentsController.reply_to_comment"):
                try:
                    logger.info("comments reply", extra={"request_id": request_id})
                    return self.manager.reply_to_comment(
                        db, actor, comment_id, payload, background_tasks=background_tasks
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "reply_to_comment"))

        @app.get(
            "/comments/{comment_id}/replies",
            response_model=CommentListResponse,
            status_code=status.HTTP_200_OK,
            tags=["comments"],
            dependencies=route_dependencies,
        )
        def list_comment_replies_endpoint(
            request: Request,
            comment_id: str,
            actor: CommentReadActor,
            include_archived: bool = False,
            db: Any = Depends(get_db),
        ):
            """List the replies to a top-level comment — fetched on demand, not eagerly with the main list."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("CommentsController.list_comment_replies"):
                try:
                    logger.info("comments list_replies", extra={"request_id": request_id})
                    return self.manager.list_replies(
                        db, actor, comment_id, include_archived=include_archived
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "list_comment_replies"))

        @app.post(
            "/comments/{comment_id}/like",
            response_model=CommentResponse,
            status_code=status.HTTP_200_OK,
            tags=["comments"],
            dependencies=route_dependencies,
        )
        def toggle_comment_like_endpoint(
            request: Request,
            comment_id: str,
            actor: CommentWriteActor,
            background_tasks: BackgroundTasks,
            db: Any = Depends(get_db),
        ):
            """Toggle the current user's like on a comment."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("CommentsController.toggle_comment_like"):
                try:
                    return self.manager.toggle_like(
                        db, actor, comment_id, background_tasks=background_tasks
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "toggle_comment_like"))

        @app.patch(
            "/comments/{comment_id}",
            response_model=CommentResponse,
            status_code=status.HTTP_200_OK,
            tags=["comments"],
            dependencies=route_dependencies,
        )
        def update_comment_endpoint(
            request: Request,
            comment_id: str,
            payload: CommentUpdateRequest,
            actor: CommentWriteActor,
            background_tasks: BackgroundTasks,
            db: Any = Depends(get_db),
        ):
            """Update the text and mentions of an existing comment."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("CommentsController.update_comment"):
                try:
                    logger.info("comments update", extra={"request_id": request_id})
                    return self.manager.update_comment(
                        db, actor, comment_id, payload, background_tasks=background_tasks
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "update_comment"))

        @app.delete(
            "/comments/{comment_id}",
            status_code=status.HTTP_200_OK,
            tags=["comments"],
            dependencies=route_dependencies,
        )
        def archive_comment_endpoint(
            request: Request,
            comment_id: str,
            actor: CommentWriteActor,
            db: Any = Depends(get_db),
        ):
            """Soft-delete a comment by setting its archived_at timestamp."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("CommentsController.archive_comment"):
                try:
                    logger.info("comments archive", extra={"request_id": request_id})
                    self.manager.archive_comment(db, actor, comment_id)
                    return {"message": "Comment archived successfully"}
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "archive_comment"))
