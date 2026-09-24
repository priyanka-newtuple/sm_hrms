"""Seed system email templates for mention, assignment, and comment notifications.

Revision ID: 202608030001
Revises: 202607270001
Create Date: 2026-08-03
"""

from __future__ import annotations

import os
import uuid

import sqlalchemy as sa

from alembic import op

revision = "202608030001"
down_revision = "202607270001"
branch_labels = None
depends_on = None

EMAIL_KIND_MENTION = "notification.mention"
EMAIL_KIND_ASSIGNMENT = "notification.assignment"
EMAIL_KIND_COMMENT = "notification.comment"


def _definitions_schema() -> str:
    return os.environ.get("POSTGRES_APP_SCHEMA", "public") + "_definitions"


MENTION_BODY_HTML = """
<html><body style="font-family:sans-serif;color:#333;background:#f5f5f5;margin:0;padding:0;">
<div style="max-width:600px;margin:0 auto;padding:20px;">
<div style="background:#fff;border-radius:8px;padding:24px;">
<h2 style="color:#0047AB;border-bottom:1px solid #eee;padding-bottom:16px;margin:0 0 16px 0;">You were mentioned</h2>
<div style="background:#fff8e6;border-left:3px solid #f5a623;padding:12px 16px;border-radius:0 6px 6px 0;margin-bottom:16px;">
  <div style="font-size:13px;color:#666;margin-bottom:4px;"><strong>{{actor_name}}</strong> said:</div>
  <div style="white-space:pre-wrap;">{{comment_text}}</div>
</div>
<a href="{{link}}" style="display:inline-block;background:#0047AB;color:#fff;padding:12px 24px;text-decoration:none;border-radius:6px;font-weight:500;">View &amp; Reply</a>
</div></div></body></html>
"""

ASSIGNMENT_BODY_HTML = """
<html><body style="font-family:sans-serif;color:#333;background:#f5f5f5;margin:0;padding:0;">
<div style="max-width:600px;margin:0 auto;padding:20px;">
<div style="background:#fff;border-radius:8px;padding:24px;">
<h2 style="color:#0047AB;border-bottom:1px solid #eee;padding-bottom:16px;margin:0 0 16px 0;">You were assigned {{entity_label}}</h2>
<div style="font-size:14px;color:#333;margin-bottom:16px;">You are now the assignee, assigned by {{actor_name}}.</div>
<a href="{{link}}" style="display:inline-block;background:#0047AB;color:#fff;padding:12px 24px;text-decoration:none;border-radius:6px;font-weight:500;">View</a>
</div></div></body></html>
"""

COMMENT_BODY_HTML = """
<html><body style="font-family:sans-serif;color:#333;background:#f5f5f5;margin:0;padding:0;">
<div style="max-width:600px;margin:0 auto;padding:20px;">
<div style="background:#fff;border-radius:8px;padding:24px;">
<h2 style="color:#0047AB;border-bottom:1px solid #eee;padding-bottom:16px;margin:0 0 16px 0;">New comment on {{entity_label}}</h2>
<div style="background:#fff8e6;border-left:3px solid #f5a623;padding:12px 16px;border-radius:0 6px 6px 0;margin-bottom:16px;">
  <div style="font-size:13px;color:#666;margin-bottom:4px;"><strong>{{actor_name}}</strong> said:</div>
  <div style="white-space:pre-wrap;">{{comment_text}}</div>
</div>
<a href="{{link}}" style="display:inline-block;background:#0047AB;color:#fff;padding:12px 24px;text-decoration:none;border-radius:6px;font-weight:500;">View &amp; Reply</a>
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
            "name": "Mention notification",
            "subject": "{{actor_name}} mentioned you",
            "body_html": MENTION_BODY_HTML,
            "action_kind": EMAIL_KIND_MENTION,
        },
    )
    conn.execute(
        sa.text(_INSERT_SQL.format(schema=schema)),
        {
            "template_id": str(uuid.uuid4()),
            "name": "Assignment notification",
            "subject": "You were assigned {{entity_label}}",
            "body_html": ASSIGNMENT_BODY_HTML,
            "action_kind": EMAIL_KIND_ASSIGNMENT,
        },
    )
    conn.execute(
        sa.text(_INSERT_SQL.format(schema=schema)),
        {
            "template_id": str(uuid.uuid4()),
            "name": "Comment notification",
            "subject": "New comment on {{entity_label}}",
            "body_html": COMMENT_BODY_HTML,
            "action_kind": EMAIL_KIND_COMMENT,
        },
    )


def downgrade() -> None:
    schema = _definitions_schema()
    conn = op.get_bind()
    conn.execute(
        sa.text(
            f'DELETE FROM "{schema}".email_templates '
            f"WHERE action_kind IN (:mention_kind, :assignment_kind, :comment_kind) AND is_system = TRUE"
        ),
        {
            "mention_kind": EMAIL_KIND_MENTION,
            "assignment_kind": EMAIL_KIND_ASSIGNMENT,
            "comment_kind": EMAIL_KIND_COMMENT,
        },
    )
