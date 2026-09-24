"""Seed system email templates for reply and like notifications.

Same visual structure as the existing mention/comment templates
(2026_08_03_0001) — reply reuses their quoted-comment callout plus a
reply-preview line; like drops the callout since there's no reply text.

Revision ID: 202608140002
Revises: 202608140001
Create Date: 2026-08-14
"""

from __future__ import annotations

import os
import uuid

import sqlalchemy as sa

from alembic import op

revision = "202608140002"
down_revision = "202608140001"
branch_labels = None
depends_on = None

EMAIL_KIND_REPLY = "notification.reply"
EMAIL_KIND_LIKE = "notification.like"


def _definitions_schema() -> str:
    return os.environ.get("POSTGRES_APP_SCHEMA", "public") + "_definitions"


REPLY_BODY_HTML = """
<html><body style="font-family:sans-serif;color:#333;background:#f5f5f5;margin:0;padding:0;">
<div style="max-width:600px;margin:0 auto;padding:20px;">
<div style="background:#fff;border-radius:8px;padding:24px;">
<h2 style="color:#0047AB;border-bottom:1px solid #eee;padding-bottom:16px;margin:0 0 16px 0;">{{actor_name}} replied to your comment</h2>
<div style="background:#f0f7ff;border-left:3px solid #0047AB;padding:12px 16px;border-radius:0 6px 6px 0;margin-bottom:12px;">
  <div style="font-size:13px;color:#666;margin-bottom:4px;">Your comment:</div>
  <div style="white-space:pre-wrap;">{{comment_text}}</div>
</div>
<div style="background:#fff8e6;border-left:3px solid #f5a623;padding:12px 16px;border-radius:0 6px 6px 0;margin-bottom:16px;">
  <div style="font-size:13px;color:#666;margin-bottom:4px;"><strong>{{actor_name}}</strong> replied:</div>
  <div style="white-space:pre-wrap;">{{reply_text}}</div>
</div>
<a href="{{link}}" style="display:inline-block;background:#0047AB;color:#fff;padding:12px 24px;text-decoration:none;border-radius:6px;font-weight:500;">View &amp; Reply</a>
</div></div></body></html>
"""

LIKE_BODY_HTML = """
<html><body style="font-family:sans-serif;color:#333;background:#f5f5f5;margin:0;padding:0;">
<div style="max-width:600px;margin:0 auto;padding:20px;">
<div style="background:#fff;border-radius:8px;padding:24px;">
<h2 style="color:#0047AB;border-bottom:1px solid #eee;padding-bottom:16px;margin:0 0 16px 0;">{{actor_name}} liked your comment</h2>
<div style="background:#f0f7ff;border-left:3px solid #0047AB;padding:12px 16px;border-radius:0 6px 6px 0;margin-bottom:16px;">
  <div style="white-space:pre-wrap;">{{comment_text}}</div>
</div>
<a href="{{link}}" style="display:inline-block;background:#0047AB;color:#fff;padding:12px 24px;text-decoration:none;border-radius:6px;font-weight:500;">View</a>
</div></div></body></html>
"""


_INSERT_SQL = """
    INSERT INTO "{schema}".email_templates
        (template_id, organization_id, name, subject, body_html, action_kind, is_system)
    SELECT :template_id, NULL, :name, :subject, :body_html, :action_kind, TRUE
    WHERE NOT EXISTS (
        SELECT 1 FROM "{schema}".email_templates
        WHERE action_kind = :action_kind AND is_system = TRUE
    )
"""


def upgrade() -> None:
    schema = _definitions_schema()
    conn = op.get_bind()
    conn.execute(
        sa.text(_INSERT_SQL.format(schema=schema)),
        {
            "template_id": str(uuid.uuid4()),
            "name": "Reply notification",
            "subject": "{{actor_name}} replied to your comment",
            "body_html": REPLY_BODY_HTML,
            "action_kind": EMAIL_KIND_REPLY,
        },
    )
    conn.execute(
        sa.text(_INSERT_SQL.format(schema=schema)),
        {
            "template_id": str(uuid.uuid4()),
            "name": "Like notification",
            "subject": "{{actor_name}} liked your comment",
            "body_html": LIKE_BODY_HTML,
            "action_kind": EMAIL_KIND_LIKE,
        },
    )


def downgrade() -> None:
    schema = _definitions_schema()
    conn = op.get_bind()
    conn.execute(
        sa.text(
            f'DELETE FROM "{schema}".email_templates '
            f"WHERE action_kind IN (:reply_kind, :like_kind) AND is_system = TRUE"
        ),
        {
            "reply_kind": EMAIL_KIND_REPLY,
            "like_kind": EMAIL_KIND_LIKE,
        },
    )
