"""Regression coverage for notifications/manager.py mention-markup rendering.

Bug: comment/reply text stores mentions as `@[Name](user_id)` markup so the
frontend can render pills, but notification bodies and email previews are
plain text — every create_*_notification path truncated+escaped the RAW text
without rendering the markup first, so recipients saw the literal
`@[Name](user_id)` (brackets, id and all) instead of `@Name`.

Text cleanup is `comments.models.interface.render_mentions_as_text` — the
canonical helper (also used by the mention/comment email preview path); the
notification-body assertions here confirm it's applied consistently across
all four notification types (mention, comment, reply, like), not just email.

Uses a mocked db_model_service — these tests exercise only the text-cleanup
step, not persistence.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from comments.models.interface import render_mentions_as_text
from notifications.manager import NotificationsServiceManager


def _fake_notification_row(**overrides: object) -> dict[str, object]:
    base = {
        "id": "notif-1",
        "organization_id": "org-1",
        "recipient_id": "user-1",
        "notification_type": "mention",
        "source_type": "comment",
        "source_id": "comment-1",
        "entity_id": "entity-1",
        "entity_type": "ATS.Candidate",
        "actor_id": "actor-1",
        "actor_name": "Bootstrap Super Admin",
        "title": "Bootstrap Super Admin mentioned you",
        "body": None,
        "link": None,
        "is_read": False,
        "read_at": None,
        "created_at": datetime.now(timezone.utc),
    }
    base.update(overrides)
    return base


def _build_manager() -> NotificationsServiceManager:
    db_service = MagicMock()
    db_service.create_notification.side_effect = lambda **kwargs: _fake_notification_row(
        body=kwargs.get("body"), link=kwargs.get("link")
    )
    manager = NotificationsServiceManager(
        db_service,
        database_service_manager=None,
        config=None,
    )
    manager.start()
    return manager


def test_render_mentions_as_text_turns_markup_into_plain_at_name() -> None:
    raw = "@[Vinay Kumar](a10d6d27-6af7-4f93-83f1-f5f3b8bd1ad4)  hwlloo"
    assert render_mentions_as_text(raw) == "@Vinay Kumar  hwlloo"


def test_render_mentions_as_text_handles_multiple_mentions_and_plain_text() -> None:
    raw = "hey @[Bob](id-1) and @[Ann Lee](id-2), please check this out"
    assert render_mentions_as_text(raw) == "hey @Bob and @Ann Lee, please check this out"


def test_render_mentions_as_text_is_a_noop_on_text_without_mentions() -> None:
    raw = "no mentions here, just [brackets] and (parens)"
    assert render_mentions_as_text(raw) == raw


def test_create_mention_notification_body_has_no_raw_markup() -> None:
    """The exact bug report: a real email showed
    '@[Vinay Kumar](a10d6d27-6af7-4f93-83f1-f5f3b8bd1ad4)  hwlloo' verbatim."""
    manager = _build_manager()
    comment_text = "@[Vinay Kumar](a10d6d27-6af7-4f93-83f1-f5f3b8bd1ad4)  hwlloo"

    notification = manager.create_mention_notification(
        organization_id="org-1",
        recipient_id="user-1",
        entity_id="entity-1",
        entity_type="ATS.Candidate",
        comment_id="comment-1",
        comment_text=comment_text,
        actor_id="actor-1",
        actor_name="Bootstrap Super Admin",
    )

    assert notification.body == "@Vinay Kumar  hwlloo"
    assert "[" not in notification.body
    assert "]" not in notification.body
    assert "a10d6d27-6af7-4f93-83f1-f5f3b8bd1ad4" not in notification.body


def test_create_reply_notification_strips_markup_from_both_texts() -> None:
    manager = _build_manager()

    notification = manager.create_reply_notification(
        organization_id="org-1",
        recipient_id="user-1",
        entity_id="entity-1",
        entity_type="ATS.Candidate",
        comment_id="reply-1",
        parent_comment_text="original @[Alice](id-a) comment",
        reply_text="replying to @[Bob](id-b) now",
        actor_id="actor-1",
        actor_name="Actor",
    )

    assert notification.body == "replying to @Bob now"


def test_create_comment_notification_and_like_notification_strip_markup() -> None:
    manager = _build_manager()
    comment_text = "loop in @[Priya](id-p) please"

    comment_notification = manager.create_comment_notification(
        organization_id="org-1",
        recipient_id="user-1",
        entity_id="entity-1",
        entity_type="ATS.Candidate",
        entity_label="Candidate X",
        comment_id="comment-1",
        comment_text=comment_text,
        actor_id="actor-1",
        actor_name="Actor",
    )
    like_notification = manager.create_like_notification(
        organization_id="org-1",
        recipient_id="user-1",
        entity_id="entity-1",
        entity_type="ATS.Candidate",
        comment_id="comment-1",
        comment_text=comment_text,
        actor_id="actor-1",
        actor_name="Actor",
    )

    assert comment_notification.body == "loop in @Priya please"
    assert like_notification.body == "loop in @Priya please"
