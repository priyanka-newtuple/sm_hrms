"""Seed remaining system email templates (calendar invite, action-failed alert,
password reset, new-user and new-org admin notifications).

Moves these hardcoded email bodies out of the code and into system-owned
templates so orgs can customize them and a default is always available.
Idempotent.

Revision ID: 202608090002
Revises: 202608090001
Create Date: 2026-08-09
"""

from __future__ import annotations

import os
import uuid

import sqlalchemy as sa

from alembic import op

revision = "202608090002"
down_revision = "202608090001"
branch_labels = None
depends_on = None

EMAIL_KIND_CALENDAR_INVITE = "calendar.invite"
EMAIL_KIND_ACTION_FAILED = "notification.action_failed"
EMAIL_KIND_PASSWORD_RESET = "auth.password_reset"
EMAIL_KIND_NEW_USER = "notification.new_user"
EMAIL_KIND_NEW_ORG = "notification.new_org"


def _definitions_schema() -> str:
    return os.environ.get("POSTGRES_APP_SCHEMA", "public") + "_definitions"


CALENDAR_INVITE_BODY_HTML = """
<html><body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
<div style="max-width: 600px; margin: 0 auto; padding: 20px;">
<h2 style="color: #0047AB; margin-bottom: 20px;">{{title}}</h2>
<div style="background-color: #f8f9fa; border-radius: 8px; padding: 20px; margin-bottom: 20px;">
<p style="margin: 0 0 10px 0;"><strong>When:</strong> {{when}}</p>
{{location_block}}{{description_block}}</div>
<p style="color: #666; font-size: 14px;">You have been invited to this event. Please add it to your calendar.</p>
<hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
<p style="color: #999; font-size: 12px;">Organized by: {{organizer}}</p>
</div></body></html>
"""

ACTION_FAILED_BODY_HTML = """
<p>An action in your workflow has failed and requires human intervention.</p>
<p><strong>Action:</strong> {{action_kind}}</p>
<p><strong>Entity:</strong> {{entity_id}}</p>
<p><strong>Error:</strong> {{error}}</p>
<p>The workflow has been paused. Please review and take action.</p>
"""

PASSWORD_RESET_BODY_HTML = """
<html><body style="margin:0;padding:0;background:#f5f5f5;font-family:-apple-system,sans-serif;">
<div style="max-width:600px;margin:0 auto;padding:20px;">
<div style="background:#fff;border-radius:8px;padding:24px;box-shadow:0 1px 3px rgba(0,0,0,.1);">
<h2 style="color:#0047AB;">Reset Your Password</h2>
<p>Hi {{user_name}},</p>
<p>We received a request to reset your password.</p>
<a href="{{reset_url}}" style="display:inline-block;background:#0047AB;color:#fff;padding:14px 28px;text-decoration:none;border-radius:6px;font-weight:500;">Reset Password</a>
<p style="font-size:13px;color:#999;margin-top:20px;">This link expires in 1 hour.</p>
</div></div></body></html>
"""

NEW_USER_BODY_HTML = """
<html><body style="font-family:sans-serif;color:#333;background:#f5f5f5;margin:0;padding:0;">
<div style="max-width:600px;margin:0 auto;padding:20px;">
<div style="background:#fff;border-radius:8px;padding:24px;">
<h2 style="color:#0047AB;border-bottom:1px solid #eee;padding-bottom:16px;margin:0 0 16px 0;">New User Registration</h2>
<div style="background:#f0f7ff;border-radius:6px;padding:16px;margin-bottom:16px;">
  <p style="margin:0 0 8px 0;"><strong>Name:</strong> {{new_user_name}}</p>
  <p style="margin:0;"><strong>Email:</strong> {{new_user_email}}</p>
</div>
<p style="color:#666;">A new user has registered and is awaiting approval.</p>
<a href="{{approval_url}}" style="display:inline-block;background:#0047AB;color:#fff;padding:12px 24px;text-decoration:none;border-radius:6px;font-weight:500;">Review &amp; Approve</a>
</div></div></body></html>
"""

NEW_ORG_BODY_HTML = """
<html><body style="font-family:sans-serif;color:#333;background:#f5f5f5;margin:0;padding:0;">
<div style="max-width:600px;margin:0 auto;padding:20px;">
<div style="background:#fff;border-radius:8px;padding:24px;">
<h2 style="color:#0047AB;border-bottom:1px solid #eee;padding-bottom:16px;margin:0 0 16px 0;">New Organization Request</h2>
<div style="background:#f0f7ff;border-radius:6px;padding:16px;margin-bottom:16px;">
  <p style="margin:0 0 8px 0;"><strong>Organization:</strong> {{org_name}}</p>
  <p style="margin:0 0 8px 0;"><strong>Requested by:</strong> {{requester_name}}</p>
  <p style="margin:0;"><strong>Email:</strong> {{requester_email}}</p>
</div>
<p style="color:#666;">A new organization has been requested and is awaiting your approval.</p>
<a href="{{approval_url}}" style="display:inline-block;background:#0047AB;color:#fff;padding:12px 24px;text-decoration:none;border-radius:6px;font-weight:500;">Review &amp; Approve</a>
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

_TEMPLATES = [
    ("Calendar invite", "Calendar Invite: {{title}}", CALENDAR_INVITE_BODY_HTML, EMAIL_KIND_CALENDAR_INVITE),
    ("Action failed alert", "Action failed: {{action_kind}}", ACTION_FAILED_BODY_HTML, EMAIL_KIND_ACTION_FAILED),
    ("Password reset", "Reset your password", PASSWORD_RESET_BODY_HTML, EMAIL_KIND_PASSWORD_RESET),
    ("New user registration", "New user registration: {{new_user_name}}", NEW_USER_BODY_HTML, EMAIL_KIND_NEW_USER),
    ("New organization request", "New organization request: {{org_name}}", NEW_ORG_BODY_HTML, EMAIL_KIND_NEW_ORG),
]


def upgrade() -> None:
    schema = _definitions_schema()
    conn = op.get_bind()
    for name, subject, body_html, action_kind in _TEMPLATES:
        conn.execute(
            sa.text(_INSERT_SQL.format(schema=schema)),
            {
                "template_id": str(uuid.uuid4()),
                "name": name,
                "subject": subject,
                "body_html": body_html,
                "action_kind": action_kind,
            },
        )


def downgrade() -> None:
    schema = _definitions_schema()
    conn = op.get_bind()
    conn.execute(
        sa.text(
            f'DELETE FROM "{schema}".email_templates '
            f"WHERE action_kind IN (:k1, :k2, :k3, :k4, :k5) AND is_system = TRUE"
        ),
        {
            "k1": EMAIL_KIND_CALENDAR_INVITE,
            "k2": EMAIL_KIND_ACTION_FAILED,
            "k3": EMAIL_KIND_PASSWORD_RESET,
            "k4": EMAIL_KIND_NEW_USER,
            "k5": EMAIL_KIND_NEW_ORG,
        },
    )
