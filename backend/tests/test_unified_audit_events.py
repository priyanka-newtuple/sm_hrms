"""Exhaustive coverage for the unified audit_events write/read pathway.

Covers:
  - entities/manager.py `_try_emit_audit_event`, called from all 5 entity CRUD
    paths (create, update, assignee-change, archive, restore).
  - audit/manager.py `AuditServiceManager.list_audit_events_for_actor` (the
    sole read path), including entity-scope authorization and field masking.

Uses real Postgres via the `entities_db_service_manager` fixture (see
conftest.py) — no ORM mocking. `roles_manager` and `user_service_manager`
are local, deterministic test doubles (not the real RBAC subsystem).
"""

from __future__ import annotations

import os
from typing import Any

import pytest
from sqlalchemy import text

from audit.db_models import AuditEventsModelService
from audit.manager import AuditServiceManager
from audit.models.interface import AuditMetadataKey
from common.enums import AuditMetadataType
from common.protocols import MASKED_FIELD_VALUE, EntityAccessCheck
from entities.db_models import EntitiesModelService
from entities.manager import EntitiesServiceManager
from entities.models.interface import EntityAuditEventType
from entities.models.request import (
    EntityRecordCreateRequest,
    EntityRecordUpdateRequest,
    EntityTypeCreateRequest,
)
from exceptions import AuthorizationError, NotFoundError, ValidationError

from tests.conftest import ENTITIES_TEST_ORG_IDS

ORG_1 = ENTITIES_TEST_ORG_IDS[0]
ORG_2 = ENTITIES_TEST_ORG_IDS[1]


class _AlwaysAllowAuth:
    """Minimal auth stand-in exposing `check_access` so `_resolve_identity_service`
    doesn't pick something else up; entities manager's own org-match check is
    what actually gates access in these tests."""

    class _Decision:
        allowed = True
        reason = ""

    def check_access(self, _payload: dict[str, object]) -> "_AlwaysAllowAuth._Decision":
        return self._Decision()


class FakeRolesManager:
    """Deterministic `RolesServiceProtocol` double.

    `rules` maps entity_type name -> {"visible": [...] | None, "masked": [...],
    "view_allowed": bool}. Missing entity types default to fully permissive
    (visible=None, masked=[], view_allowed=True) so tests that don't care
    about RBAC don't need to configure anything.
    """

    def __init__(self, rules: dict[str, dict[str, Any]] | None = None) -> None:
        self.rules = rules or {}

    def _rule(self, entity_type: str) -> dict[str, Any]:
        return self.rules.get(entity_type, {"visible": None, "masked": [], "view_allowed": True})

    def get_visible_fields(self, db: Any, user_id: str, org_id: str, entity_type: str) -> list[str] | None:
        return self._rule(entity_type).get("visible")

    def get_editable_fields(self, db: Any, user_id: str, org_id: str, entity_type: str) -> list[str] | None:
        return self._rule(entity_type).get("editable")

    def get_masked_fields(self, db: Any, user_id: str, org_id: str, entity_type: str) -> list[str]:
        return list(self._rule(entity_type).get("masked") or [])

    def check_entity_permission(
        self, db: Any, user_id: str, org_id: str, entity_type: str, action: str
    ) -> bool:
        return bool(self._rule(entity_type).get("view_allowed", True))

    def evaluate_entity_access(
        self, db: Any, user_id: str, org_id: str, entity_type: str, action: str
    ) -> EntityAccessCheck:
        """What `guard_write`/`guard_read` actually call. `write_allowed` gates
        edit/create/delete separately from `view_allowed` so a test can grant
        read but withhold write."""
        rule = self._rule(entity_type)
        key = "view_allowed" if action == "view" else "write_allowed"
        allowed = bool(rule.get(key, rule.get("view_allowed", True)))
        return EntityAccessCheck(allowed=allowed, conditions=[])


class FakeUserServiceManager:
    """Deterministic actor-display-info double.

    `raises=True` simulates a lookup failure (e.g. user deleted) without
    blocking the audit write."""

    def __init__(self, name: str = "Ada Lovelace", role: str = "recruiter", raises: bool = False) -> None:
        self.name = name
        self.role = role
        self.raises = raises

    def get_actor_display_info(self, actor: dict[str, object]) -> tuple[str | None, str | None]:
        if self.raises:
            raise RuntimeError("user lookup unavailable")
        return self.name, self.role


class _AlwaysRaisingAuditEventsService:
    """Simulates `audit_events_service` being entirely unavailable."""

    def emit_audit_event(self, **kwargs: object) -> None:
        raise RuntimeError("audit backend is down")


def _actor(user_id: str, organization_id: str, actor_type: str = "user") -> dict[str, object]:
    return {
        "user_id": user_id,
        "organization_id": organization_id,
        "actor_type": actor_type,
        "roles": ["admin"],
    }


def _audit_schema() -> str:
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "modular_backend")
    return f"{app_schema}_audit"


@pytest.fixture
def clean_audit_events(entities_db_service_manager):
    """Truncate audit_events, entity_events, and the entity/entity_type rows
    this suite creates for the test orgs, before and after each test.

    Entity types created here use a fixed set of names (e.g. "Candidate"), so
    without cleanup the `(org, name, version)` uniqueness constraint on
    entity_types would collide across tests in this module.
    """
    audit_schema = _audit_schema()
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "modular_backend")
    runtime_schema = f"{app_schema}_runtime"
    definitions_schema = f"{app_schema}_definitions"
    engine = entities_db_service_manager.postgres_db_service().engine

    def _cleanup() -> None:
        with engine.begin() as conn:
            conn.execute(
                text(f'DELETE FROM "{audit_schema}".audit_events WHERE organization_id = ANY(:ids)'),
                {"ids": list(ENTITIES_TEST_ORG_IDS)},
            )
            conn.execute(
                text(f'DELETE FROM "{audit_schema}".entity_events WHERE organization_id = ANY(:ids)'),
                {"ids": list(ENTITIES_TEST_ORG_IDS)},
            )
            conn.execute(
                text(f'DELETE FROM "{runtime_schema}".entity_state WHERE organization_id = ANY(:ids)'),
                {"ids": list(ENTITIES_TEST_ORG_IDS)},
            )
            conn.execute(
                text(f'DELETE FROM "{runtime_schema}".entities WHERE organization_id = ANY(:ids)'),
                {"ids": list(ENTITIES_TEST_ORG_IDS)},
            )
            conn.execute(
                text(
                    f'DELETE FROM "{definitions_schema}".entity_type_relations '
                    f"WHERE organization_id = ANY(:ids)"
                ),
                {"ids": list(ENTITIES_TEST_ORG_IDS)},
            )
            conn.execute(
                text(f'DELETE FROM "{definitions_schema}".entity_types WHERE organization_id = ANY(:ids)'),
                {"ids": list(ENTITIES_TEST_ORG_IDS)},
            )

    _cleanup()
    yield
    _cleanup()


def _count_entity_events(entities_db_service_manager, organization_id: str) -> int:
    """Query the legacy entity_events table directly to prove no new rows land there."""
    schema = _audit_schema()
    engine = entities_db_service_manager.postgres_db_service().engine
    with engine.connect() as conn:
        row = conn.execute(
            text(f'SELECT COUNT(*) FROM "{schema}".entity_events WHERE organization_id = :org_id'),
            {"org_id": organization_id},
        ).fetchone()
        return int(row[0])


def _query_audit_events(entities_db_service_manager, organization_id: str) -> list[dict]:
    """Read audit_events rows directly (bypassing the manager) for write-path assertions."""
    schema = _audit_schema()
    engine = entities_db_service_manager.postgres_db_service().engine
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f'SELECT organization_id, metadata_type, entity_type, entity_id, event_type, '
                f'actor_id, actor_name, actor_role, actor_type, metadata '
                f'FROM "{schema}".audit_events WHERE organization_id = :org_id '
                f"ORDER BY event_timestamp ASC"
            ),
            {"org_id": organization_id},
        ).mappings().all()
        return [dict(r) for r in rows]


@pytest.fixture
def entities_db_service(entities_db_service_manager) -> EntitiesModelService:
    return EntitiesModelService(database_service_manager=entities_db_service_manager)


@pytest.fixture
def audit_events_service(entities_db_service_manager) -> AuditEventsModelService:
    return AuditEventsModelService(database_service_manager=entities_db_service_manager)


def _make_entities_manager(
    entities_db_service: EntitiesModelService,
    entities_db_service_manager,
    audit_events_service: Any,
    roles_manager: Any = None,
    user_service_manager: Any = None,
) -> EntitiesServiceManager:
    manager = EntitiesServiceManager(
        entities_db_service,
        database_service_manager=entities_db_service_manager,
        config=None,
        auth_service_manager=_AlwaysAllowAuth(),
        # Permissive by default: assignment now checks entity edit permission on
        # every call, including self-assignment, so a `None` roles service would
        # make unrelated audit assertions fail on an attribute error.
        roles_manager=roles_manager if roles_manager is not None else FakeRolesManager(),
        audit_service_manager=AuditServiceManager(audit_events_service),
        user_service_manager=user_service_manager,
    )
    manager.start()
    return manager


def _make_audit_manager(
    audit_events_service: AuditEventsModelService,
    entities_db_service: EntitiesModelService,
    roles_manager: Any,
) -> AuditServiceManager:
    manager = AuditServiceManager(
        audit_events_service,
        roles_manager=roles_manager,
        entities_db_model_service=entities_db_service,
    )
    manager.start()
    return manager


def _create_entity_type(
    entities_manager: EntitiesServiceManager, organization_id: str, name: str
) -> str:
    response = entities_manager.create_entity_type(
        EntityTypeCreateRequest(
            organization_id=organization_id,
            name=name,
            schema_definition={"fields": [{"name": "email", "type": "email"}]},
            version=1,
            is_active=True,
        )
    )
    return response.entity_type_id


def _patch_audit_emit_type_lookup_to_raise(monkeypatch: pytest.MonkeyPatch, entities_db_service: EntitiesModelService) -> None:
    """Make `get_entity_type_name_by_id` raise only for the audit-emit call site.

    `_try_emit_audit_event` calls it without a `db` session (it opens its own
    lookup), while `guard_read`/`guard_write` (the RBAC gate that runs earlier
    in every `_for_actor` method) always pass an open `db` session. Patching
    unconditionally would break the primary operation itself instead of only
    the best-effort audit lookup, which is not the scenario under test.
    """
    original = entities_db_service.get_entity_type_name_by_id

    def _maybe_raise(*args: object, **kwargs: object) -> str | None:
        if kwargs.get("db") is not None:
            return original(*args, **kwargs)
        raise RuntimeError("entity type lookup exploded")

    monkeypatch.setattr(entities_db_service, "get_entity_type_name_by_id", _maybe_raise)


def _create_entity_record(
    entities_manager: EntitiesServiceManager,
    actor: dict[str, object],
    entity_type_id: str,
    identifier: str,
    owner_id: str | None = None,
):
    return entities_manager.create_entity_record_for_actor(
        actor,
        EntityRecordCreateRequest(
            organization_id=actor["organization_id"],
            entity_type_id=entity_type_id,
            data={"identifier": identifier, "email": f"{identifier}@example.com"},
            owner_id=owner_id,
        ),
    )


# ── Write pathway: CREATE ───────────────────────────────────────────────────


def test_create_entity_record_writes_single_audit_event_with_correct_shape(
    entities_db_service, entities_db_service_manager, audit_events_service, clean_audit_events
) -> None:
    roles_manager = FakeRolesManager()
    user_manager = FakeUserServiceManager(name="Ada Lovelace", role="recruiter")
    manager = _make_entities_manager(
        entities_db_service, entities_db_service_manager, audit_events_service, roles_manager, user_manager
    )
    actor = _actor("user-1", ORG_1)
    entity_type_id = _create_entity_type(manager, ORG_1, "Candidate")

    record = _create_entity_record(manager, actor, entity_type_id, "CAND-001", owner_id="owner-9")

    events = _query_audit_events(entities_db_service_manager, ORG_1)
    assert len(events) == 1
    event = events[0]
    assert event["metadata_type"] == AuditMetadataType.ENTITY.value
    assert event["event_type"] == str(EntityAuditEventType.CREATED)
    assert event["entity_type"] == "Candidate"
    assert event["entity_id"] == record.entity_id
    assert event["actor_id"] == "user-1"
    assert event["actor_name"] == "Ada Lovelace"
    assert event["actor_role"] == "recruiter"
    assert event["actor_type"] == "user"
    assert event["metadata"] == {"identifier": "CAND-001", "owner_id": "owner-9"}


def test_create_entity_record_writes_no_entity_events_row(
    entities_db_service, entities_db_service_manager, audit_events_service, clean_audit_events
) -> None:
    manager = _make_entities_manager(entities_db_service, entities_db_service_manager, audit_events_service)
    actor = _actor("user-1", ORG_1)
    entity_type_id = _create_entity_type(manager, ORG_1, "Candidate")

    _create_entity_record(manager, actor, entity_type_id, "CAND-002")

    assert _count_entity_events(entities_db_service_manager, ORG_1) == 0


# ── Write pathway: UPDATE ───────────────────────────────────────────────────


def test_update_entity_record_writes_audit_event_with_changed_fields(
    entities_db_service, entities_db_service_manager, audit_events_service, clean_audit_events
) -> None:
    manager = _make_entities_manager(entities_db_service, entities_db_service_manager, audit_events_service)
    actor = _actor("user-1", ORG_1)
    entity_type_id = _create_entity_type(manager, ORG_1, "Candidate")
    record = _create_entity_record(manager, actor, entity_type_id, "CAND-003")

    manager.update_entity_record_for_actor(
        actor,
        record.entity_id,
        EntityRecordUpdateRequest(data={"email": "new@example.com"}),
    )

    events = _query_audit_events(entities_db_service_manager, ORG_1)
    update_events = [e for e in events if e["event_type"] == str(EntityAuditEventType.UPDATED)]
    assert len(update_events) == 1
    changed_fields = update_events[0]["metadata"]["changed_fields"]
    assert changed_fields == {
        "email": {"before": f"CAND-003@example.com", "after": "new@example.com"}
    }


def test_update_entity_record_with_no_field_changes_emits_no_event(
    entities_db_service, entities_db_service_manager, audit_events_service, clean_audit_events
) -> None:
    manager = _make_entities_manager(entities_db_service, entities_db_service_manager, audit_events_service)
    actor = _actor("user-1", ORG_1)
    entity_type_id = _create_entity_type(manager, ORG_1, "Candidate")
    record = _create_entity_record(manager, actor, entity_type_id, "CAND-004")

    # Re-submit the identical email value -> no actual change.
    manager.update_entity_record_for_actor(
        actor,
        record.entity_id,
        EntityRecordUpdateRequest(data={"email": "CAND-004@example.com"}),
    )

    events = _query_audit_events(entities_db_service_manager, ORG_1)
    update_events = [e for e in events if e["event_type"] == str(EntityAuditEventType.UPDATED)]
    assert update_events == []


# ── Write pathway: ASSIGNEE_CHANGED ─────────────────────────────────────────


def test_set_entity_assignee_writes_audit_event_with_previous_and_new_assignee(
    entities_db_service, entities_db_service_manager, audit_events_service, clean_audit_events
) -> None:
    manager = _make_entities_manager(entities_db_service, entities_db_service_manager, audit_events_service)
    actor = _actor("user-1", ORG_1)
    entity_type_id = _create_entity_type(manager, ORG_1, "Candidate")
    record = _create_entity_record(manager, actor, entity_type_id, "CAND-005")

    manager.set_entity_assignee_for_actor(actor, record.entity_id, "assignee-a")
    # Reassign as the same actor is fine as long as "assignee-a" isn't the actor itself.
    manager.set_entity_assignee_for_actor(actor, record.entity_id, "assignee-b")

    events = _query_audit_events(entities_db_service_manager, ORG_1)
    assignee_events = [
        e for e in events if e["event_type"] == str(EntityAuditEventType.ASSIGNEE_CHANGED)
    ]
    assert len(assignee_events) == 2
    assert assignee_events[0]["metadata"] == {
        "previous_assignee_id": None,
        "new_assignee_id": "assignee-a",
        "assignment_mode": "manual",
        "assignment_source": "api",
    }
    assert assignee_events[1]["metadata"] == {
        "previous_assignee_id": "assignee-a",
        "new_assignee_id": "assignee-b",
        "assignment_mode": "manual",
        "assignment_source": "api",
    }


# ── Write pathway: ARCHIVE / RESTORE ────────────────────────────────────────


def test_archive_entity_record_writes_audit_event_with_empty_metadata(
    entities_db_service, entities_db_service_manager, audit_events_service, clean_audit_events
) -> None:
    manager = _make_entities_manager(entities_db_service, entities_db_service_manager, audit_events_service)
    actor = _actor("user-1", ORG_1)
    entity_type_id = _create_entity_type(manager, ORG_1, "Candidate")
    record = _create_entity_record(manager, actor, entity_type_id, "CAND-006")

    manager.archive_entity_record_for_actor(actor, record.entity_id)

    events = _query_audit_events(entities_db_service_manager, ORG_1)
    archive_events = [e for e in events if e["event_type"] == str(EntityAuditEventType.ARCHIVED)]
    assert len(archive_events) == 1
    assert archive_events[0]["metadata"] == {}
    assert archive_events[0]["entity_id"] == record.entity_id


def test_restore_entity_record_writes_audit_event_with_empty_metadata(
    entities_db_service, entities_db_service_manager, audit_events_service, clean_audit_events
) -> None:
    manager = _make_entities_manager(entities_db_service, entities_db_service_manager, audit_events_service)
    actor = _actor("user-1", ORG_1)
    entity_type_id = _create_entity_type(manager, ORG_1, "Candidate")
    record = _create_entity_record(manager, actor, entity_type_id, "CAND-007")
    manager.archive_entity_record_for_actor(actor, record.entity_id)

    manager.restore_entity_record_for_actor(actor, record.entity_id)

    events = _query_audit_events(entities_db_service_manager, ORG_1)
    restore_events = [e for e in events if e["event_type"] == str(EntityAuditEventType.RESTORED)]
    assert len(restore_events) == 1
    assert restore_events[0]["metadata"] == {}


def test_no_entity_events_rows_written_across_full_crud_lifecycle(
    entities_db_service, entities_db_service_manager, audit_events_service, clean_audit_events
) -> None:
    manager = _make_entities_manager(entities_db_service, entities_db_service_manager, audit_events_service)
    actor = _actor("user-1", ORG_1)
    entity_type_id = _create_entity_type(manager, ORG_1, "Candidate")
    record = _create_entity_record(manager, actor, entity_type_id, "CAND-008")
    manager.update_entity_record_for_actor(
        actor, record.entity_id, EntityRecordUpdateRequest(data={"email": "x@example.com"})
    )
    manager.set_entity_assignee_for_actor(actor, record.entity_id, "assignee-z")
    manager.archive_entity_record_for_actor(actor, record.entity_id)
    manager.restore_entity_record_for_actor(actor, record.entity_id)

    assert _count_entity_events(entities_db_service_manager, ORG_1) == 0
    # Sanity: the unified table did receive rows for this lifecycle.
    assert len(_query_audit_events(entities_db_service_manager, ORG_1)) == 5


# ── Write pathway: degraded-dependency resilience ───────────────────────────


def test_entity_type_name_lookup_failure_still_writes_audit_row_with_null_entity_type(
    entities_db_service, entities_db_service_manager, audit_events_service, clean_audit_events, monkeypatch
) -> None:
    manager = _make_entities_manager(entities_db_service, entities_db_service_manager, audit_events_service)
    actor = _actor("user-1", ORG_1)
    entity_type_id = _create_entity_type(manager, ORG_1, "Candidate")

    def _raise_lookup(*args: object, **kwargs: object) -> str | None:
        raise RuntimeError("entity type lookup exploded")

    _patch_audit_emit_type_lookup_to_raise(monkeypatch, entities_db_service)

    record = _create_entity_record(manager, actor, entity_type_id, "CAND-009")

    events = _query_audit_events(entities_db_service_manager, ORG_1)
    assert len(events) == 1
    assert events[0]["entity_type"] is None
    assert events[0]["entity_id"] == record.entity_id
    assert events[0]["event_type"] == str(EntityAuditEventType.CREATED)


def test_actor_display_info_failure_still_writes_audit_row_with_null_actor_fields(
    entities_db_service, entities_db_service_manager, audit_events_service, clean_audit_events
) -> None:
    failing_user_manager = FakeUserServiceManager(raises=True)
    manager = _make_entities_manager(
        entities_db_service,
        entities_db_service_manager,
        audit_events_service,
        user_service_manager=failing_user_manager,
    )
    actor = _actor("user-1", ORG_1)
    entity_type_id = _create_entity_type(manager, ORG_1, "Candidate")

    record = _create_entity_record(manager, actor, entity_type_id, "CAND-010")

    events = _query_audit_events(entities_db_service_manager, ORG_1)
    assert len(events) == 1
    assert events[0]["actor_name"] is None
    assert events[0]["actor_role"] is None
    assert events[0]["entity_id"] == record.entity_id


def test_audit_service_unavailable_does_not_block_entity_creation(
    entities_db_service, entities_db_service_manager, clean_audit_events
) -> None:
    manager = _make_entities_manager(
        entities_db_service,
        entities_db_service_manager,
        audit_events_service=_AlwaysRaisingAuditEventsService(),
    )
    actor = _actor("user-1", ORG_1)
    entity_type_id = _create_entity_type(manager, ORG_1, "Candidate")

    # The primary operation must succeed even though the audit backend raises.
    record = _create_entity_record(manager, actor, entity_type_id, "CAND-011")

    assert record.entity_id
    assert record.data["identifier"] == "CAND-011"


def test_audit_service_none_does_not_block_entity_creation(
    entities_db_service, entities_db_service_manager, clean_audit_events
) -> None:
    manager = _make_entities_manager(
        entities_db_service, entities_db_service_manager, audit_events_service=None
    )
    actor = _actor("user-1", ORG_1)
    entity_type_id = _create_entity_type(manager, ORG_1, "Candidate")

    record = _create_entity_record(manager, actor, entity_type_id, "CAND-012")

    assert record.entity_id


# ── Read pathway: entity-scoped listing, pagination, authorization ─────────


def test_list_audit_events_entity_scoped_returns_items_newest_first_with_total(
    entities_db_service, entities_db_service_manager, audit_events_service, clean_audit_events
) -> None:
    roles_manager = FakeRolesManager()
    entities_manager = _make_entities_manager(
        entities_db_service, entities_db_service_manager, audit_events_service, roles_manager
    )
    audit_manager = _make_audit_manager(audit_events_service, entities_db_service, roles_manager)
    actor = _actor("user-1", ORG_1)
    entity_type_id = _create_entity_type(entities_manager, ORG_1, "Candidate")
    record = _create_entity_record(entities_manager, actor, entity_type_id, "CAND-013")
    entities_manager.update_entity_record_for_actor(
        actor, record.entity_id, EntityRecordUpdateRequest(data={"email": "a@example.com"})
    )
    entities_manager.archive_entity_record_for_actor(actor, record.entity_id)

    response = audit_manager.list_audit_events_for_actor(actor, entity_id=record.entity_id)

    assert response.total == 3
    assert len(response.items) == 3
    # newest first
    assert response.items[0].event_type == str(EntityAuditEventType.ARCHIVED)
    assert response.items[1].event_type == str(EntityAuditEventType.UPDATED)
    assert response.items[2].event_type == str(EntityAuditEventType.CREATED)


def test_list_audit_events_entity_scoped_respects_limit_and_offset(
    entities_db_service, entities_db_service_manager, audit_events_service, clean_audit_events
) -> None:
    roles_manager = FakeRolesManager()
    entities_manager = _make_entities_manager(
        entities_db_service, entities_db_service_manager, audit_events_service, roles_manager
    )
    audit_manager = _make_audit_manager(audit_events_service, entities_db_service, roles_manager)
    actor = _actor("user-1", ORG_1)
    entity_type_id = _create_entity_type(entities_manager, ORG_1, "Candidate")
    record = _create_entity_record(entities_manager, actor, entity_type_id, "CAND-014")
    entities_manager.set_entity_assignee_for_actor(actor, record.entity_id, "a1")
    entities_manager.set_entity_assignee_for_actor(actor, record.entity_id, "a2")
    entities_manager.archive_entity_record_for_actor(actor, record.entity_id)
    # 4 events total: CREATED, ASSIGNEE_CHANGED x2, ARCHIVED

    page1 = audit_manager.list_audit_events_for_actor(actor, entity_id=record.entity_id, limit=2, offset=0)
    page2 = audit_manager.list_audit_events_for_actor(actor, entity_id=record.entity_id, limit=2, offset=2)

    assert page1.total == 4
    assert page2.total == 4
    assert len(page1.items) == 2
    assert len(page2.items) == 2
    assert page1.items[0].event_type == str(EntityAuditEventType.ARCHIVED)
    assert page2.items[1].event_type == str(EntityAuditEventType.CREATED)


def test_list_audit_events_nonexistent_entity_raises_not_found(
    entities_db_service, entities_db_service_manager, audit_events_service, clean_audit_events
) -> None:
    roles_manager = FakeRolesManager()
    audit_manager = _make_audit_manager(audit_events_service, entities_db_service, roles_manager)
    actor = _actor("user-1", ORG_1)

    with pytest.raises(NotFoundError):
        audit_manager.list_audit_events_for_actor(actor, entity_id="does-not-exist")


def test_list_audit_events_wrong_org_entity_raises_not_found(
    entities_db_service, entities_db_service_manager, audit_events_service, clean_audit_events
) -> None:
    roles_manager = FakeRolesManager()
    entities_manager = _make_entities_manager(
        entities_db_service, entities_db_service_manager, audit_events_service, roles_manager
    )
    audit_manager = _make_audit_manager(audit_events_service, entities_db_service, roles_manager)
    owner_actor = _actor("user-1", ORG_1)
    entity_type_id = _create_entity_type(entities_manager, ORG_1, "Candidate")
    record = _create_entity_record(entities_manager, owner_actor, entity_type_id, "CAND-015")

    other_org_actor = _actor("user-2", ORG_2)

    with pytest.raises(NotFoundError):
        audit_manager.list_audit_events_for_actor(other_org_actor, entity_id=record.entity_id)


def test_list_audit_events_actor_without_view_permission_raises_authorization_error(
    entities_db_service, entities_db_service_manager, audit_events_service, clean_audit_events
) -> None:
    permissive_roles = FakeRolesManager()
    entities_manager = _make_entities_manager(
        entities_db_service, entities_db_service_manager, audit_events_service, permissive_roles
    )
    actor = _actor("user-1", ORG_1)
    entity_type_id = _create_entity_type(entities_manager, ORG_1, "Candidate")
    record = _create_entity_record(entities_manager, actor, entity_type_id, "CAND-016")

    restrictive_roles = FakeRolesManager({"Candidate": {"view_allowed": False}})
    audit_manager = _make_audit_manager(audit_events_service, entities_db_service, restrictive_roles)

    with pytest.raises(AuthorizationError):
        audit_manager.list_audit_events_for_actor(actor, entity_id=record.entity_id)


# ── Read pathway: field masking on ENTITY_UPDATED ───────────────────────────


def test_list_audit_events_masks_field_not_in_visible_fields(
    entities_db_service, entities_db_service_manager, audit_events_service, clean_audit_events
) -> None:
    permissive_roles = FakeRolesManager()
    entities_manager = _make_entities_manager(
        entities_db_service, entities_db_service_manager, audit_events_service, permissive_roles
    )
    actor = _actor("user-1", ORG_1)
    entity_type_id = _create_entity_type(entities_manager, ORG_1, "Candidate")
    record = _create_entity_record(entities_manager, actor, entity_type_id, "CAND-017")
    entities_manager.update_entity_record_for_actor(
        actor, record.entity_id, EntityRecordUpdateRequest(data={"email": "new@example.com"})
    )

    # Reader can only see "identifier", not "email" -> email dropped entirely.
    restrictive_roles = FakeRolesManager({"Candidate": {"visible": ["identifier"], "masked": []}})
    audit_manager = _make_audit_manager(audit_events_service, entities_db_service, restrictive_roles)

    response = audit_manager.list_audit_events_for_actor(actor, entity_id=record.entity_id)

    update_events = [i for i in response.items if i.event_type == str(EntityAuditEventType.UPDATED)]
    assert len(update_events) == 1
    assert update_events[0].metadata[AuditMetadataKey.CHANGED_FIELDS] == {}


def test_list_audit_events_masks_field_in_masked_fields(
    entities_db_service, entities_db_service_manager, audit_events_service, clean_audit_events
) -> None:
    permissive_roles = FakeRolesManager()
    entities_manager = _make_entities_manager(
        entities_db_service, entities_db_service_manager, audit_events_service, permissive_roles
    )
    actor = _actor("user-1", ORG_1)
    entity_type_id = _create_entity_type(entities_manager, ORG_1, "Candidate")
    record = _create_entity_record(entities_manager, actor, entity_type_id, "CAND-018")
    entities_manager.update_entity_record_for_actor(
        actor, record.entity_id, EntityRecordUpdateRequest(data={"email": "new@example.com"})
    )

    masking_roles = FakeRolesManager({"Candidate": {"visible": None, "masked": ["email"]}})
    audit_manager = _make_audit_manager(audit_events_service, entities_db_service, masking_roles)

    response = audit_manager.list_audit_events_for_actor(actor, entity_id=record.entity_id)

    update_events = [i for i in response.items if i.event_type == str(EntityAuditEventType.UPDATED)]
    changed = update_events[0].metadata[AuditMetadataKey.CHANGED_FIELDS]
    assert changed["email"] == {"before": MASKED_FIELD_VALUE, "after": MASKED_FIELD_VALUE}


def test_list_audit_events_unrestricted_field_passes_through_full_value(
    entities_db_service, entities_db_service_manager, audit_events_service, clean_audit_events
) -> None:
    roles_manager = FakeRolesManager()
    entities_manager = _make_entities_manager(
        entities_db_service, entities_db_service_manager, audit_events_service, roles_manager
    )
    audit_manager = _make_audit_manager(audit_events_service, entities_db_service, roles_manager)
    actor = _actor("user-1", ORG_1)
    entity_type_id = _create_entity_type(entities_manager, ORG_1, "Candidate")
    record = _create_entity_record(entities_manager, actor, entity_type_id, "CAND-019")
    entities_manager.update_entity_record_for_actor(
        actor, record.entity_id, EntityRecordUpdateRequest(data={"email": "new@example.com"})
    )

    response = audit_manager.list_audit_events_for_actor(actor, entity_id=record.entity_id)

    update_events = [i for i in response.items if i.event_type == str(EntityAuditEventType.UPDATED)]
    changed = update_events[0].metadata[AuditMetadataKey.CHANGED_FIELDS]
    assert changed["email"] == {"before": "CAND-019@example.com", "after": "new@example.com"}


def test_list_audit_events_row_with_null_entity_type_fails_closed(
    entities_db_service, entities_db_service_manager, audit_events_service, clean_audit_events, monkeypatch
) -> None:
    roles_manager = FakeRolesManager()
    entities_manager = _make_entities_manager(
        entities_db_service, entities_db_service_manager, audit_events_service, roles_manager
    )
    audit_manager = _make_audit_manager(audit_events_service, entities_db_service, roles_manager)
    actor = _actor("user-1", ORG_1)
    entity_type_id = _create_entity_type(entities_manager, ORG_1, "Candidate")
    record = _create_entity_record(entities_manager, actor, entity_type_id, "CAND-020")

    _patch_audit_emit_type_lookup_to_raise(monkeypatch, entities_db_service)
    entities_manager.update_entity_record_for_actor(
        actor, record.entity_id, EntityRecordUpdateRequest(data={"email": "new@example.com"})
    )
    monkeypatch.undo()

    response = audit_manager.list_audit_events_for_actor(actor, entity_id=record.entity_id)

    update_events = [i for i in response.items if i.event_type == str(EntityAuditEventType.UPDATED)]
    assert len(update_events) == 1
    assert update_events[0].entity_type is None
    changed = update_events[0].metadata[AuditMetadataKey.CHANGED_FIELDS]
    # Fail-closed: full redaction, not passthrough.
    assert changed["email"] == {"before": MASKED_FIELD_VALUE, "after": MASKED_FIELD_VALUE}


def test_list_audit_events_non_updated_events_are_never_masked(
    entities_db_service, entities_db_service_manager, audit_events_service, clean_audit_events
) -> None:
    masking_roles = FakeRolesManager({"Candidate": {"visible": ["identifier"], "masked": ["owner_id"]}})
    entities_manager = _make_entities_manager(
        entities_db_service, entities_db_service_manager, audit_events_service, masking_roles
    )
    audit_manager = _make_audit_manager(audit_events_service, entities_db_service, masking_roles)
    actor = _actor("user-1", ORG_1)
    entity_type_id = _create_entity_type(entities_manager, ORG_1, "Candidate")
    record = _create_entity_record(entities_manager, actor, entity_type_id, "CAND-021", owner_id="owner-1")
    entities_manager.archive_entity_record_for_actor(actor, record.entity_id)

    response = audit_manager.list_audit_events_for_actor(actor, entity_id=record.entity_id)

    created = next(i for i in response.items if i.event_type == str(EntityAuditEventType.CREATED))
    archived = next(i for i in response.items if i.event_type == str(EntityAuditEventType.ARCHIVED))
    # CREATED payload uses "owner_id" as a top-level metadata key, not inside
    # changed_fields, so masking (which only ever touches CHANGED_FIELDS on
    # ENTITY_UPDATED rows) must leave it untouched.
    assert created.metadata == {"identifier": "CAND-021", "owner_id": "owner-1"}
    assert archived.metadata == {}


# ── Read pathway: org-wide listing ──────────────────────────────────────────


def test_list_audit_events_org_wide_returns_events_across_entities(
    entities_db_service, entities_db_service_manager, audit_events_service, clean_audit_events
) -> None:
    roles_manager = FakeRolesManager()
    entities_manager = _make_entities_manager(
        entities_db_service, entities_db_service_manager, audit_events_service, roles_manager
    )
    audit_manager = _make_audit_manager(audit_events_service, entities_db_service, roles_manager)
    actor = _actor("user-1", ORG_1)
    entity_type_id = _create_entity_type(entities_manager, ORG_1, "Candidate")
    record_a = _create_entity_record(entities_manager, actor, entity_type_id, "CAND-022")
    record_b = _create_entity_record(entities_manager, actor, entity_type_id, "CAND-023")

    response = audit_manager.list_audit_events_for_actor(actor)

    assert response.entity_id is None
    assert response.total == 2
    returned_entity_ids = {item.entity_id for item in response.items}
    assert returned_entity_ids == {record_a.entity_id, record_b.entity_id}


def test_list_audit_events_org_wide_does_not_leak_other_org_events(
    entities_db_service, entities_db_service_manager, audit_events_service, clean_audit_events
) -> None:
    roles_manager = FakeRolesManager()
    entities_manager = _make_entities_manager(
        entities_db_service, entities_db_service_manager, audit_events_service, roles_manager
    )
    audit_manager = _make_audit_manager(audit_events_service, entities_db_service, roles_manager)
    org1_actor = _actor("user-1", ORG_1)
    org2_actor = _actor("user-2", ORG_2)
    et_org1 = _create_entity_type(entities_manager, ORG_1, "Candidate")
    et_org2 = _create_entity_type(entities_manager, ORG_2, "Candidate")
    _create_entity_record(entities_manager, org1_actor, et_org1, "CAND-024")
    _create_entity_record(entities_manager, org2_actor, et_org2, "CAND-025")

    response = audit_manager.list_audit_events_for_actor(org1_actor)

    assert response.total == 1
    assert all(item.organization_id == ORG_1 for item in response.items)


# ── Read pathway: metadata_type / event_type filters ────────────────────────


def test_list_audit_events_metadata_type_filter_narrows_results(
    entities_db_service, entities_db_service_manager, audit_events_service, clean_audit_events
) -> None:
    roles_manager = FakeRolesManager()
    entities_manager = _make_entities_manager(
        entities_db_service, entities_db_service_manager, audit_events_service, roles_manager
    )
    audit_manager = _make_audit_manager(audit_events_service, entities_db_service, roles_manager)
    actor = _actor("user-1", ORG_1)
    entity_type_id = _create_entity_type(entities_manager, ORG_1, "Candidate")
    _create_entity_record(entities_manager, actor, entity_type_id, "CAND-026")

    matching = audit_manager.list_audit_events_for_actor(
        actor, metadata_type=AuditMetadataType.ENTITY.value
    )
    non_matching = audit_manager.list_audit_events_for_actor(
        actor, metadata_type=AuditMetadataType.TRANSITION.value
    )

    assert matching.total == 1
    assert non_matching.total == 0


def test_list_audit_events_metadata_type_single_string_still_works_entity_scoped(
    entities_db_service, entities_db_service_manager, audit_events_service, clean_audit_events
) -> None:
    """Backward compat: a plain single string for metadata_type (not a list)
    must keep working on the entity-scoped path after adding list support."""
    roles_manager = FakeRolesManager()
    entities_manager = _make_entities_manager(
        entities_db_service, entities_db_service_manager, audit_events_service, roles_manager
    )
    audit_manager = _make_audit_manager(audit_events_service, entities_db_service, roles_manager)
    actor = _actor("user-1", ORG_1)
    entity_type_id = _create_entity_type(entities_manager, ORG_1, "Candidate")
    record = _create_entity_record(entities_manager, actor, entity_type_id, "CAND-028")
    audit_events_service.emit_audit_event(
        organization_id=ORG_1,
        metadata_type=AuditMetadataType.TRANSITION,
        entity_id=record.entity_id,
        event_type="TRANSITION_SUCCEEDED",
        actor_type="user",
    )

    result = audit_manager.list_audit_events_for_actor(
        actor, entity_id=record.entity_id, metadata_type=AuditMetadataType.ENTITY.value
    )

    assert result.total == 1
    assert result.items[0].metadata_type == AuditMetadataType.ENTITY.value


def test_list_audit_events_metadata_type_accepts_list_entity_scoped(
    entities_db_service, entities_db_service_manager, audit_events_service, clean_audit_events
) -> None:
    """New capability: metadata_type as a list of values returns the union,
    scoped to one entity, without needing multiple API calls."""
    roles_manager = FakeRolesManager()
    entities_manager = _make_entities_manager(
        entities_db_service, entities_db_service_manager, audit_events_service, roles_manager
    )
    audit_manager = _make_audit_manager(audit_events_service, entities_db_service, roles_manager)
    actor = _actor("user-1", ORG_1)
    entity_type_id = _create_entity_type(entities_manager, ORG_1, "Candidate")
    record = _create_entity_record(entities_manager, actor, entity_type_id, "CAND-029")
    audit_events_service.emit_audit_event(
        organization_id=ORG_1,
        metadata_type=AuditMetadataType.TRANSITION,
        entity_id=record.entity_id,
        event_type="TRANSITION_SUCCEEDED",
        actor_type="user",
    )
    audit_events_service.emit_audit_event(
        organization_id=ORG_1,
        metadata_type=AuditMetadataType.AUTH,
        entity_id=record.entity_id,
        event_type="AUTH_LOGIN_SUCCESS",
        actor_type="user",
    )

    result = audit_manager.list_audit_events_for_actor(
        actor,
        entity_id=record.entity_id,
        metadata_type=[AuditMetadataType.ENTITY.value, AuditMetadataType.TRANSITION.value],
    )

    assert result.total == 2
    returned_types = {item.metadata_type for item in result.items}
    assert returned_types == {AuditMetadataType.ENTITY.value, AuditMetadataType.TRANSITION.value}


def test_list_audit_events_metadata_type_invalid_single_value_raises_validation_error(
    entities_db_service, entities_db_service_manager, audit_events_service, clean_audit_events
) -> None:
    """A single unrecognized metadata_type (e.g. a typo or wrong case) must be
    rejected outright rather than silently matching zero rows."""
    roles_manager = FakeRolesManager()
    audit_manager = _make_audit_manager(audit_events_service, entities_db_service, roles_manager)
    actor = _actor("user-1", ORG_1)

    with pytest.raises(ValidationError):
        audit_manager.list_audit_events_for_actor(actor, metadata_type="bogus")


def test_list_audit_events_metadata_type_wrong_case_raises_validation_error(
    entities_db_service, entities_db_service_manager, audit_events_service, clean_audit_events
) -> None:
    """Postgres string comparison is case-sensitive, so a wrong-case value would
    otherwise silently match zero rows instead of erroring -- must be rejected."""
    roles_manager = FakeRolesManager()
    audit_manager = _make_audit_manager(audit_events_service, entities_db_service, roles_manager)
    actor = _actor("user-1", ORG_1)

    with pytest.raises(ValidationError):
        audit_manager.list_audit_events_for_actor(actor, metadata_type="Entity")


def test_list_audit_events_metadata_type_mixed_valid_and_invalid_raises_validation_error(
    entities_db_service, entities_db_service_manager, audit_events_service, clean_audit_events
) -> None:
    """Fail closed on a mixed list: one bad value invalidates the whole request
    rather than silently narrowing to only the valid entries."""
    roles_manager = FakeRolesManager()
    audit_manager = _make_audit_manager(audit_events_service, entities_db_service, roles_manager)
    actor = _actor("user-1", ORG_1)

    with pytest.raises(ValidationError):
        audit_manager.list_audit_events_for_actor(
            actor, metadata_type=[AuditMetadataType.ENTITY.value, "bogus"]
        )


def test_list_audit_events_metadata_type_empty_list_treated_as_no_filter(
    entities_db_service, entities_db_service_manager, audit_events_service, clean_audit_events
) -> None:
    """An empty list isn't reachable via HTTP (a URL can't express zero values for
    a repeated query param) but is exercised here as a direct manager call: it has
    no invalid elements, so it passes validation and is treated as "no filter",
    matching the pre-existing `list_for_*_paginated` behavior."""
    roles_manager = FakeRolesManager()
    entities_manager = _make_entities_manager(
        entities_db_service, entities_db_service_manager, audit_events_service, roles_manager
    )
    audit_manager = _make_audit_manager(audit_events_service, entities_db_service, roles_manager)
    actor = _actor("user-1", ORG_1)
    entity_type_id = _create_entity_type(entities_manager, ORG_1, "Candidate")
    _create_entity_record(entities_manager, actor, entity_type_id, "CAND-032")

    result = audit_manager.list_audit_events_for_actor(actor, metadata_type=[])

    assert result.total == 1


def test_list_audit_events_event_type_filter_narrows_results(
    entities_db_service, entities_db_service_manager, audit_events_service, clean_audit_events
) -> None:
    roles_manager = FakeRolesManager()
    entities_manager = _make_entities_manager(
        entities_db_service, entities_db_service_manager, audit_events_service, roles_manager
    )
    audit_manager = _make_audit_manager(audit_events_service, entities_db_service, roles_manager)
    actor = _actor("user-1", ORG_1)
    entity_type_id = _create_entity_type(entities_manager, ORG_1, "Candidate")
    record = _create_entity_record(entities_manager, actor, entity_type_id, "CAND-027")
    entities_manager.archive_entity_record_for_actor(actor, record.entity_id)

    created_only = audit_manager.list_audit_events_for_actor(
        actor, entity_id=record.entity_id, event_type=str(EntityAuditEventType.CREATED)
    )
    archived_only = audit_manager.list_audit_events_for_actor(
        actor, entity_id=record.entity_id, event_type=str(EntityAuditEventType.ARCHIVED)
    )

    assert created_only.total == 1
    assert created_only.items[0].event_type == str(EntityAuditEventType.CREATED)
    assert archived_only.total == 1
    assert archived_only.items[0].event_type == str(EntityAuditEventType.ARCHIVED)


# ── Read pathway: cross-module rows (comments, auth) unaffected by entity-CRUD
# masking/scope changes ──────────────────────────────────────────────────────
#
# `list_audit_events_for_actor` is the single read path for *all* writers into
# `audit_events`, not just entities/manager.py. These tests insert rows shaped
# exactly like backend/comments/manager.py's `_emit_comment_event` and
# backend/auth/db_models.py's `log_auth_event` write them (verified above by
# reading both call sites directly) to prove the entity-CRUD-specific masking
# pass (`_mask_entity_updated_items`) and the newly-added `_check_entity_scope`
# gate behave correctly against non-entity-CRUD rows, without touching
# comments/manager.py or auth/manager.py themselves.


def test_list_audit_events_comment_shaped_row_passes_through_unmasked(
    entities_db_service, entities_db_service_manager, audit_events_service, clean_audit_events
) -> None:
    roles_manager = FakeRolesManager()
    entities_manager = _make_entities_manager(
        entities_db_service, entities_db_service_manager, audit_events_service, roles_manager
    )
    audit_manager = _make_audit_manager(audit_events_service, entities_db_service, roles_manager)
    actor = _actor("user-1", ORG_1)
    entity_type_id = _create_entity_type(entities_manager, ORG_1, "Candidate")
    record = _create_entity_record(entities_manager, actor, entity_type_id, "CAND-028")

    comment_metadata = {"comment_id": "some-id", "content_preview": "hello", "is_internal": False}
    audit_events_service.emit_audit_event(
        organization_id=ORG_1,
        metadata_type=AuditMetadataType.ENTITY,
        entity_id=record.entity_id,
        event_type="COMMENT_CREATED",
        actor_type="user",
        actor_id="user-1",
        user_id="user-1",
        source="api",
        event_metadata=comment_metadata,
    )

    response = audit_manager.list_audit_events_for_actor(actor, entity_id=record.entity_id)

    comment_events = [i for i in response.items if i.event_type == "COMMENT_CREATED"]
    assert len(comment_events) == 1
    # Untouched by `_mask_entity_updated_items`: no "changed_fields" key, so
    # the masking gate's isinstance/key check skips this row entirely.
    assert comment_events[0].metadata == comment_metadata


def test_list_audit_events_comment_shaped_row_still_subject_to_entity_scope_gate(
    entities_db_service, entities_db_service_manager, audit_events_service, clean_audit_events
) -> None:
    permissive_roles = FakeRolesManager()
    entities_manager = _make_entities_manager(
        entities_db_service, entities_db_service_manager, audit_events_service, permissive_roles
    )
    actor = _actor("user-1", ORG_1)
    entity_type_id = _create_entity_type(entities_manager, ORG_1, "Candidate")
    record = _create_entity_record(entities_manager, actor, entity_type_id, "CAND-029")

    audit_events_service.emit_audit_event(
        organization_id=ORG_1,
        metadata_type=AuditMetadataType.ENTITY,
        entity_id=record.entity_id,
        event_type="COMMENT_CREATED",
        actor_type="user",
        actor_id="user-1",
        user_id="user-1",
        source="api",
        event_metadata={"comment_id": "some-id", "content_preview": "hello", "is_internal": False},
    )

    # `_check_entity_scope` gates on the entity's type, not on the event_type
    # of any individual row within it -- deliberate widening vs. the old
    # (nonexistent) permission check on this endpoint, and it applies
    # uniformly to every row scoped to that entity, comment rows included.
    restrictive_roles = FakeRolesManager({"Candidate": {"view_allowed": False}})
    audit_manager = _make_audit_manager(audit_events_service, entities_db_service, restrictive_roles)

    with pytest.raises(AuthorizationError):
        audit_manager.list_audit_events_for_actor(actor, entity_id=record.entity_id)


def test_list_audit_events_auth_shaped_row_appears_in_org_wide_listing_unmasked(
    entities_db_service, entities_db_service_manager, audit_events_service, clean_audit_events
) -> None:
    roles_manager = FakeRolesManager()
    entities_manager = _make_entities_manager(
        entities_db_service, entities_db_service_manager, audit_events_service, roles_manager
    )
    audit_manager = _make_audit_manager(audit_events_service, entities_db_service, roles_manager)
    actor = _actor("user-1", ORG_1)
    entity_type_id = _create_entity_type(entities_manager, ORG_1, "Candidate")
    _create_entity_record(entities_manager, actor, entity_type_id, "CAND-030")

    auth_metadata = {"email": "ada@example.com"}
    audit_events_service.emit_audit_event(
        organization_id=ORG_1,
        metadata_type=AuditMetadataType.AUTH,
        entity_id=None,
        event_type="AUTH_LOGIN_SUCCESS",
        actor_type="system",
        actor_id="auth_service",
        user_id="user-1",
        source="api",
        event_metadata=auth_metadata,
    )

    response = audit_manager.list_audit_events_for_actor(actor)

    assert response.total == 2  # 1 entity-CRUD CREATED row + 1 auth row
    auth_events = [i for i in response.items if i.event_type == "AUTH_LOGIN_SUCCESS"]
    assert len(auth_events) == 1
    assert auth_events[0].metadata_type == AuditMetadataType.AUTH.value
    assert auth_events[0].entity_id is None
    # Not `metadata_type=ENTITY` at all, so `_mask_entity_updated_items`'s
    # filter excludes it outright regardless of `changed_fields` presence.
    assert auth_events[0].metadata == auth_metadata


def test_list_audit_events_org_wide_mixed_rows_masks_only_entity_updated_row(
    entities_db_service, entities_db_service_manager, audit_events_service, clean_audit_events
) -> None:
    masking_roles = FakeRolesManager({"Candidate": {"visible": None, "masked": ["email"]}})
    entities_manager = _make_entities_manager(
        entities_db_service, entities_db_service_manager, audit_events_service, masking_roles
    )
    audit_manager = _make_audit_manager(audit_events_service, entities_db_service, masking_roles)
    actor = _actor("user-1", ORG_1)
    entity_type_id = _create_entity_type(entities_manager, ORG_1, "Candidate")
    record = _create_entity_record(entities_manager, actor, entity_type_id, "CAND-031")
    entities_manager.update_entity_record_for_actor(
        actor, record.entity_id, EntityRecordUpdateRequest(data={"email": "new@example.com"})
    )

    comment_metadata = {"comment_id": "some-id", "content_preview": "hello", "is_internal": False}
    audit_events_service.emit_audit_event(
        organization_id=ORG_1,
        metadata_type=AuditMetadataType.ENTITY,
        entity_id=record.entity_id,
        event_type="COMMENT_CREATED",
        actor_type="user",
        actor_id="user-1",
        user_id="user-1",
        source="api",
        event_metadata=comment_metadata,
    )
    auth_metadata = {"email": "ada@example.com"}
    audit_events_service.emit_audit_event(
        organization_id=ORG_1,
        metadata_type=AuditMetadataType.AUTH,
        entity_id=None,
        event_type="AUTH_LOGIN_SUCCESS",
        actor_type="system",
        actor_id="auth_service",
        user_id="user-1",
        source="api",
        event_metadata=auth_metadata,
    )

    response = audit_manager.list_audit_events_for_actor(actor)

    assert response.total == 4  # CREATED, ENTITY_UPDATED, COMMENT_CREATED, AUTH_LOGIN_SUCCESS
    by_type = {i.event_type: i for i in response.items}

    updated = by_type[str(EntityAuditEventType.UPDATED)]
    changed = updated.metadata[AuditMetadataKey.CHANGED_FIELDS]
    assert changed["email"] == {"before": MASKED_FIELD_VALUE, "after": MASKED_FIELD_VALUE}

    comment_event = by_type["COMMENT_CREATED"]
    assert comment_event.metadata == comment_metadata

    auth_event = by_type["AUTH_LOGIN_SUCCESS"]
    assert auth_event.metadata == auth_metadata


# ── Deleted-endpoint stub ────────────────────────────────────────────────────
#
# `GET /entity-records/{entity_id}/events` at the full FastAPI-router level is
# skipped here: wiring a `TestClient` for this module requires the real
# `require_permission` auth dependency chain (DB-backed `get_db` + bearer
# token parsing) which is disproportionate to stand up for a fixed-404 stub
# with no manager/DB call. The behavior (fixed 404, exact detail message,
# `include_in_schema=False`, no manager/db touch) is verified by direct code
# inspection of backend/entities/controller.py instead.
