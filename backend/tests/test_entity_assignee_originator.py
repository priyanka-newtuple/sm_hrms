"""Coverage for assigning an entity record to its originator.

Exercises `entities/manager.py::set_entity_assignee_for_actor` end to end
against real Postgres: real `audit_events` rows supply the originator, and real
`users`/`user_organizations` rows decide whether that originator is assignable.
Only the RBAC service is a double, so a test can grant or withhold entity edit
permission without building real roles.

Also covers the security fix that every assignment — self-assignment included —
requires entity edit permission.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import pytest
from fastapi import APIRouter
from sqlalchemy import text

from audit.db_models import AuditEventsModelService
from audit.manager import AuditServiceManager
from common.auth import build_system_actor
from common.protocols import EntityAccessCheck
from entities.controller import EntitiesRestController
from entities.db_models import EntitiesModelService
from entities.manager import EntitiesServiceManager
from entities.models.interface import (
    ASSIGNMENT_MODE_CONFLICT_MESSAGE,
    AssignmentRejection,
    EntityAuditEventType,
)
from entities.models.request import (
    EntityAssigneeUpdateRequest,
    EntityRecordCreateRequest,
    EntityTypeCreateRequest,
)
from exceptions import AuthorizationError, NotFoundError, ValidationError
from tests.conftest import ENTITIES_TEST_ORG_IDS
from user.db_models import UserModelService, UserStatus
from user.manager import UserServiceManager

ORG_1 = ENTITIES_TEST_ORG_IDS[0]
ORG_2 = ENTITIES_TEST_ORG_IDS[1]

ENTITY_TYPE_NAME = "Patient"


class _AlwaysAllowAuth:
    """Auth stand-in so `_resolve_identity_service` finds a `check_access` holder."""

    class _Decision:
        allowed = True
        reason = ""

    def check_access(self, _payload: dict[str, object]) -> _AlwaysAllowAuth._Decision:
        return self._Decision()


class ConfigurableRoles:
    """RBAC double whose entity edit answer a test can set.

    Only `evaluate_entity_access` decides allow/deny for `guard_write`; the
    field methods are permissive so response formatting never masks anything.
    """

    def __init__(self, *, can_edit: bool = True, can_view: bool = True) -> None:
        self.can_edit = can_edit
        self.can_view = can_view

    def evaluate_entity_access(
        self, db: Any, user_id: str, org_id: str, entity_type: str, action: str
    ) -> EntityAccessCheck:
        allowed = self.can_view if action == "view" else self.can_edit
        return EntityAccessCheck(allowed=allowed, conditions=[])

    def check_entity_permission(
        self, db: Any, user_id: str, org_id: str, entity_type: str, action: str
    ) -> bool:
        return True

    def get_visible_fields(
        self, db: Any, user_id: str, org_id: str, entity_type: str
    ) -> list[str] | None:
        return None

    def get_editable_fields(
        self, db: Any, user_id: str, org_id: str, entity_type: str
    ) -> list[str] | None:
        return None

    def get_masked_fields(
        self, db: Any, user_id: str, org_id: str, entity_type: str
    ) -> list[str]:
        return []


def _schema(suffix: str = "") -> str:
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "modular_backend")
    return f"{app_schema}_{suffix}" if suffix else app_schema


def _actor(user_id: str, organization_id: str = ORG_1) -> dict[str, object]:
    return {
        "user_id": user_id,
        "organization_id": organization_id,
        "actor_type": "user",
        "roles": ["admin"],
    }


@pytest.fixture
def engine(entities_db_service_manager):
    return entities_db_service_manager.postgres_db_service().engine


def _insert_user(
    conn: Any, user_id: str, full_name: str, status: str, primary_org: str | None
) -> None:
    """Insert one users row. `is_active` is generated from status by the DB."""
    conn.execute(
        text(
            f'INSERT INTO "{_schema()}".users '
            "(id, email, full_name, role, status, auth_type, organization_id) "
            "VALUES (:id, :email, :name, 'recruiter', :status, 'local', :org)"
        ),
        {
            "id": user_id,
            "email": f"{user_id}@example.test",
            "name": full_name,
            "status": status,
            "org": primary_org,
        },
    )


def _insert_membership(conn: Any, user_id: str, org_id: str, status: str) -> None:
    """Insert one explicit organization membership row."""
    conn.execute(
        text(
            f'INSERT INTO "{_schema()}".user_organizations '
            "(id, user_id, organization_id, role, status) "
            "VALUES (:id, :uid, :org, 'recruiter', :status)"
        ),
        {"id": str(uuid.uuid4()), "uid": user_id, "org": org_id, "status": status},
    )


@pytest.fixture
def seeded_users(engine):
    """Insert the users this suite assigns to, and remove them afterwards.

    `is_active` is deliberately not written: the column is generated from
    `status` by the database.
    """
    created: list[str] = []

    def _seed(
        *,
        full_name: str,
        status: str = UserStatus.ACTIVE.value,
        membership_status: str | None = UserStatus.ACTIVE.value,
        membership_org: str = ORG_1,
        primary_org: str | None = None,
    ) -> str:
        user_id = str(uuid.uuid4())
        created.append(user_id)
        with engine.begin() as conn:
            _insert_user(conn, user_id, full_name, status, primary_org)
            if membership_status is not None:
                _insert_membership(conn, user_id, membership_org, membership_status)
        return user_id

    yield _seed

    app_schema = _schema()
    with engine.begin() as conn:
        conn.execute(
            text(f'DELETE FROM "{app_schema}".user_organizations WHERE user_id = ANY(:ids)'),
            {"ids": created},
        )
        conn.execute(
            text(f'DELETE FROM "{app_schema}".users WHERE id = ANY(:ids)'), {"ids": created}
        )


@pytest.fixture
def clean_records(engine):
    """Clear the entity/audit rows this suite writes, before and after each test."""

    def _cleanup() -> None:
        with engine.begin() as conn:
            for table in (
                f'"{_schema("audit")}".audit_events',
                f'"{_schema("runtime")}".entity_state',
                f'"{_schema("runtime")}".entities',
                f'"{_schema("definitions")}".entity_types',
            ):
                conn.execute(
                    text(f"DELETE FROM {table} WHERE organization_id = ANY(:ids)"),
                    {"ids": list(ENTITIES_TEST_ORG_IDS)},
                )

    _cleanup()
    yield
    _cleanup()


@pytest.fixture
def make_manager(entities_db_service_manager):
    """Build an entities manager with real audit + user services."""

    def _build(*, can_edit: bool = True, can_view: bool = True) -> EntitiesServiceManager:
        manager = EntitiesServiceManager(
            EntitiesModelService(database_service_manager=entities_db_service_manager),
            database_service_manager=entities_db_service_manager,
            config=None,
            auth_service_manager=_AlwaysAllowAuth(),
            roles_manager=ConfigurableRoles(can_edit=can_edit, can_view=can_view),
            audit_service_manager=AuditServiceManager(
                AuditEventsModelService(database_service_manager=entities_db_service_manager)
            ),
            user_service_manager=UserServiceManager(
                UserModelService(entities_db_service_manager)
            ),
        )
        manager.start()
        return manager

    return _build


def _entity_type(manager: EntitiesServiceManager, organization_id: str = ORG_1) -> str:
    response = manager.create_entity_type(
        EntityTypeCreateRequest(
            organization_id=organization_id,
            name=ENTITY_TYPE_NAME,
            schema_definition={"fields": [{"name": "email", "type": "email"}]},
            version=1,
            is_active=True,
        )
    )
    return response.entity_type_id


def _record(
    manager: EntitiesServiceManager,
    actor: dict[str, object],
    entity_type_id: str,
    identifier: str,
    organization_id: str = ORG_1,
) -> Any:
    return manager.create_entity_record_for_actor(
        actor,
        EntityRecordCreateRequest(
            organization_id=organization_id,
            entity_type_id=entity_type_id,
            data={"identifier": identifier, "email": "p@example.test"},
        ),
    )


def _assignee_events(engine, organization_id: str = ORG_1) -> list[dict]:
    with engine.connect() as conn:
        rows = (
            conn.execute(
                text(
                    f'SELECT metadata, actor_id FROM "{_schema("audit")}".audit_events '
                    "WHERE organization_id = :org AND event_type = :event_type "
                    "ORDER BY event_timestamp ASC, id ASC"
                ),
                {"org": organization_id, "event_type": str(EntityAuditEventType.ASSIGNEE_CHANGED)},
            )
            .mappings()
            .all()
        )
    return [dict(row) for row in rows]


def _stored_assignee(engine, entity_id: str) -> str | None:
    with engine.connect() as conn:
        row = conn.execute(
            text(f'SELECT assignee_id FROM "{_schema("runtime")}".entities WHERE entity_id = :id'),
            {"id": entity_id},
        ).fetchone()
    return row[0] if row else None


# ── Request contract ────────────────────────────────────────────────────────


def test_supplying_both_assignee_and_originator_flag_is_rejected() -> None:
    with pytest.raises(Exception) as exc_info:
        EntityAssigneeUpdateRequest(assignee_id="someone", assign_to_originator=True)
    assert ASSIGNMENT_MODE_CONFLICT_MESSAGE in str(exc_info.value)


def test_originator_flag_alone_is_accepted() -> None:
    request = EntityAssigneeUpdateRequest(assign_to_originator=True)
    assert request.assignee_id is None
    assert request.assign_to_originator is True


def test_blank_assignee_with_originator_flag_is_accepted_as_originator_mode() -> None:
    """A blank string collapses to None, so it is not treated as a second mode."""
    request = EntityAssigneeUpdateRequest(assignee_id="   ", assign_to_originator=True)
    assert request.assignee_id is None
    assert request.assign_to_originator is True


# ── Originator resolution ───────────────────────────────────────────────────


def test_originator_assignment_writes_the_creators_user_id(
    engine, make_manager, seeded_users, clean_records
) -> None:
    manager = make_manager()
    creator_id = seeded_users(full_name="Mohit Rana")
    creator = _actor(creator_id)
    entity_type_id = _entity_type(manager)
    record = _record(manager, creator, entity_type_id, "PAT-001")

    assigner = _actor(seeded_users(full_name="Nisha Verma"))
    response = manager.set_entity_assignee_for_actor(
        assigner, record.entity_id, None, assign_to_originator=True
    )

    assert response.assignee_id == creator_id
    assert _stored_assignee(engine, record.entity_id) == creator_id


def test_originator_audit_row_records_mode_and_keeps_the_requester_as_actor(
    engine, make_manager, seeded_users, clean_records
) -> None:
    """The originator is the target; the person who asked stays the audit actor."""
    manager = make_manager()
    creator_id = seeded_users(full_name="Mohit Rana")
    entity_type_id = _entity_type(manager)
    record = _record(manager, _actor(creator_id), entity_type_id, "PAT-002")
    assigner_id = seeded_users(full_name="Nisha Verma")

    manager.set_entity_assignee_for_actor(
        _actor(assigner_id), record.entity_id, None, assign_to_originator=True
    )

    events = _assignee_events(engine)
    assert len(events) == 1
    assert events[0]["actor_id"] == assigner_id
    assert events[0]["metadata"] == {
        "previous_assignee_id": None,
        "new_assignee_id": creator_id,
        "assignment_mode": "originator",
        "assignment_source": "api",
    }


def test_repeated_originator_assignment_is_idempotent(
    engine, make_manager, seeded_users, clean_records
) -> None:
    """Second identical request: same result, no second history row."""
    manager = make_manager()
    creator_id = seeded_users(full_name="Mohit Rana")
    entity_type_id = _entity_type(manager)
    record = _record(manager, _actor(creator_id), entity_type_id, "PAT-003")
    assigner = _actor(seeded_users(full_name="Nisha Verma"))

    first = manager.set_entity_assignee_for_actor(
        assigner, record.entity_id, None, assign_to_originator=True
    )
    second = manager.set_entity_assignee_for_actor(
        assigner, record.entity_id, None, assign_to_originator=True
    )

    assert first.assignee_id == second.assignee_id == creator_id
    assert len(_assignee_events(engine)) == 1


def test_reassigning_back_to_an_earlier_holder_is_recorded(
    engine, make_manager, seeded_users, clean_records
) -> None:
    """A -> B -> A is three real changes, not a repeat; every one is history."""
    manager = make_manager()
    creator_id = seeded_users(full_name="Anish Kumar")
    other_id = seeded_users(full_name="Mohit Rana")
    entity_type_id = _entity_type(manager)
    record = _record(manager, _actor(creator_id), entity_type_id, "PAT-004")
    assigner = _actor(seeded_users(full_name="Nisha Verma"))

    manager.set_entity_assignee_for_actor(
        assigner, record.entity_id, None, assign_to_originator=True
    )
    manager.set_entity_assignee_for_actor(assigner, record.entity_id, other_id)
    manager.set_entity_assignee_for_actor(
        assigner, record.entity_id, None, assign_to_originator=True
    )

    events = _assignee_events(engine)
    assert [event["metadata"]["new_assignee_id"] for event in events] == [
        creator_id,
        other_id,
        creator_id,
    ]
    assert _stored_assignee(engine, record.entity_id) == creator_id


def test_system_created_record_has_no_originator_to_assign(
    engine, make_manager, seeded_users, clean_records
) -> None:
    """A scheduler-created record carries a system actor and no actor_id."""
    manager = make_manager()
    entity_type_id = _entity_type(manager)
    record = _record(manager, build_system_actor(ORG_1, source="scheduler"), entity_type_id, "PAT-005")
    assigner = _actor(seeded_users(full_name="Nisha Verma"))

    with pytest.raises(ValidationError) as exc_info:
        manager.set_entity_assignee_for_actor(
            assigner, record.entity_id, None, assign_to_originator=True
        )

    assert exc_info.value.code == AssignmentRejection.ORIGINATOR_NOT_FOUND
    assert _stored_assignee(engine, record.entity_id) is None


def test_originator_whose_user_row_is_gone_is_rejected(
    engine, make_manager, seeded_users, clean_records
) -> None:
    manager = make_manager()
    entity_type_id = _entity_type(manager)
    # Creator never existed in `users` — the audit row still names them.
    record = _record(manager, _actor(str(uuid.uuid4())), entity_type_id, "PAT-006")
    assigner = _actor(seeded_users(full_name="Nisha Verma"))

    with pytest.raises(ValidationError) as exc_info:
        manager.set_entity_assignee_for_actor(
            assigner, record.entity_id, None, assign_to_originator=True
        )

    assert exc_info.value.code == AssignmentRejection.ORIGINATOR_USER_MISSING
    assert _stored_assignee(engine, record.entity_id) is None


# ── Originator assignability ────────────────────────────────────────────────


def test_suspended_originator_is_rejected_by_name_and_assignee_is_untouched(
    engine, make_manager, seeded_users, clean_records
) -> None:
    manager = make_manager()
    creator_id = seeded_users(
        full_name="Mohit Rana", membership_status=UserStatus.SUSPENDED.value
    )
    entity_type_id = _entity_type(manager)
    record = _record(manager, _actor(creator_id), entity_type_id, "PAT-007")
    held_by = seeded_users(full_name="Amit Shah")
    assigner = _actor(seeded_users(full_name="Nisha Verma"))
    manager.set_entity_assignee_for_actor(assigner, record.entity_id, held_by)

    with pytest.raises(ValidationError) as exc_info:
        manager.set_entity_assignee_for_actor(
            assigner, record.entity_id, None, assign_to_originator=True
        )

    assert exc_info.value.code == AssignmentRejection.ORIGINATOR_SUSPENDED
    assert "Mohit Rana cannot be assigned because the user is suspended." in str(exc_info.value)
    assert _stored_assignee(engine, record.entity_id) == held_by


@pytest.mark.parametrize(
    "account_status", [UserStatus.PENDING.value, UserStatus.REJECTED.value]
)
def test_inactive_account_with_active_membership_is_rejected(
    engine, make_manager, seeded_users, clean_records, account_status
) -> None:
    """The account lifecycle status gates assignment too, not only membership.

    A live CHECK constraint (`ck_users_status_lifecycle`) limits `users.status`
    to pending/active/rejected, so these two are the only non-active accounts
    that can exist — account-level *suspension* is not representable.
    """
    manager = make_manager()
    creator_id = seeded_users(
        full_name="Mohit Rana",
        status=account_status,
        membership_status=UserStatus.ACTIVE.value,
    )
    entity_type_id = _entity_type(manager)
    record = _record(manager, _actor(creator_id), entity_type_id, "PAT-008")
    assigner = _actor(seeded_users(full_name="Nisha Verma"))

    with pytest.raises(ValidationError) as exc_info:
        manager.set_entity_assignee_for_actor(
            assigner, record.entity_id, None, assign_to_originator=True
        )

    assert exc_info.value.code == AssignmentRejection.ORIGINATOR_INACTIVE_ACCOUNT
    assert "Mohit Rana cannot be assigned because their account is not active." in str(
        exc_info.value
    )
    assert _stored_assignee(engine, record.entity_id) is None


def test_account_status_cannot_hold_suspended(engine, seeded_users) -> None:
    """Guards the assumption above: suspension lives only on the membership row."""
    with pytest.raises(Exception) as exc_info:
        seeded_users(full_name="Nobody", status="suspended")
    assert "ck_users_status_lifecycle" in str(exc_info.value)


def test_primary_org_user_without_a_membership_row_is_rejected(
    engine, make_manager, seeded_users, clean_records
) -> None:
    """The legacy primary-organization fallback must not grant assignability."""
    manager = make_manager()
    creator_id = seeded_users(
        full_name="Mohit Rana", membership_status=None, primary_org=ORG_1
    )
    entity_type_id = _entity_type(manager)
    record = _record(manager, _actor(creator_id), entity_type_id, "PAT-009")
    assigner = _actor(seeded_users(full_name="Nisha Verma"))

    with pytest.raises(ValidationError) as exc_info:
        manager.set_entity_assignee_for_actor(
            assigner, record.entity_id, None, assign_to_originator=True
        )

    assert exc_info.value.code == AssignmentRejection.ORIGINATOR_NOT_A_MEMBER
    assert _stored_assignee(engine, record.entity_id) is None


def test_originator_who_belongs_only_to_another_org_is_rejected(
    engine, make_manager, seeded_users, clean_records
) -> None:
    manager = make_manager()
    creator_id = seeded_users(full_name="Mohit Rana", membership_org=ORG_2)
    entity_type_id = _entity_type(manager)
    record = _record(manager, _actor(creator_id), entity_type_id, "PAT-010")
    assigner = _actor(seeded_users(full_name="Nisha Verma"))

    with pytest.raises(ValidationError) as exc_info:
        manager.set_entity_assignee_for_actor(
            assigner, record.entity_id, None, assign_to_originator=True
        )

    assert exc_info.value.code == AssignmentRejection.ORIGINATOR_NOT_A_MEMBER
    assert _stored_assignee(engine, record.entity_id) is None


# ── Route contract: the endpoint itself is gated as a write ─────────────────


def _route_permission_keys(path: str, method: str) -> set[str]:
    """Permission keys the given route's dependencies enforce.

    Reads them off the registered FastAPI route rather than sending a request,
    so the gate can be asserted without a real token, org and role rows.
    """
    router = APIRouter()
    EntitiesRestController(object()).prepare(router)
    route = next(
        r
        for r in router.routes
        if getattr(r, "path", "") == path and method in getattr(r, "methods", set())
    )
    keys: set[str] = set()
    for dependency in route.dependant.dependencies:
        call = dependency.call
        if "require_permission" not in getattr(call, "__qualname__", ""):
            continue
        keys.update(
            cell.cell_contents
            for cell in (call.__closure__ or ())
            if isinstance(cell.cell_contents, str) and ":" in cell.cell_contents
        )
    return keys


def test_assignee_route_is_gated_by_entity_record_write() -> None:
    """The security fix lives on the route, so assert it there.

    Reverting the endpoint to a read-level actor would leave every
    manager-level test passing, and only this one failing.
    """
    assert _route_permission_keys("/entity-records/{entity_id}/assignee", "PUT") == {
        "entity_record:write"
    }


def test_assignee_route_is_gated_like_other_entity_writes() -> None:
    """Assignment is a write, so its gate must match the record-update route."""
    assignee = _route_permission_keys("/entity-records/{entity_id}/assignee", "PUT")
    update = _route_permission_keys("/entity-records/{entity_id}", "PUT")
    assert assignee == update


# ── Authorization: every assignment is a write ──────────────────────────────


def test_originator_assignment_requires_entity_edit_permission(
    engine, make_manager, seeded_users, clean_records
) -> None:
    manager = make_manager()
    creator_id = seeded_users(full_name="Mohit Rana")
    entity_type_id = _entity_type(manager)
    record = _record(manager, _actor(creator_id), entity_type_id, "PAT-011")
    assigner = _actor(seeded_users(full_name="Nisha Verma"))

    restricted = make_manager(can_edit=False)
    with pytest.raises(AuthorizationError):
        restricted.set_entity_assignee_for_actor(
            assigner, record.entity_id, None, assign_to_originator=True
        )

    assert _stored_assignee(engine, record.entity_id) is None


def test_self_assignment_requires_entity_edit_permission(
    engine, make_manager, seeded_users, clean_records
) -> None:
    """The security fix: picking up a record yourself is still a write."""
    manager = make_manager()
    user_id = seeded_users(full_name="Nisha Verma")
    actor = _actor(user_id)
    entity_type_id = _entity_type(manager)
    record = _record(manager, actor, entity_type_id, "PAT-012")

    restricted = make_manager(can_edit=False)
    with pytest.raises(AuthorizationError):
        restricted.set_entity_assignee_for_actor(actor, record.entity_id, user_id)

    assert _stored_assignee(engine, record.entity_id) is None


def test_self_unassignment_requires_entity_edit_permission(
    engine, make_manager, seeded_users, clean_records
) -> None:
    """Releasing a record you hold is a write as well."""
    manager = make_manager()
    holder_id = seeded_users(full_name="Nisha Verma")
    actor = _actor(holder_id)
    entity_type_id = _entity_type(manager)
    record = _record(manager, actor, entity_type_id, "PAT-013")
    manager.set_entity_assignee_for_actor(actor, record.entity_id, holder_id)

    restricted = make_manager(can_edit=False)
    with pytest.raises(AuthorizationError):
        restricted.set_entity_assignee_for_actor(actor, record.entity_id, None)

    assert _stored_assignee(engine, record.entity_id) == holder_id


def test_self_assignment_succeeds_with_edit_permission(
    engine, make_manager, seeded_users, clean_records
) -> None:
    manager = make_manager()
    user_id = seeded_users(full_name="Nisha Verma")
    actor = _actor(user_id)
    entity_type_id = _entity_type(manager)
    record = _record(manager, actor, entity_type_id, "PAT-014")

    response = manager.set_entity_assignee_for_actor(actor, record.entity_id, user_id)

    assert response.assignee_id == user_id
    assert _stored_assignee(engine, record.entity_id) == user_id


# ── Manual mode is unchanged ────────────────────────────────────────────────


def test_manual_assignment_does_not_validate_the_target(
    engine, make_manager, seeded_users, clean_records
) -> None:
    """Existing behavior preserved: manual mode accepts an unvalidated id.

    Originator validation must not leak into the manual path — the workflow
    action validates its own configured user instead.
    """
    manager = make_manager()
    entity_type_id = _entity_type(manager)
    record = _record(manager, _actor(seeded_users(full_name="Nisha Verma")), entity_type_id, "PAT-015")
    assigner = _actor(seeded_users(full_name="Amit Shah"))

    response = manager.set_entity_assignee_for_actor(assigner, record.entity_id, "not-a-real-user")

    assert response.assignee_id == "not-a-real-user"


def test_unassigning_clears_the_assignee_and_records_it(
    engine, make_manager, seeded_users, clean_records
) -> None:
    manager = make_manager()
    entity_type_id = _entity_type(manager)
    holder = seeded_users(full_name="Amit Shah")
    record = _record(manager, _actor(seeded_users(full_name="Nisha Verma")), entity_type_id, "PAT-016")
    assigner = _actor(seeded_users(full_name="Nisha Verma"))
    manager.set_entity_assignee_for_actor(assigner, record.entity_id, holder)

    response = manager.set_entity_assignee_for_actor(assigner, record.entity_id, None)

    assert response.assignee_id is None
    assert _stored_assignee(engine, record.entity_id) is None
    assert _assignee_events(engine)[-1]["metadata"]["new_assignee_id"] is None


def test_unassigning_an_already_unassigned_record_writes_no_history(
    engine, make_manager, seeded_users, clean_records
) -> None:
    manager = make_manager()
    entity_type_id = _entity_type(manager)
    record = _record(manager, _actor(seeded_users(full_name="Nisha Verma")), entity_type_id, "PAT-017")
    assigner = _actor(seeded_users(full_name="Amit Shah"))

    manager.set_entity_assignee_for_actor(assigner, record.entity_id, None)

    assert _assignee_events(engine) == []


# ── Originator on the record read path ──────────────────────────────────────
#
# `get_entity_with_states_for_actor` reports the originator so the UI can hide
# "Assign to Originator" from the person who created the record. The lookup
# must sit behind the same read authorization as the record itself.


def test_with_states_reports_the_creator_as_originator(
    make_manager, seeded_users, clean_records
) -> None:
    manager = make_manager()
    creator_id = seeded_users(full_name="Mohit Rana")
    entity_type_id = _entity_type(manager)
    record = _record(manager, _actor(creator_id), entity_type_id, "PAT-100")

    viewer = _actor(seeded_users(full_name="Nisha Verma"))
    response = manager.get_entity_with_states_for_actor(viewer, record.entity_id)

    assert response.originator_id == creator_id


def test_with_states_reports_no_originator_for_a_system_created_record(
    make_manager, seeded_users, clean_records
) -> None:
    """A record nobody human created has no originator — None, not an error.

    This is the case the action refuses at assign time, so the button should
    never be offered for it.
    """
    manager = make_manager()
    entity_type_id = _entity_type(manager)
    record = _record(manager, build_system_actor(ORG_1), entity_type_id, "PAT-101")

    viewer = _actor(seeded_users(full_name="Nisha Verma"))
    response = manager.get_entity_with_states_for_actor(viewer, record.entity_id)

    assert response.originator_id is None


def test_with_states_denies_the_originator_to_an_actor_denied_the_record(
    make_manager, seeded_users, clean_records
) -> None:
    """Entity-access denial must block the whole response, not just the record.

    The originator is resolved after the read gate, so a denied actor never
    reaches the audit log — asserted here by spying on the lookup.
    """
    seeding_manager = make_manager()
    creator_id = seeded_users(full_name="Mohit Rana")
    entity_type_id = _entity_type(seeding_manager)
    record = _record(seeding_manager, _actor(creator_id), entity_type_id, "PAT-102")

    manager = make_manager(can_view=False)
    calls: list[str] = []
    real_lookup = manager.audit_service_manager.find_entity_originator

    def _spy(**kwargs: Any) -> str | None:
        calls.append(str(kwargs.get("entity_id")))
        return real_lookup(**kwargs)

    manager.audit_service_manager.find_entity_originator = _spy  # type: ignore[method-assign]

    viewer = _actor(seeded_users(full_name="Nisha Verma"))
    with pytest.raises(AuthorizationError):
        manager.get_entity_with_states_for_actor(viewer, record.entity_id)

    assert calls == []


def test_with_states_does_not_expose_an_originator_across_organizations(
    make_manager, seeded_users, clean_records
) -> None:
    """A record belongs to one org — another org's actor gets nothing at all."""
    manager = make_manager()
    creator_id = seeded_users(full_name="Mohit Rana")
    entity_type_id = _entity_type(manager)
    record = _record(manager, _actor(creator_id), entity_type_id, "PAT-103")

    outsider = _actor(seeded_users(full_name="Raj Malhotra", membership_org=ORG_2), ORG_2)
    with pytest.raises(NotFoundError):
        manager.get_entity_with_states_for_actor(outsider, record.entity_id)


def test_with_states_originator_matches_the_user_the_action_would_assign(
    engine, make_manager, seeded_users, clean_records
) -> None:
    """The read path and the assign action must name the same person.

    Guards against the two drifting apart — they share one resolver, and this
    is the test that fails if someone gives either its own rule.
    """
    manager = make_manager()
    creator_id = seeded_users(full_name="Mohit Rana")
    entity_type_id = _entity_type(manager)
    record = _record(manager, _actor(creator_id), entity_type_id, "PAT-104")

    viewer = _actor(seeded_users(full_name="Nisha Verma"))
    reported = manager.get_entity_with_states_for_actor(viewer, record.entity_id).originator_id

    manager.set_entity_assignee_for_actor(viewer, record.entity_id, None, assign_to_originator=True)

    assert reported == _stored_assignee(engine, record.entity_id)
