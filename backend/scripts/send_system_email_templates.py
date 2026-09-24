"""Manual e2e check: render and send every seeded system email template.

Drives the real outbound pipeline for each system template
(get_default_email_template_for_kind -> render {{placeholders}} -> send_email ->
provider strategy -> SMTP/SES) and sends one message per template to a target
address. Use it to confirm template rendering + email delivery work end to end
after configuring an email provider in Settings -> Integrations.

This is a manual utility (it sends real email), not part of the pytest suite.

Run it inside the backend container, e.g.:

    docker compose -f docker-compose.local.yml exec \
        -e E2E_EMAIL_TO=you@example.com modular-backend \
        python scripts/send_system_email_templates.py

or pass the recipient explicitly:

    python scripts/send_system_email_templates.py --to you@example.com [--org <org_id>]

The recipient must be provided via --to or the E2E_EMAIL_TO env var; the target
org (default: the seed org) must have an email provider configured.
"""

from __future__ import annotations

import argparse
import os
import sys

# Allow running as `python scripts/send_system_email_templates.py` from backend/:
# ensure the backend root (parent of this scripts/ dir) is importable.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from mail.db_models import MailModelService
from mail.manager import MailServiceManager

DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"

# Every seeded system template action_kind.
TEMPLATE_KINDS = [
    "notification.mention",
    "notification.comment",
    "notification.assignment",
    "user.invitation",
    "calendar.invite",
    "notification.action_failed",
    "auth.password_reset",
    "notification.new_user",
    "notification.new_org",
]

# Sample values covering every placeholder used across the templates. Extra keys
# are harmless — the renderer only substitutes placeholders that appear.
SAMPLE_VALUES = {
    "actor_name": "Alice Admin",
    "comment_text": "Please review this candidate.",
    "link": "https://example.com/entity/123",
    "entity_label": "Job: Senior Engineer",
    "inviter_name": "Alice Admin",
    "org_name": "Acme Corp",
    "role": "Recruiter",
    "expires": "August 20, 2026",
    "accept_url": "https://example.com/accept-invite?token=demo",
    "title": "Interview with Candidate",
    "when": "August 20, 2026 at 02:00 PM - 03:00 PM",
    "location_block": "<p><strong>Where:</strong> Zoom</p>",
    "description_block": "<p><strong>Description:</strong><br>Technical round</p>",
    "organizer": "Alice Admin",
    "action_kind": "mail.send_email",
    "entity_id": "ent-123",
    "error": "Example error message",
    "user_name": "Test User",
    "reset_url": "https://example.com/reset-password?token=demo",
    "new_user_name": "Carol New",
    "new_user_email": "carol@example.com",
    "approval_url": "https://example.com/settings?tab=users",
    "requester_name": "Dan Requester",
    "requester_email": "dan@example.com",
}


def _session():
    schema = os.environ.get("POSTGRES_APP_SCHEMA", "modular_backend")
    engine = create_engine(
        os.environ["DATABASE_URL"],
        future=True,
        connect_args={"options": f"-csearch_path={schema},{schema}_definitions,public"},
    )
    return sessionmaker(bind=engine, future=True)()


def main() -> int:
    parser = argparse.ArgumentParser(description="Send every system email template to a target address.")
    parser.add_argument("--to", default=os.environ.get("E2E_EMAIL_TO"), help="Recipient email (or set E2E_EMAIL_TO).")
    parser.add_argument("--org", default=os.environ.get("E2E_ORG_ID", DEFAULT_ORG_ID), help="Organization id whose email provider is used.")
    args = parser.parse_args()

    if not args.to:
        parser.error("recipient required: pass --to or set E2E_EMAIL_TO")

    db = _session()
    mail = MailServiceManager(email_config_model_service=MailModelService())
    results: list[tuple[str, str, bool]] = []
    try:
        for kind in TEMPLATE_KINDS:
            template = mail.get_default_email_template_for_kind(db, args.org, kind)
            if not template:
                results.append((kind, "NO TEMPLATE", False))
                continue
            subject = "[E2E test] " + mail._render_template(template["subject"], SAMPLE_VALUES)
            body_html = mail._render_template(template["body_html"], SAMPLE_VALUES)
            leftover = "{{" in subject or "{{" in body_html
            result = mail.send_email(db=db, org_id=args.org, to=args.to, subject=subject, body_html=body_html)
            ok = result.success and not leftover
            note = "sent" if result.success else result.message
            if leftover:
                note += " [LEFTOVER PLACEHOLDER]"
            results.append((kind, note, ok))
    finally:
        db.close()

    print(f"\n=== System email template e2e (to {args.to}, org {args.org}) ===")
    for kind, note, ok in results:
        print(f"  {'OK  ' if ok else 'FAIL'} {kind:28s} -> {note}")
    sent = sum(1 for _, _, ok in results if ok)
    print(f"\nSENT {sent}/{len(results)} successfully")
    return 0 if sent == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
