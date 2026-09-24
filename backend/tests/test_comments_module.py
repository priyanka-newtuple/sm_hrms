"""Regression coverage for comments/db_models.py + comments/manager.py + controller.py listing.

Bug: comment fetches were scoped by (entity_id, workflow_id) instead of
entity_id alone. `Comment.workflow_id` is a creation-time snapshot of whichever
workflow version an entity was enrolled in when the comment was written —
republishing a funnel repoints the entity to a new `WorkflowStateMachineModel`
row, but existing comment rows keep their old snapshot. Filtering the list
query on an exact match against the entity's *current* workflow_id therefore
made older comments disappear even though the rows were untouched.

Uses real Postgres via the `entities_db_service_manager` fixture (see
conftest.py) — the `comments` table has no foreign keys, so these tests write
directly to it without needing real entity/workflow rows.
"""

from __future__ import annotations

import os
from typing import Annotated
from unittest.mock import ANY, MagicMock

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

import comments.controller as comments_controller_module
from comments.db_models import CommentModelService
from comments.manager import CommentsServiceManager
from comments.models.response import CommentListResponse
from common.deps import get_db
from tests.conftest import ENTITIES_TEST_ORG_IDS

ORG_1 = ENTITIES_TEST_ORG_IDS[0]


def _runtime_schema() -> str:
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "modular_backend")
    return f"{app_schema}_runtime"


def _seed_comment(
    comment_service: CommentModelService,
    db_session,
    *,
    entity_id: str,
    text: str,
    workflow_id: str,
    state_id: str | None = None,
    state_name: str | None = None,
):
    """Persist one comment row for the given entity, tagged with a workflow_id snapshot.

    author_id is left unset (nullable) — comments.author_id has an FK to users
    that isn't reflected in the SQLAlchemy model, and author identity isn't
    relevant to this listing behavior.
    """
    return comment_service.create(
        db_session,
        organization_id=ORG_1,
        entity_id=entity_id,
        entity_type="ATS.Candidate",
        text=text,
        author_id=None,
        author_name="Alice",
        workflow_id=workflow_id,
        state_id=state_id,
        state_name=state_name,
    )


@pytest.fixture
def clean_comments_table(entities_db_service_manager):
    """Truncate test-org rows from runtime.comments around the requesting test."""
    runtime_schema = _runtime_schema()
    engine = entities_db_service_manager.postgres_db_service().engine

    def _cleanup() -> None:
        with engine.begin() as conn:
            conn.execute(
                text(f'DELETE FROM "{runtime_schema}".comments WHERE organization_id = ANY(:ids)'),
                {"ids": list(ENTITIES_TEST_ORG_IDS)},
            )

    _cleanup()
    yield
    _cleanup()


@pytest.fixture
def db_session(entities_db_service_manager):
    session = entities_db_service_manager.postgres_db_service().get_db_session()
    yield session
    session.close()


@pytest.fixture
def comment_service() -> CommentModelService:
    return CommentModelService()


@pytest.fixture
def comments_manager(comment_service) -> CommentsServiceManager:
    mgr = CommentsServiceManager(
        comment_model_service=comment_service,
        database_service_manager=None,
        config=None,
    )
    mgr.start()
    return mgr


def _actor(org: str = ORG_1) -> dict[str, object]:
    return {"user_id": "admin-user", "organization_id": org, "roles": ["admin"]}


def test_list_for_entity_ignores_stored_workflow_id(
    db_session, comment_service, clean_comments_table
) -> None:
    """Two comments on the same entity, stamped with different workflow_id
    snapshots (simulating one written before and one after a funnel
    republish), must both come back from a plain entity-scoped fetch."""
    entity_id = "entity-repointed-1"

    old_version_comment = _seed_comment(
        comment_service,
        db_session,
        entity_id=entity_id,
        text="Left before the funnel was republished",
        workflow_id="wf-version-old",
        state_name="APPLIED",
    )
    new_version_comment = _seed_comment(
        comment_service,
        db_session,
        entity_id=entity_id,
        text="Left after the republish",
        workflow_id="wf-version-new",
        state_name="APPLIED",
    )

    results = comment_service.list_for_entity(db_session, entity_id, ORG_1)

    assert {c.id for c in results} == {old_version_comment.id, new_version_comment.id}


def test_list_comments_survives_workflow_version_change(
    db_session, comment_service, comments_manager, clean_comments_table
) -> None:
    """Same scenario through the full manager path (authorization + visibility
    filtering included) — the API response an entity's comments tab actually
    receives must not lose history when the entity's workflow_id changes."""
    entity_id = "entity-repointed-2"

    _seed_comment(
        comment_service,
        db_session,
        entity_id=entity_id,
        text="Comment from the old workflow version",
        workflow_id="wf-version-old",
    )
    _seed_comment(
        comment_service,
        db_session,
        entity_id=entity_id,
        text="Comment from the new workflow version",
        workflow_id="wf-version-new",
    )

    result = comments_manager.list_comments(db_session, _actor(), entity_id)

    assert result.total == 2
    assert {c.text for c in result.comments} == {
        "Comment from the old workflow version",
        "Comment from the new workflow version",
    }


FIXED_ACTOR = {"user_id": "admin-user", "organization_id": ORG_1, "roles": ["admin"]}


def _fixed_actor_dependency() -> dict[str, object]:
    return FIXED_ACTOR


@pytest.fixture
def comments_client(monkeypatch):
    """Real FastAPI app around CommentsRestController with the manager mocked
    out and permission checks stubbed — isolates the controller's
    request/response wiring from persistence and RBAC, mirroring the pattern
    used in test_bulk_import_controller.py."""
    monkeypatch.setattr(
        comments_controller_module,
        "CommentReadActor",
        Annotated[dict, Depends(_fixed_actor_dependency)],
    )

    manager = MagicMock()
    controller = comments_controller_module.CommentsRestController(
        comments_service_manager=manager,
        database_service_manager=None,
        auth_service_manager=None,
    )
    router = APIRouter()
    controller.prepare(router)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: MagicMock()
    return TestClient(app), manager


@pytest.fixture
def seeded_entity(entities_db_service_manager, db_session, clean_entities_tables):
    """Insert one minimal User + EntityType + EntityRecord row so
    `CommentsServiceManager.create_comment`'s `resolve_context` call (which
    queries real user/entity/entity_type rows, and `comments.author_id` has
    a real FK to `users.id`) has something to resolve — unlike the
    workflow-visibility tests above, mention persistence goes through the
    full manager path, not just `CommentModelService.create` directly."""
    from uuid import uuid4

    from entities.db_models import EntityRecordModel, EntityTypeModel
    from user.db_models import User

    entity_type_id = str(uuid4())
    entity_id = str(uuid4())
    db_session.add(
        User(id="admin-user", email="admin-user@test.local", full_name="Admin User")
    )
    db_session.add(
        EntityTypeModel(entity_type_id=entity_type_id, organization_id=ORG_1, name="Candidate")
    )
    # Flush before adding the entity row — entities.entity_type_id has no
    # ORM-level ForeignKey() (plain Column), so SQLAlchemy can't infer the
    # insert order on its own; force it explicitly to satisfy the DB-level FKs.
    db_session.flush()
    db_session.add(
        EntityRecordModel(
            entity_id=entity_id,
            organization_id=ORG_1,
            entity_type_id=entity_type_id,
            data={"identifier": "Test Candidate"},
        )
    )
    db_session.commit()
    yield entity_id
    db_session.query(User).filter(User.id == "admin-user").delete()
    db_session.commit()


def test_create_comment_persists_parsed_mentions(
    db_session, comment_service, comments_manager, clean_comments_table, seeded_entity
) -> None:
    """Bug: `create_comment` parses `@[Name](id)` mentions (for notifications)
    but never passed the parsed list to `CommentModelService.create`, so the
    stored `mentions` column was always `[]` regardless of the comment text —
    confirmed empirically against real rows created before this fix, which
    all show `mentions=[]` despite correctly-formatted mention syntax."""
    from comments.models.request import CommentCreateRequest

    response = comments_manager.create_comment(
        db_session,
        _actor(),
        seeded_entity,
        CommentCreateRequest(text="@[Bob](user-bob) can you take a look?"),
    )

    assert response.mentions == [{"user_id": "user-bob", "full_name": "Bob", "position": 0}]

    # Re-fetch from the DB directly (not just the in-memory response) to
    # prove it was actually persisted, not merely echoed back.
    stored = comment_service.get(db_session, response.id, ORG_1)
    assert stored.mentions == [{"user_id": "user-bob", "full_name": "Bob", "position": 0}]


def test_update_comment_persists_parsed_mentions(
    db_session, comment_service, comments_manager, clean_comments_table, seeded_entity
) -> None:
    """Same bug, on the edit path: `update_comment` also parses mentions but
    must pass them through to `CommentModelService.update_text` for an edit
    that adds/changes a mention to actually update the stored column."""
    from comments.models.request import CommentCreateRequest, CommentUpdateRequest

    created = comments_manager.create_comment(
        db_session, _actor(), seeded_entity, CommentCreateRequest(text="no mentions yet")
    )

    updated = comments_manager.update_comment(
        db_session,
        _actor(),
        created.id,
        CommentUpdateRequest(text="@[Alice](user-alice) now tagging you"),
    )

    assert updated.mentions == [{"user_id": "user-alice", "full_name": "Alice", "position": 0}]
    stored = comment_service.get(db_session, created.id, ORG_1)
    assert stored.mentions == [{"user_id": "user-alice", "full_name": "Alice", "position": 0}]


def test_list_comments_excludes_replies_but_counts_them(
    db_session, comment_service, comments_manager, clean_comments_table, seeded_entity
) -> None:
    """Replies must not come back with the main comments list (kept light —
    reply_count is a cheap column-only aggregate, not the full reply body)
    and must be fetchable on demand via list_replies."""
    from comments.models.request import CommentCreateRequest, CommentReplyRequest

    parent = comments_manager.create_comment(
        db_session, _actor(), seeded_entity, CommentCreateRequest(text="top-level comment")
    )
    comments_manager.reply_to_comment(
        db_session, _actor(), parent.id, CommentReplyRequest(text="a reply")
    )

    listing = comments_manager.list_comments(db_session, _actor(), seeded_entity)
    assert [c.id for c in listing.comments] == [parent.id]
    assert listing.comments[0].reply_count == 1

    replies = comments_manager.list_replies(db_session, _actor(), parent.id)
    assert replies.total == 1
    assert replies.comments[0].text == "a reply"
    assert replies.comments[0].parent_id == parent.id


def _viewer_actor(org: str = ORG_1) -> dict[str, object]:
    """An actor with no role that grants access to role_restricted content."""
    return {"user_id": "viewer-user", "organization_id": org, "roles": ["viewer"]}


def test_toggle_like_rejects_comment_actor_cannot_see(
    db_session, comment_service, comments_manager, clean_comments_table, seeded_entity
) -> None:
    """A role-restricted comment the actor's roles don't grant access to must
    behave as not-found for liking too, not just for listing — otherwise
    toggle_like leaks the restricted comment's existence and full content."""
    from comments.models.request import CommentCreateRequest
    from exceptions import NotFoundError

    restricted = comments_manager.create_comment(
        db_session,
        _actor(),
        seeded_entity,
        CommentCreateRequest(
            text="admins only", visibility="role_restricted", visible_to_roles=["admin"]
        ),
    )

    with pytest.raises(NotFoundError):
        comments_manager.toggle_like(db_session, _viewer_actor(), restricted.id)


def test_list_replies_returns_empty_for_archived_parent(
    db_session, comment_service, comments_manager, clean_comments_table, seeded_entity
) -> None:
    """Replies of an archived (soft-deleted) parent must not remain fetchable
    via the direct replies endpoint — the thread is gone."""
    from comments.models.request import CommentCreateRequest, CommentReplyRequest

    parent = comments_manager.create_comment(
        db_session, _actor(), seeded_entity, CommentCreateRequest(text="will be archived")
    )
    comments_manager.reply_to_comment(
        db_session, _actor(), parent.id, CommentReplyRequest(text="a reply")
    )
    comments_manager.archive_comment(db_session, _actor(), parent.id)

    replies = comments_manager.list_replies(db_session, _actor(), parent.id)
    assert replies.total == 0


def test_list_replies_returns_empty_for_role_restricted_parent_actor_cant_see(
    db_session, comment_service, comments_manager, clean_comments_table, seeded_entity
) -> None:
    """A viewer without the required role must not be able to fetch a
    role-restricted parent's replies at all — defense in depth alongside
    create_comment's visibility-inheritance enforcement, for any reply that
    ends up with looser visibility than its parent regardless of how."""
    from comments.models.request import CommentCreateRequest

    parent = comments_manager.create_comment(
        db_session,
        _actor(),
        seeded_entity,
        CommentCreateRequest(
            text="restricted parent", visibility="role_restricted", visible_to_roles=["admin"]
        ),
    )
    # Simulate a mismatched reply (e.g. from data written before this
    # invariant existed) via the db layer directly, bypassing create_comment's
    # own enforcement — list_replies must still not leak it.
    comment_service.create(
        db_session,
        organization_id=ORG_1,
        entity_id=seeded_entity,
        entity_type="Candidate",
        text="a looser-visibility reply",
        author_id=None,
        author_name="Someone",
        visibility="all",
        parent_id=parent.id,
    )

    replies = comments_manager.list_replies(db_session, _viewer_actor(), parent.id)
    assert replies.total == 0


def test_list_comments_and_list_replies_accept_system_actor(
    db_session, comment_service, comments_manager, clean_comments_table, seeded_entity
) -> None:
    """A system actor (background job/scheduler/agent, user_id=None) must be
    able to list comments and replies — only liked_by_me depends on user_id,
    which should degrade to False rather than hard-failing the whole call."""
    from common.auth import build_system_actor
    from comments.models.request import CommentCreateRequest, CommentReplyRequest

    parent = comments_manager.create_comment(
        db_session, _actor(), seeded_entity, CommentCreateRequest(text="top-level comment")
    )
    comments_manager.reply_to_comment(
        db_session, _actor(), parent.id, CommentReplyRequest(text="a reply")
    )

    system_actor = build_system_actor(ORG_1)
    listing = comments_manager.list_comments(db_session, system_actor, seeded_entity)
    assert [c.id for c in listing.comments] == [parent.id]
    assert listing.comments[0].liked_by_me is False

    replies = comments_manager.list_replies(db_session, system_actor, parent.id)
    assert replies.total == 1
    assert replies.comments[0].liked_by_me is False


def test_reply_to_comment_with_stale_workflow_snapshot_succeeds(
    db_session, comment_service, comments_manager, clean_comments_table, seeded_entity
) -> None:
    """A comment's workflow_id is a creation-time snapshot — an entity can
    move to a different workflow (or unenroll) after a comment is written.
    Replying to that old comment must not re-validate CURRENT enrollment
    against the stale snapshot, or it would 400 even though a brand-new
    top-level comment on the same entity works fine."""
    from comments.models.request import CommentReplyRequest

    parent = _seed_comment(
        comment_service,
        db_session,
        entity_id=seeded_entity,
        text="left while enrolled in an old workflow",
        workflow_id="wf-no-longer-enrolled",
        state_name="APPLIED",
    )

    reply = comments_manager.reply_to_comment(
        db_session, _actor(), parent.id, CommentReplyRequest(text="a reply")
    )

    assert reply.parent_id == parent.id
    assert reply.workflow_id == "wf-no-longer-enrolled"
    assert reply.state_name == "APPLIED"


def test_create_comment_rejects_reply_visibility_mismatch(
    db_session, comment_service, comments_manager, clean_comments_table, seeded_entity
) -> None:
    """The generic create-comment endpoint also accepts parent_id — a reply
    posted through it must not be allowed to declare weaker visibility than
    its role-restricted parent."""
    from comments.models.request import CommentCreateRequest
    from exceptions import ValidationError

    parent = comments_manager.create_comment(
        db_session,
        _actor(),
        seeded_entity,
        CommentCreateRequest(
            text="restricted parent", visibility="role_restricted", visible_to_roles=["admin"]
        ),
    )

    with pytest.raises(ValidationError):
        comments_manager.create_comment(
            db_session,
            _actor(),
            seeded_entity,
            CommentCreateRequest(text="sneaky reply", parent_id=parent.id, visibility="all"),
        )


def test_notify_assignee_of_comment_reply_links_at_parent_with_reply_id(
    db_session, comment_service, clean_comments_table, seeded_entity
) -> None:
    """Regression: _notify_assignee_of_comment used to build its link from
    the raw comment_id even when the comment was a reply — since replies are
    lazy-loaded, that link had nothing to scroll to until the parent's own
    thread was expanded. It must link at the parent (with reply_id set),
    same as _notify_reply_to_comment_author / _notify_like_of_comment."""
    notifications_manager = MagicMock()
    mgr = CommentsServiceManager(
        comment_model_service=comment_service,
        database_service_manager=None,
        config=None,
        notifications_manager=notifications_manager,
    )
    mgr.start()

    parent = _seed_comment(
        comment_service, db_session, entity_id=seeded_entity, text="parent", workflow_id="wf-1"
    )
    reply = _seed_comment(
        comment_service, db_session, entity_id=seeded_entity, text="a reply", workflow_id="wf-1"
    )

    mgr._notify_assignee_of_comment(
        db_session,
        organization_id=ORG_1,
        entity_id=seeded_entity,
        entity_type="ATS.Candidate",
        entity_label="Some Candidate",
        assignee_id="assignee-user",
        comment_id=reply.id,
        comment_text="a reply",
        actor_id="actor-user",
        actor_name="Actor",
        already_notified_user_ids=set(),
        workflow_id="wf-1",
        parent_id=parent.id,
    )

    notifications_manager.create_comment_notification.assert_called_once()
    link = notifications_manager.create_comment_notification.call_args.kwargs["link"]
    assert f"comment={parent.id}" in link
    assert f"reply={reply.id}" in link


def test_replace_mention_notifications_reply_links_at_parent_with_reply_id(
    db_session, comment_service, clean_comments_table, seeded_entity
) -> None:
    """Same bug, second call site: someone @mentioned inside a reply's text
    must get a link that points at the parent (with reply_id set), not the
    reply's own unreachable id."""
    notifications_manager = MagicMock()
    mgr = CommentsServiceManager(
        comment_model_service=comment_service,
        database_service_manager=None,
        config=None,
        notifications_manager=notifications_manager,
    )
    mgr.start()

    parent = _seed_comment(
        comment_service, db_session, entity_id=seeded_entity, text="parent", workflow_id="wf-1"
    )
    reply = _seed_comment(
        comment_service,
        db_session,
        entity_id=seeded_entity,
        text="@[Bob](bob-id) hey",
        workflow_id="wf-1",
    )

    mgr._replace_mention_notifications(
        db_session,
        comment_service,
        organization_id=ORG_1,
        entity_id=seeded_entity,
        entity_type="ATS.Candidate",
        entity_label="Some Candidate",
        comment_id=reply.id,
        comment_text="@[Bob](bob-id) hey",
        actor_id="actor-user",
        actor_name="Actor",
        mentions=[{"user_id": "bob-id", "full_name": "Bob", "position": 0}],
        workflow_id="wf-1",
        parent_id=parent.id,
    )

    notifications_manager.create_mention_notification.assert_called_once()
    link = notifications_manager.create_mention_notification.call_args.kwargs["link"]
    assert f"comment={parent.id}" in link
    assert f"reply={reply.id}" in link


def test_reply_to_comment_rejects_role_restricted_parent_actor_cant_see(
    db_session, comment_service, comments_manager, clean_comments_table, seeded_entity
) -> None:
    """Regression: reply_to_comment never checked the actor's own visibility
    into the parent before replying (unlike toggle_like/list_replies, which
    both do) — a viewer with generic comment-write permission could reply
    into (and thereby confirm the existence of) an admin-only thread."""
    from comments.models.request import CommentCreateRequest, CommentReplyRequest
    from exceptions import NotFoundError

    admin_only_parent = comments_manager.create_comment(
        db_session,
        _actor(),
        seeded_entity,
        CommentCreateRequest(
            text="restricted parent", visibility="role_restricted", visible_to_roles=["admin"]
        ),
    )

    viewer = {"user_id": "viewer-user", "organization_id": ORG_1, "roles": ["viewer"]}
    with pytest.raises(NotFoundError):
        comments_manager.reply_to_comment(
            db_session, viewer, admin_only_parent.id, CommentReplyRequest(text="sneaky reply")
        )


def test_list_comments_endpoint_no_longer_accepts_workflow_id(comments_client) -> None:
    """The list endpoint's `workflow_id` query parameter was removed as part of
    the visibility fix. A client still sending it (e.g. a cached frontend
    bundle) must not error, and the value must not reach the manager —
    otherwise the old scoping bug could silently come back through the API
    contract even though the manager/db_models signatures were cleaned up."""
    client, manager = comments_client
    manager.list_comments.return_value = CommentListResponse(comments=[], total=0)

    response = client.get(
        "/entities/entity-1/comments",
        params={"workflow_id": "some-stale-workflow-id", "state_name": "APPLIED"},
    )

    assert response.status_code == 200
    manager.list_comments.assert_called_once_with(
        ANY, FIXED_ACTOR, "entity-1", state_name="APPLIED", include_archived=False
    )


def test_edit_and_delete_are_both_strictly_author_only(
    db_session, comment_service, comments_manager, clean_comments_table, seeded_entity
) -> None:
    """Edit and delete must enforce the same rule — only the original author,
    no admin/owner/superadmin override for either one. (Edit used to allow
    an admin override; removed for consistency with delete, which never had
    one.)"""
    from comments.models.request import CommentCreateRequest, CommentUpdateRequest
    from exceptions import AuthorizationError

    # _actor() ("admin-user") is the only user row seeded_entity actually
    # creates — the FK on comments.author_id needs a real row, so the
    # author has to be that one; the other actor never gets inserted
    # anywhere, so it doesn't need to be a real user.
    author = _actor()
    other_admin = {"user_id": "other-admin-user", "organization_id": ORG_1, "roles": ["admin"]}

    comment = comments_manager.create_comment(
        db_session, author, seeded_entity, CommentCreateRequest(text="mine")
    )

    with pytest.raises(AuthorizationError):
        comments_manager.update_comment(
            db_session, other_admin, comment.id, CommentUpdateRequest(text="edited by someone else")
        )

    with pytest.raises(AuthorizationError):
        comments_manager.archive_comment(db_session, other_admin, comment.id)

    # The author themself can still do both.
    comments_manager.update_comment(
        db_session, author, comment.id, CommentUpdateRequest(text="edited by the author")
    )
    comments_manager.archive_comment(db_session, author, comment.id)


def test_reply_create_and_archive_emit_reply_specific_audit_events(
    db_session, comment_service, clean_comments_table, seeded_entity
) -> None:
    """A reply must not be indistinguishable from a top-level comment in the
    audit log — it gets its own REPLY_CREATED/REPLY_ARCHIVED event types
    (instead of COMMENT_CREATED/COMMENT_ARCHIVED), and every emitted event
    carries parent_id so a reader never has to join back to `comments` just
    to tell top-level activity apart from reply activity."""
    from comments.models.request import CommentCreateRequest, CommentReplyRequest

    audit_events_service = MagicMock()
    mgr = CommentsServiceManager(
        comment_model_service=comment_service,
        database_service_manager=None,
        config=None,
        audit_events_service=audit_events_service,
    )
    mgr.start()

    parent = mgr.create_comment(
        db_session, _actor(), seeded_entity, CommentCreateRequest(text="top level")
    )
    assert audit_events_service.emit_audit_event.call_args.kwargs["event_type"] == "COMMENT_CREATED"
    assert audit_events_service.emit_audit_event.call_args.kwargs["event_metadata"]["parent_id"] is None

    reply = mgr.reply_to_comment(
        db_session, _actor(), parent.id, CommentReplyRequest(text="a reply")
    )
    assert audit_events_service.emit_audit_event.call_args.kwargs["event_type"] == "REPLY_CREATED"
    assert audit_events_service.emit_audit_event.call_args.kwargs["event_metadata"]["parent_id"] == parent.id

    mgr.archive_comment(db_session, _actor(), reply.id)
    assert audit_events_service.emit_audit_event.call_args.kwargs["event_type"] == "REPLY_ARCHIVED"
    assert audit_events_service.emit_audit_event.call_args.kwargs["event_metadata"]["parent_id"] == parent.id

    mgr.archive_comment(db_session, _actor(), parent.id)
    assert audit_events_service.emit_audit_event.call_args.kwargs["event_type"] == "COMMENT_ARCHIVED"
    assert audit_events_service.emit_audit_event.call_args.kwargs["event_metadata"]["parent_id"] is None


def test_toggle_like_emits_liked_and_unliked_audit_events(
    db_session, comment_service, clean_comments_table, seeded_entity
) -> None:
    """Unlike the notification path (which only fires on like), the audit
    trail must record both transitions — an unlike is a real event even
    though nobody gets notified about it."""
    from comments.models.request import CommentCreateRequest

    audit_events_service = MagicMock()
    mgr = CommentsServiceManager(
        comment_model_service=comment_service,
        database_service_manager=None,
        config=None,
        audit_events_service=audit_events_service,
    )
    mgr.start()

    comment = mgr.create_comment(
        db_session, _actor(), seeded_entity, CommentCreateRequest(text="like me")
    )
    audit_events_service.emit_audit_event.reset_mock()

    liker = {"user_id": "liker-user", "organization_id": ORG_1, "roles": ["admin"]}

    mgr.toggle_like(db_session, liker, comment.id)
    assert audit_events_service.emit_audit_event.call_args.kwargs["event_type"] == "COMMENT_LIKED"

    mgr.toggle_like(db_session, liker, comment.id)
    assert audit_events_service.emit_audit_event.call_args.kwargs["event_type"] == "COMMENT_UNLIKED"
