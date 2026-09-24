"""Response schemas for the mail module."""

from __future__ import annotations

from pydantic import Field

from common.data_model import BaseModel as PydanticBaseModel


class EmailSendResult(PydanticBaseModel):
    """Result of sending an email."""

    success: bool
    message: str
    message_id: str | None = None


class EmailTestResponse(PydanticBaseModel):
    success: bool
    message: str
    message_id: str | None = Field(None, description="SES message ID if successful")
