"""Interface models and contracts for comments."""

from __future__ import annotations

import re

from pydantic import ConfigDict

from common.data_model import BaseModel as PydanticBaseModel

PIPELINE_ROUTE_PREFIX = "/pipeline"

MENTION_PATTERN = re.compile(r"@\[([^\]]+)\]\(([^)]+)\)")


def render_mentions_as_text(text: str) -> str:
    """Turn `@[Full Name](user_id)` tokens into plain `@Full Name` — the stored
    form is for the UI to resolve; emails need the readable one."""
    return MENTION_PATTERN.sub(lambda match: f"@{match.group(1)}", text or "")


def build_comment_link(
    workflow_id: str, entity_id: str, comment_id: str, *, reply_id: str | None = None
) -> str:
    """Frontend route to an entity's comment thread on the pipeline board.

    ``comment_id`` must be a top-level comment — replies are lazy-loaded, so
    linking straight to a reply's own id wouldn't find anything to scroll to
    until its parent's replies are expanded.
    """
    link = (
        f"{PIPELINE_ROUTE_PREFIX}/{workflow_id}"
        f"?entity={entity_id}&tab=comments&comment={comment_id}"
    )
    if reply_id:
        link += f"&reply={reply_id}"
    return link


class CommentThreadKey(PydanticBaseModel):
    model_config = ConfigDict(frozen=True)

    entity_id: str
    organization_id: str


def normalize_mentions(raw_mentions: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for mention in raw_mentions:
        user_id = str(mention).strip()
        if not user_id or user_id in seen:
            continue
        seen.add(user_id)
        normalized.append(user_id)
    return normalized