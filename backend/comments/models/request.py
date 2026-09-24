from __future__ import annotations

from pydantic import BaseModel, field_validator


class CommentCreateRequest(BaseModel):
    text: str
    visibility: str = "all"
    visible_to_roles: list[str] | None = None
    workflow_id: str | None = None
    parent_id: str | None = None

    @field_validator("text")
    @classmethod
    def text_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("text cannot be empty")
        return v

    @field_validator("visibility")
    @classmethod
    def visibility_valid(cls, v: str) -> str:
        allowed = {"all", "internal", "role_restricted"}
        if v not in allowed:
            raise ValueError(f"visibility must be one of {allowed}")
        return v


class CommentUpdateRequest(BaseModel):
    text: str

    @field_validator("text")
    @classmethod
    def text_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("text cannot be empty")
        return v


class CommentReplyRequest(BaseModel):
    """Body for POST /comments/{comment_id}/replies — entity_id and parent_id
    are supplied by the route, not the client."""

    text: str

    @field_validator("text")
    @classmethod
    def text_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("text cannot be empty")
        return v