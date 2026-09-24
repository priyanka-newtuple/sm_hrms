from __future__ import annotations

from pydantic import BaseModel

from comments.db_models import Comment


class MentionInfo(BaseModel):
    user_id: str
    full_name: str
    position: int


class LikeSummary(BaseModel):
    user_id: str
    user_name: str
    user_avatar_url: str | None = None


class CommentEditHistoryEntry(BaseModel):
    previous_text: str
    edited_at: str
    edited_by_id: str
    edited_by_name: str


class CommentResponse(BaseModel):
    id: str
    organization_id: str
    entity_id: str
    entity_type: str
    workflow_id: str | None
    state_id: str | None
    state_name: str | None
    text: str
    mentions: list[dict]
    author_id: str | None
    author_name: str
    author_role: str | None
    author_avatar_url: str | None
    parent_id: str | None
    reply_count: int = 0
    likes: list[LikeSummary]
    like_count: int
    liked_by_me: bool
    visibility: str
    visible_to_roles: list[str] | None
    is_edited: bool
    edited_at: str | None
    edit_history: list[dict]
    archived_at: str | None
    archived_by: str | None
    created_at: str

    @classmethod
    def from_orm(
        cls,
        comment: object,
        *,
        reply_count: int = 0,
        current_user_id: str | None = None,
    ) -> "CommentResponse":
        c: Comment = comment  # type: ignore[assignment]
        likes = list(c.likes or [])
        return cls(
            id=c.id,
            organization_id=c.organization_id,
            entity_id=c.entity_id,
            entity_type=c.entity_type,
            workflow_id=c.workflow_id,
            state_id=c.state_id,
            state_name=c.state_name,
            text=c.text,
            mentions=list(c.mentions or []),
            author_id=c.author_id,
            author_name=c.author_name,
            author_role=c.author_role,
            author_avatar_url=getattr(c, "author_avatar_url", None),
            parent_id=getattr(c, "parent_id", None),
            reply_count=reply_count,
            likes=[LikeSummary(**like) for like in likes],
            like_count=len(likes),
            liked_by_me=bool(
                current_user_id and any(like.get("user_id") == current_user_id for like in likes)
            ),
            visibility=c.visibility,
            visible_to_roles=list(c.visible_to_roles) if c.visible_to_roles else None,
            is_edited=bool(c.is_edited),
            edited_at=c.edited_at.isoformat() if c.edited_at else None,
            edit_history=list(c.edit_history or []),
            archived_at=c.archived_at.isoformat() if c.archived_at else None,
            archived_by=c.archived_by,
            created_at=c.created_at.isoformat() if c.created_at else "",
        )


class CommentListResponse(BaseModel):
    comments: list[CommentResponse]
    total: int