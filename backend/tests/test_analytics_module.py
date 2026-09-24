"""Real-Postgres coverage for the analytics module.

Seeds unified ``audit_events`` rows (with explicit timestamps) plus real
``users`` rows, then exercises the actual SQL aggregations through
``AnalyticsModelService`` / ``AnalyticsServiceManager``. Uses the
``entities_db_service_manager`` fixture (see conftest.py) — no ORM mocking.
Only the RBAC permission gate uses a deterministic test double, mirroring
tests/test_unified_audit_events.py.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from analytics.controller import AnalyticsRestController
from analytics.db_models import AnalyticsModelService
from analytics.manager import AnalyticsServiceManager
from analytics.models.interface import AnalyticsGroupBy
from analytics.models.request import AnalyticsFlexibleRequest
from audit.db_models import AuditEventModel, AuditEventsModelService
from common.auth import register_roles_db_service
from common.deps import get_db
from common.enums import AuditMetadataType
from exceptions import ValidationError
from tests.conftest import ENTITIES_TEST_ORG_IDS
from user.db_models import User, UserModelService

ORG_A = ENTITIES_TEST_ORG_IDS[0]
ORG_B = ENTITIES_TEST_ORG_IDS[1]

USER_ALICE = "analytics-test-user-alice"
USER_BOB = "analytics-test-user-bob"
TEST_USER_IDS = (USER_ALICE, USER_BOB)

# Fixed, in-range timestamps so day/week bucket assertions are deterministic.
# 2026-07-01 is a Wednesday; its ISO week starts Monday 2026-06-29.
JUL_1 = datetime(2026, 7, 1, 9, 0, tzinfo=UTC)
JUL_2 = datetime(2026, 7, 2, 11, 0, tzinfo=UTC)
JUN_20 = datetime(2026, 6, 20, 8, 0, tzinfo=UTC)
RANGE_FROM = date(2026, 7, 1)
RANGE_TO = date(2026, 7, 7)


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def clean_analytics_data(entities_db_service_manager):
    """Delete test-org audit_events and analytics test users around each test."""
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "modular_backend")
    audit_schema = f"{app_schema}_audit"
    engine = entities_db_service_manager.postgres_db_service().engine

    def _cleanup() -> None:
        with engine.begin() as conn:
            conn.execute(
                text(
                    f'DELETE FROM "{audit_schema}".audit_events WHERE organization_id = ANY(:ids)'
                ),
                {"ids": list(ENTITIES_TEST_ORG_IDS)},
            )
            conn.execute(
                text(f'DELETE FROM "{app_schema}".users WHERE id = ANY(:ids)'),
                {"ids": list(TEST_USER_IDS)},
            )

    _cleanup()
    yield
    _cleanup()


@pytest.fixture
def analytics_db(entities_db_service_manager) -> AnalyticsModelService:
    return AnalyticsModelService(entities_db_service_manager)


@pytest.fixture
def user_service(entities_db_service_manager) -> UserModelService:
    return UserModelService(entities_db_service_manager)


@pytest.fixture
def audit_events_service(entities_db_service_manager) -> AuditEventsModelService:
    return AuditEventsModelService(entities_db_service_manager)


@pytest.fixture
def manager(analytics_db, user_service, audit_events_service) -> AnalyticsServiceManager:
    return AnalyticsServiceManager(analytics_db, user_service, audit_events_service)


@pytest.fixture
def db(entities_db_service_manager):
    """Per-test DB session, mirroring the request-scoped session in production."""
    session = entities_db_service_manager.postgres_db_service().get_db_session()
    try:
        yield session
    finally:
        session.close()


# ── seed helpers ──────────────────────────────────────────────────────────────


def _insert_events(entities_db_service_manager, rows: list[dict]) -> None:
    """Insert audit_events rows with explicit timestamps (read-path tests own
    their fixtures; the write path is covered by test_unified_audit_events)."""
    session = entities_db_service_manager.postgres_db_service().get_db_session()
    try:
        for row in rows:
            session.add(
                AuditEventModel(
                    id=str(uuid.uuid4()),
                    organization_id=row.get("org", ORG_A),
                    metadata_type=row.get("metadata_type", AuditMetadataType.ENTITY.value),
                    event_type=row["event_type"],
                    user_id=row.get("user_id"),
                    actor_type=row.get("actor_type", "user"),
                    actor_id=row.get("actor_id"),
                    actor_name=row.get("actor_name"),
                    source="api",
                    event_timestamp=row.get("at", JUL_1),
                )
            )
        session.commit()
    finally:
        session.close()


def _login(
    user_id: str, at: datetime, org: str = ORG_A, event_type: str = "AUTH_LOGIN_SUCCESS"
) -> dict:
    """An auth row exactly as production writes it: actor is the auth service,
    the human is only in user_id."""
    return {
        "org": org,
        "metadata_type": AuditMetadataType.AUTH.value,
        "event_type": event_type,
        "user_id": user_id,
        "actor_type": "system",
        "actor_id": "auth_service",
        "at": at,
    }


def _action(user_id: str, event_type: str, at: datetime, org: str = ORG_A, **extra) -> dict:
    return {"org": org, "event_type": event_type, "user_id": user_id, "at": at, **extra}


def _seed_user(entities_db_service_manager, user_id: str, name: str, email: str) -> None:
    session = entities_db_service_manager.postgres_db_service().get_db_session()
    try:
        session.add(
            User(
                id=user_id,
                email=email,
                full_name=name,
                organization_id=ORG_A,
                role="admin",
                status="active",
            )
        )
        session.commit()
    finally:
        session.close()


# ── report queries against real Postgres ─────────────────────────────────────


def test_login_activity_counts_logins_scoped_to_org_and_range(
    entities_db_service_manager, manager, db, clean_analytics_data
) -> None:
    _insert_events(
        entities_db_service_manager,
        [
            _login(USER_ALICE, JUL_1),
            _login(USER_ALICE, JUL_2, event_type="AUTH_GOOGLE_LOGIN"),
            _login(USER_BOB, JUL_1),
            _login(USER_ALICE, JUL_1, event_type="AUTH_LOGIN_FAILED"),  # not a login
            _login(None, JUL_1),  # unattributable — excluded
            _login(USER_ALICE, JUN_20),  # outside range
            _login("other-org-user", JUL_1, org=ORG_B),  # other org
        ],
    )

    response = manager.login_activity(db, {"organization_id": ORG_A}, RANGE_FROM, RANGE_TO)

    assert response.total_logins == 3
    assert response.active_users == 2
    assert [(p.label, p.value) for p in response.daily] == [
        ("2026-07-01", 2),
        ("2026-07-02", 1),
        ("2026-07-03", 0),
        ("2026-07-04", 0),
        ("2026-07-05", 0),
        ("2026-07-06", 0),
        ("2026-07-07", 0),
    ]
    assert [(p.label, p.value) for p in response.weekly] == [
        ("2026-06-29", 3),
        ("2026-07-06", 0),
    ]


def test_action_breakdown_groups_by_type_and_excludes_auth(
    entities_db_service_manager, manager, db, clean_analytics_data
) -> None:
    _insert_events(
        entities_db_service_manager,
        [
            _action(USER_ALICE, "ENTITY_CREATED", JUL_1),
            _action(USER_ALICE, "ENTITY_CREATED", JUL_1),
            _action(USER_BOB, "ENTITY_CREATED", JUL_2),
            _action(
                USER_ALICE,
                "TRANSITION_SUCCEEDED",
                JUL_2,
                metadata_type=AuditMetadataType.TRANSITION.value,
            ),
            _action(
                USER_ALICE,
                "TRANSITION_SUCCEEDED",
                JUL_2,
                metadata_type=AuditMetadataType.TRANSITION.value,
            ),
            _login(USER_ALICE, JUL_1),  # auth — excluded from actions
            _action(USER_BOB, "ENTITY_CREATED", JUL_1, org=ORG_B),  # other org
        ],
    )

    response = manager.action_breakdown(db, {"organization_id": ORG_A}, RANGE_FROM, RANGE_TO)

    assert response.total_actions == 5
    assert [(i.action, i.category, i.count) for i in response.items] == [
        ("ENTITY_CREATED", AuditMetadataType.ENTITY.value, 3),
        ("TRANSITION_SUCCEEDED", AuditMetadataType.TRANSITION.value, 2),
    ]


def test_user_activity_aggregates_per_user_with_real_user_enrichment(
    entities_db_service_manager, manager, db, clean_analytics_data
) -> None:
    _seed_user(
        entities_db_service_manager, USER_ALICE, "Alice Admin", "alice.analytics@test.example"
    )
    _insert_events(
        entities_db_service_manager,
        [
            _login(USER_ALICE, JUL_1),
            _login(USER_ALICE, JUL_2),
            _action(USER_ALICE, "ENTITY_CREATED", JUL_1),
            _action(USER_ALICE, "ENTITY_CREATED", JUL_1),
            _action(USER_ALICE, "COMMENT_CREATED", JUL_2),
            # Bob has no users row — name falls back to the recorded actor_name.
            _action(USER_BOB, "ENTITY_UPDATED", JUL_1, actor_name="Bob Gone"),
        ],
    )

    response = manager.user_activity(db, {"organization_id": ORG_A}, RANGE_FROM, RANGE_TO)

    assert response.total == 2
    assert response.limit == 25
    assert response.offset == 0
    assert [item.user_id for item in response.items] == [USER_ALICE, USER_BOB]

    alice = response.items[0]
    assert alice.name == "Alice Admin"
    assert alice.email == "alice.analytics@test.example"
    assert alice.login_count == 2
    assert alice.last_login_at == JUL_2
    assert alice.total_actions == 3
    assert [(a.action, a.count) for a in alice.actions] == [
        ("ENTITY_CREATED", 2),
        ("COMMENT_CREATED", 1),
    ]

    bob = response.items[1]
    assert bob.name == "Bob Gone"
    assert bob.email is None
    assert bob.login_count == 0
    assert bob.last_login_at is None
    assert bob.total_actions == 1


def test_login_only_user_is_a_person_not_system(
    entities_db_service_manager, manager, db, clean_analytics_data
) -> None:
    """Auth rows carry actor_type='system' (written by the auth service), so a
    user whose only activity is logging in must still surface as a person."""
    _seed_user(
        entities_db_service_manager, USER_ALICE, "Alice Admin", "alice.analytics@test.example"
    )
    _insert_events(
        entities_db_service_manager,
        [_login(USER_ALICE, JUL_1), _login(USER_ALICE, JUL_2)],
    )

    response = manager.user_activity(db, {"organization_id": ORG_A}, RANGE_FROM, RANGE_TO)

    alice = response.items[0]
    assert alice.actor_type == "user"
    assert alice.name == "Alice Admin"
    assert alice.login_count == 2
    assert alice.total_actions == 0


def test_flexible_report_groups_by_day_and_action(
    entities_db_service_manager, manager, db, clean_analytics_data
) -> None:
    _insert_events(
        entities_db_service_manager,
        [
            _action(USER_ALICE, "ENTITY_CREATED", JUL_1),
            _action(USER_ALICE, "ENTITY_CREATED", JUL_1),
            _action(USER_BOB, "COMMENT_CREATED", JUL_2),
            _login(USER_ALICE, JUL_1),  # excluded: include_auth=False
        ],
    )
    request = AnalyticsFlexibleRequest(
        date_from=RANGE_FROM,
        date_to=RANGE_TO,
        group_by=[AnalyticsGroupBy.DAY, AnalyticsGroupBy.ACTION],
    )

    response = manager.flexible(db, {"organization_id": ORG_A}, request)

    assert [column.key for column in response.columns] == ["day", "action", "count"]
    assert response.rows == [
        {"day": "2026-07-01", "action": "ENTITY_CREATED", "count": 2},
        {"day": "2026-07-02", "action": "COMMENT_CREATED", "count": 1},
    ]


def test_flexible_report_by_user_includes_auth_and_enriches_names(
    entities_db_service_manager, manager, db, clean_analytics_data
) -> None:
    _seed_user(
        entities_db_service_manager, USER_ALICE, "Alice Admin", "alice.analytics@test.example"
    )
    _insert_events(
        entities_db_service_manager,
        [
            _login(USER_ALICE, JUL_1),
            _action(USER_ALICE, "ENTITY_CREATED", JUL_1),
            _action(USER_BOB, "ENTITY_UPDATED", JUL_2),
        ],
    )
    request = AnalyticsFlexibleRequest(
        date_from=RANGE_FROM,
        date_to=RANGE_TO,
        group_by=[AnalyticsGroupBy.USER],
        include_auth=True,
    )

    response = manager.flexible(db, {"organization_id": ORG_A}, request)

    by_user = {row["user"]: row["count"] for row in response.rows}
    assert by_user == {"Alice Admin": 2, f"Deleted user ({USER_BOB})": 1}


def test_flexible_report_returns_requested_page_and_total(
    entities_db_service_manager, manager, db, clean_analytics_data
) -> None:
    _insert_events(
        entities_db_service_manager,
        [
            _action(USER_ALICE, "ACTION_A", JUL_1),
            _action(USER_ALICE, "ACTION_B", JUL_1),
            _action(USER_ALICE, "ACTION_C", JUL_1),
        ],
    )
    request = AnalyticsFlexibleRequest(
        date_from=RANGE_FROM,
        date_to=RANGE_TO,
        group_by=[AnalyticsGroupBy.ACTION],
        limit=2,
        offset=1,
    )

    response = manager.flexible(db, {"organization_id": ORG_A}, request)

    assert response.total == 3
    assert response.limit == 2
    assert response.offset == 1
    assert response.rows == [
        {"action": "ACTION_B", "count": 1},
        {"action": "ACTION_C", "count": 1},
    ]


def test_user_activity_returns_requested_page_and_total(
    entities_db_service_manager, manager, db, clean_analytics_data
) -> None:
    _insert_events(
        entities_db_service_manager,
        [
            _action(USER_ALICE, "ACTION_A", JUL_1),
            _action(USER_ALICE, "ACTION_B", JUL_1),
            _action(USER_BOB, "ACTION_C", JUL_1),
        ],
    )

    response = manager.user_activity(
        db,
        {"organization_id": ORG_A},
        RANGE_FROM,
        RANGE_TO,
        limit=1,
        offset=1,
    )

    assert response.total == 2
    assert response.limit == 1
    assert response.offset == 1
    assert [item.user_id for item in response.items] == [USER_BOB]


# ── range validation (manager logic, real services wired) ────────────────────


def test_default_range_is_last_30_days(manager, db, clean_analytics_data) -> None:
    response = manager.login_activity(db, {"organization_id": ORG_A}, None, None)

    assert (response.date_to - response.date_from).days == 29
    assert response.total_logins == 0
    assert response.active_users == 0


def test_range_longer_than_one_year_is_allowed(manager, db, clean_analytics_data) -> None:
    response = manager.action_breakdown(
        db, {"organization_id": ORG_A}, date(2024, 1, 1), date(2025, 12, 31)
    )

    assert response.date_from == date(2024, 1, 1)
    assert response.date_to == date(2025, 12, 31)


def test_reversed_range_is_rejected(manager) -> None:
    with pytest.raises(ValidationError, match="on or before"):
        manager.action_breakdown(None, {"organization_id": ORG_A}, date(2026, 2, 2), date(2026, 2, 1))


def test_missing_organization_is_rejected(manager) -> None:
    with pytest.raises(ValidationError, match="organization_id"):
        manager.login_activity(None, {}, None, None)


# ── HTTP permission gate (real manager + real DB behind the endpoint) ────────


class _RolesGate:
    """Deterministic permission-check double registered via the real
    `register_roles_db_service` hook (mirrors repo test practice)."""

    def __init__(self, allowed: bool) -> None:
        self.allowed = allowed

    def check_permission(self, db, user_id, organization_id, permission_key):
        _ = db, user_id, organization_id
        assert permission_key == "analytics:read"
        return SimpleNamespace(allowed=self.allowed, reason="not granted")


def _client(
    allowed: bool, manager: AnalyticsServiceManager, db_service_manager
) -> TestClient:
    register_roles_db_service(_RolesGate(allowed))
    router = APIRouter()
    AnalyticsRestController(manager).prepare(router)
    app = FastAPI()
    app.include_router(router)

    def _real_db():
        session = db_service_manager.postgres_db_service().get_db_session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _real_db
    return TestClient(app)


def test_non_admin_without_analytics_permission_is_blocked(
    manager, entities_db_service_manager
) -> None:
    try:
        response = _client(False, manager, entities_db_service_manager).get(
            "/analytics/overview",
            headers={"x-user-id": "viewer-1", "x-org-id": ORG_A, "x-user-roles": "viewer"},
        )
        assert response.status_code == 403
    finally:
        register_roles_db_service(None)


def test_permitted_actor_reads_real_report_through_endpoint(
    entities_db_service_manager, manager, clean_analytics_data
) -> None:
    _insert_events(entities_db_service_manager, [_login(USER_ALICE, JUL_1)])
    try:
        response = _client(True, manager, entities_db_service_manager).get(
            f"/analytics/overview?date_from={RANGE_FROM}&date_to={RANGE_TO}",
            headers={"x-user-id": "admin-1", "x-org-id": ORG_A, "x-user-roles": "admin"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["logins"]["total_logins"] == 1
        assert body["logins"]["active_users"] == 1
        assert body["users"]["total"] == 1
        assert body["users"]["limit"] == 25
        assert body["logins"]["daily"] == [
            {"label": "2026-07-01", "value": 1},
            {"label": "2026-07-02", "value": 0},
            {"label": "2026-07-03", "value": 0},
            {"label": "2026-07-04", "value": 0},
            {"label": "2026-07-05", "value": 0},
            {"label": "2026-07-06", "value": 0},
            {"label": "2026-07-07", "value": 0},
        ]
    finally:
        register_roles_db_service(None)
