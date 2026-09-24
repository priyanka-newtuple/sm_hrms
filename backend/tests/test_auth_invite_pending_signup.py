"""Signing up while an invitation is still waiting must say so, not 'already registered'."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from auth import manager as auth_manager
from auth.manager import AuthServiceManager
from auth.models.interface import INVITE_PENDING_MESSAGE
from exceptions import ConflictError
from user.models.request import UserCreate


def _payload() -> UserCreate:
    return UserCreate(
        email="invited@example.com", password="hunter2hunter2", full_name="Invited User"
    )


def _manager(monkeypatch, *, invitation=None, existing_user=None) -> AuthServiceManager:
    monkeypatch.setattr(
        auth_manager.AuthDBOperations, "find_pending_invitation", lambda db, email: invitation
    )
    monkeypatch.setattr(
        auth_manager,
        "AuthService",
        lambda *a, **k: SimpleNamespace(get_user_by_email=lambda email: existing_user),
    )
    manager = AuthServiceManager.__new__(AuthServiceManager)
    manager.config = None
    manager.roles_db_service = None
    manager.audit_events_service = None
    return manager


def test_pending_invite_blocks_signup(monkeypatch) -> None:
    manager = _manager(monkeypatch, invitation=SimpleNamespace(token="tok-123"))

    with pytest.raises(ConflictError, match=INVITE_PENDING_MESSAGE):
        manager.register(_payload(), db=None)


def test_pending_invite_wins_over_already_registered(monkeypatch) -> None:
    """A half-created account must still report the invite, not 'already registered'."""
    manager = _manager(
        monkeypatch,
        invitation=SimpleNamespace(token="tok-123"),
        existing_user=SimpleNamespace(id="u-1", email="invited@example.com"),
    )

    with pytest.raises(ConflictError, match=INVITE_PENDING_MESSAGE):
        manager.register(_payload(), db=None)


def test_no_invite_and_existing_user_still_reports_registered(monkeypatch) -> None:
    manager = _manager(
        monkeypatch, existing_user=SimpleNamespace(id="u-1", email="invited@example.com")
    )

    with pytest.raises(ConflictError, match="Email already registered"):
        manager.register(_payload(), db=None)


def test_validate_reports_whether_the_account_exists() -> None:
    """The accept page hides the name/password fields on this flag."""
    from datetime import UTC, datetime, timedelta
    from types import SimpleNamespace as NS

    from invitation.db_models import InvitationStatus
    from invitation.manager import InvitationServiceManager

    invitation = NS(
        email="Existing@Example.com",
        role="viewer",
        status=InvitationStatus.PENDING.value,
        organization_id="org-1",
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )

    def _manager(user):
        db_service = NS(
            get_by_token=lambda db, token: invitation,
            get_organization=lambda db, org_id: NS(name="Second Org"),
            get_user_by_email=lambda db, email: user,
        )
        return InvitationServiceManager(db_service)

    assert _manager(NS(id="u-1")).validate_token(None, "tok").user_exists is True
    assert _manager(None).validate_token(None, "tok").user_exists is False


def test_expired_or_revoked_invite_falls_through_to_normal_registration(monkeypatch) -> None:
    """find_pending_invitation filters those out, so sign-up proceeds as usual."""
    from auth.db_models import ApprovalType, UserCreationResult
    from auth.models.response import TokenResponse

    user = SimpleNamespace(
        id="u-1",
        email="invited@example.com",
        full_name="Invited User",
        avatar_url=None,
        role="viewer",
        status="active",
        auth_type="local",
        organization_id="org-new",
    )

    monkeypatch.setattr(
        auth_manager.AuthDBOperations, "find_pending_invitation", lambda db, email: None
    )
    monkeypatch.setattr(
        auth_manager,
        "AuthService",
        lambda *a, **k: SimpleNamespace(
            get_user_by_email=lambda email: None,
            create_local_user=lambda **kw: UserCreationResult(
                user=user,
                organization=SimpleNamespace(id="org-new", name="New Co"),
                is_new_org=True,
                approval_type=ApprovalType.ACTIVE,
            ),
            log_auth_event=lambda **kw: None,
            create_tokens=lambda u: ("access", "refresh"),
            update_last_login=lambda u: None,
        ),
    )

    manager = AuthServiceManager.__new__(AuthServiceManager)
    manager.config = None
    manager.roles_db_service = None
    manager.audit_events_service = None

    response, code = manager.register(_payload(), db=None)

    assert code == 201
    assert isinstance(response, TokenResponse)
