"""Direct tests for the comments module's agent-facing session handling.

The tools tests reach these through a stub. That is how the old
add_stage_comment shipped broken - the stub had a method the real manager
never did - so these exercise the real classes instead.
"""

from __future__ import annotations

from types import SimpleNamespace as NS

import pytest

from comments.db_models import CommentModelService
from comments.manager import CommentsServiceManager
from comments.models.request import CommentCreateRequest
from exceptions import ServiceError


class _RecordingSession:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


def _model_service(session: _RecordingSession) -> CommentModelService:
    return CommentModelService(
        NS(postgres_db_service=lambda: NS(get_db_session=lambda: session))
    )


def test_session_scope_commits_and_closes_on_success() -> None:
    session = _RecordingSession()

    with _model_service(session).session_scope() as db:
        assert db is session

    assert session.committed is True
    assert session.rolled_back is False
    assert session.closed is True


def test_session_scope_rolls_back_and_reraises_on_failure() -> None:
    """A half-written comment must not be committed."""
    session = _RecordingSession()

    with pytest.raises(ValueError, match="boom"), _model_service(session).session_scope():
        raise ValueError("boom")

    assert session.committed is False
    assert session.rolled_back is True
    assert session.closed is True


def test_session_scope_without_a_database_manager_is_an_error() -> None:
    with pytest.raises(ServiceError), CommentModelService(None).session_scope():
        pass


def _manager(session: _RecordingSession) -> CommentsServiceManager:
    return CommentsServiceManager(_model_service(session), None, None)


def test_list_comments_for_agent_delegates_with_a_session(monkeypatch) -> None:
    """Catches a rename or signature drift the tools stub would not."""
    session = _RecordingSession()
    manager = _manager(session)
    seen: dict = {}

    monkeypatch.setattr(
        CommentsServiceManager,
        "list_comments",
        lambda self, db, actor, entity_id, **kw: seen.update(
            db=db, actor=actor, entity_id=entity_id, kw=kw
        ),
    )

    manager.list_comments_for_agent({"organization_id": "org-1"}, "e-1", state_name="Screening")

    assert seen["db"] is session
    assert seen["entity_id"] == "e-1"
    assert seen["kw"] == {"state_name": "Screening"}
    assert session.closed is True


def test_create_comment_for_agent_delegates_and_commits(monkeypatch) -> None:
    session = _RecordingSession()
    manager = _manager(session)
    seen: dict = {}

    monkeypatch.setattr(
        CommentsServiceManager,
        "create_comment",
        lambda self, db, actor, entity_id, request: seen.update(
            db=db, entity_id=entity_id, text=request.text
        ),
    )

    manager.create_comment_for_agent(
        {"organization_id": "org-1"}, "e-1", CommentCreateRequest(text="hello")
    )

    assert seen["db"] is session
    assert seen["text"] == "hello"
    assert session.committed is True
    assert session.closed is True
