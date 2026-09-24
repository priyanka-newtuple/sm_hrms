"""Seed the system email template for user invitations.

Moves the invitation email body out of the invitation manager and into a
system-owned email template so an organization can customize it (and the default
is always available). Idempotent.

Revision ID: 202608090001
Revises: 202608080002
Create Date: 2026-08-09
"""

from __future__ import annotations

import os
import uuid

import sqlalchemy as sa

from alembic import op

revision = "202608090001"
down_revision = "202608080002"
branch_labels = None
depends_on = None

EMAIL_KIND_INVITATION = "user.invitation"


def _definitions_schema() -> str:
    return os.environ.get("POSTGRES_APP_SCHEMA", "public") + "_definitions"


INVITATION_BODY_HTML = """
<html>
<body style="margin:0;padding:0;background-color:#f5f5f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#333;line-height:1.5;">
  <div style="max-width:600px;margin:0 auto;padding:20px;">
    <div style="background-color:white;border-radius:8px;padding:24px;box-shadow:0 1px 3px rgba(0,0,0,0.1);">
      <div style="border-bottom:1px solid #eee;padding-bottom:16px;margin-bottom:16px;">
        <h2 style="margin:0;color:#0047AB;font-size:20px;">You're Invited!</h2>
      </div>
      <p style="margin:0 0 16px 0;font-size:16px;">
        {{inviter_name}} has invited you to join <strong>{{org_name}}</strong> as a <strong>{{role}}</strong>.
      </p>
      <div style="background-color:#f0f7ff;border-radius:6px;padding:16px;margin:20px 0;">
        <p style="margin:0;font-size:14px;color:#666;">
          <strong>Organization:</strong> {{org_name}}<br>
          <strong>Role:</strong> {{role}}<br>
          <strong>Expires:</strong> {{expires}}
        </p>
      </div>
      <a href="{{accept_url}}" style="display:inline-block;background-color:#0047AB;color:white;padding:14px 28px;text-decoration:none;border-radius:6px;margin-top:8px;font-weight:500;font-size:16px;">
        Accept Invitation
      </a>
      <p style="margin:20px 0 0 0;font-size:13px;color:#999;">
        This invitation expires on {{expires}}. If you did not expect this invitation, you can safely ignore this email.
      </p>
    </div>
  </div>
</body>
</html>"""


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
            "name": "User invitation",
            "subject": "You're invited to join {{org_name}}",
            "body_html": INVITATION_BODY_HTML,
            "action_kind": EMAIL_KIND_INVITATION,
        },
    )


def downgrade() -> None:
    schema = _definitions_schema()
    conn = op.get_bind()
    conn.execute(
        sa.text(
            f'DELETE FROM "{schema}".email_templates '
            f"WHERE action_kind = :kind AND is_system = TRUE"
        ),
        {"kind": EMAIL_KIND_INVITATION},
    )
