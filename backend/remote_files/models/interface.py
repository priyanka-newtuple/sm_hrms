"""Contracts returned by the remote-files service."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class FetchedRemoteFile(BaseModel):
    """Validated immutable result of retrieving one external file."""

    model_config = ConfigDict(frozen=True)

    source_url: str
    final_url: str
    filename: str
    content_type: str
    content: bytes
    sha256: str
    etag: str | None = None
    last_modified: str | None = None
