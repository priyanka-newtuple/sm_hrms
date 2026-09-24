"""Tests for SEC-027 — workflow enrollment RBAC fix.

`enroll_entity_for_actor` (workflow/manager.py) is called from both the REST
endpoint (already gated by `workflow:write` at the controller) and the
agent's `enroll_entity_in_workflow` tool (which was NOT gated at all before
this fix). This suite exercises the fix at the manager level, against the
real Postgres test database, with real `roles`/`role_permissions`/
`role_workflow_permissions`/`user_roles` rows seeded per scenario — per
`design_docs/tony_workflow_enrollment_rbac_fix.md`'s Tier 1 test tier
("no mocking of anything permission-related").

Run inside the running `modular-backend` container (fastest, matches real
runtime exactly — see `design_docs/jarvis_map.md`, "Fast path for
entities/roles-module manager-level tests"):

    docker cp backend/tests/test_workflow_enrollment_rbac_fix.py \\
        state-machine-modular-modular-backend-1:/app/backend/tests/test_workflow_enrollment_rbac_fix.py
    docker exec state-machine-modular-modular-backend-1 \\
        python -m pytest tests/test_workflow_enrollment_rbac_fix.py -v
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import text

from audit.db_models import AuditEventsModelService
from audit.manager import AuditServiceManager
from blob_storage.service import BlobStorageService
from entities.db_models import EntitiesModelService
from entities.manager import EntitiesServiceManager
from entities.models.request import EntityTypeCreateRequest
from exceptions import AuthorizationError, ConflictError, NotFoundError
from filehandler.db_models import FilehandlerModelService
from filehandler.manager import FilehandlerServiceManager
from forms.db_models import FormsModelService
from method_library.db_models import MethodLibraryModelService
from permissions.db_models import PermissionsModelService
from roles.db_models import Role, RolePermission, RoleWorkflowPermission, RolesModelService, UserRoleAssignment
from roles.manager import RolesServiceManager
from user.db_models import UserModelService
from user.manager import UserServiceManager
from workflow_manager_factory import NoActiveFormsManager
from workflow.db_models import WorkflowModelService
from workflow.manager import WorkflowServiceManager
from workflow.models.interface import EntitySchema, State, StateMachineDefinition
from workflow.models.request import StateMachineCreateRequest

from tests.conftest import ENTITIES_TEST_ORG_IDS
from tests.test_workflow_module import _AlwaysAllowAuth, _db_is_reachable

pytestmark = pytest.mark.skipif(
    not _db_is_reachable(), reason="Postgres host is not reachable in this environment"
)

TEST_ORG = ENTITIES_TEST_ORG_IDS[0]


def _blank_state_machine(machine_key: str, entity_type_name: str) -> StateMachineDefinition:
    return StateMachineDefinition(
        machine_key=machine_key,
        name=machine_key,
        description="",
        entity_type=entity_type_name,
        entity_schema=EntitySchema(entity_type=entity_type_name, fields=[]),
        states=[State(name="INITIAL", tags=["initial"], order=1)],
        initial_state="INITIAL",
        transitions=[],
    )


@pytest.fixture
def rbac_env(entities_db_service_manager, clean_entities_tables):
    """Real Postgres-backed WorkflowServiceManager wired to a real
    RolesServiceManager — no fakes/mocks anywhere in the permission path."""
    engine = entities_db_service_manager.postgres_db_service().engine
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM workflow_state_machines WHERE organization_id = ANY(:ids)"),
            {"ids": list(ENTITIES_TEST_ORG_IDS)},
        )
        conn.execute(text("DELETE FROM user_roles WHERE organization_id = ANY(:ids)"), {"ids": list(ENTITIES_TEST_ORG_IDS)})
        conn.execute(
            text(
                "DELETE FROM role_permissions WHERE role_id IN "
                "(SELECT id FROM roles WHERE organization_id = ANY(:ids))"
            ),
            {"ids": list(ENTITIES_TEST_ORG_IDS)},
        )
        conn.execute(
            text(
                "DELETE FROM role_workflow_permissions WHERE role_id IN "
                "(SELECT id FROM roles WHERE organization_id = ANY(:ids))"
            ),
            {"ids": list(ENTITIES_TEST_ORG_IDS)},
        )
        conn.execute(text("DELETE FROM roles WHERE organization_id = ANY(:ids)"), {"ids": list(ENTITIES_TEST_ORG_IDS)})

    permissions_db = PermissionsModelService(entities_db_service_manager)
    roles_db = RolesModelService(entities_db_service_manager, permissions_model_service=permissions_db)
    roles_manager = RolesServiceManager(roles_db, entities_db_service_manager, config=None)

    user_db = UserModelService(entities_db_service_manager)
    user_manager = UserServiceManager(user_db, entities_db_service_manager, config=None)
    audit_events_service = AuditEventsModelService(entities_db_service_manager)

    entities_db = EntitiesModelService(database_service_manager=entities_db_service_manager)
    entities = EntitiesServiceManager(
        entities_db,
        database_service_manager=entities_db_service_manager,
        config=None,
        auth_service_manager=_AlwaysAllowAuth(),
        roles_manager=roles_manager,
        audit_service_manager=AuditServiceManager(audit_events_service),
        user_service_manager=user_manager,
    )
    entities.start()

    forms_db_model_service = FormsModelService(entities_db_service_manager)
    filehandler_db_model_service = FilehandlerModelService(entities_db_service_manager)
    filehandler_service_manager = FilehandlerServiceManager(
        filehandler_db_model_service, entities_db_service_manager, None
    )
    blob_storage_service = BlobStorageService()

    workflow_db = WorkflowModelService(database_service_manager=entities_db_service_manager)
    manager = WorkflowServiceManager(
        workflow_db_model_service=workflow_db,
        database_service_manager=entities_db_service_manager,
        config=None,
        entities_service_manager=entities,
        roles_manager=roles_manager,
        audit_events_service=audit_events_service,
        forms_service_manager=NoActiveFormsManager(),
        method_library_db_model_service=MethodLibraryModelService(entities_db_service_manager),
        filehandler_service_manager=filehandler_service_manager,
        user_service_manager=user_manager,
        blob_storage_service=blob_storage_service,
    )
    manager.start()

    entity_type_name = f"rbac_fix_type_{uuid.uuid4().hex[:8]}"
    entity_type_id = entities.create_entity_type_for_actor(
        {"user_id": "seed-admin", "organization_id": TEST_ORG, "roles": ["admin"]},
        EntityTypeCreateRequest(name=entity_type_name, description="rbac fix test type"),
    ).entity_type_id

    yield {
        "manager": manager,
        "roles_db": roles_db,
        "entities": entities,
        "engine": engine,
        "entity_type_id": entity_type_id,
        "entity_type_name": entity_type_name,
    }


def _new_session(env):
    from sqlalchemy.orm import sessionmaker

    return sessionmaker(bind=env["engine"])()


def _seed_user(session, user_id: str, org_id: str) -> None:
    session.execute(
        text(
            """
            INSERT INTO users (id, email, full_name, role, status, auth_type, organization_id)
            VALUES (:id, :email, :full_name, 'user', 'active', 'password', :org_id)
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {"id": user_id, "email": f"{user_id}@rbacfix.test", "full_name": user_id, "org_id": org_id},
    )


def _seed_role(
    session,
    *,
    org_id: str,
    user_id: str,
    permission_keys: list[str],
    workflow_scope: list[str] | None = None,
    is_system: bool = False,
) -> str:
    """Create one role granting `permission_keys`, assign it to `user_id`."""
    _seed_user(session, user_id, org_id)
    role = Role(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        name=f"rbacfix_{uuid.uuid4().hex[:10]}",
        display_name="RBAC fix test role",
        is_system=is_system,
        priority=0,
    )
    session.add(role)
    session.flush()
    for key in permission_keys:
        session.add(
            RolePermission(
                id=str(uuid.uuid4()),
                role_id=role.id,
                permission_key=key,
                allowed=True,
            )
        )
    for machine_name in workflow_scope or []:
        session.add(
            RoleWorkflowPermission(id=str(uuid.uuid4()), role_id=role.id, machine_name=machine_name)
        )
    session.add(
        UserRoleAssignment(
            id=str(uuid.uuid4()),
            user_id=user_id,
            organization_id=org_id,
            role_id=role.id,
        )
    )
    session.commit()
    return role.id


def _actor(user_id: str, org_id: str = TEST_ORG) -> dict[str, Any]:
    return {"user_id": user_id, "organization_id": org_id}


def _create_machine(env, machine_name: str) -> None:
    definition = _blank_state_machine(machine_name, env["entity_type_name"])
    env["manager"].workflow_db.create_state_machine_published(
        StateMachineCreateRequest(machine_name=machine_name, version=1, is_active=True, definition=definition),
        organization_id=TEST_ORG,
    )


def _create_entity(env) -> str:
    from entities.models.request import EntityRecordCreateRequest

    record = env["entities"].create_entity_record(
        EntityRecordCreateRequest(
            organization_id=TEST_ORG, entity_type_id=env["entity_type_id"], data={}
        )
    )
    return record.entity_id


# ── R1 — full permissions: must keep working ────────────────────────────────

def test_r1_full_permissions_enrolls_successfully(rbac_env) -> None:
    session = _new_session(rbac_env)
    user_id = f"r1-{uuid.uuid4().hex[:8]}"
    _seed_role(session, org_id=TEST_ORG, user_id=user_id, permission_keys=["workflow:read", "workflow:write"])
    machine_name = f"wf_r1_{uuid.uuid4().hex[:8]}"
    _create_machine(rbac_env, machine_name)
    entity_id = _create_entity(rbac_env)

    result = rbac_env["manager"].enroll_entity_for_actor(_actor(user_id), machine_name, entity_id)
    assert result.entity_id == entity_id
    assert result.machine_name == machine_name


# ── R2 — read-only: the bug's exact shape, must now be blocked ─────────────

def test_r2_read_only_role_is_denied_write(rbac_env) -> None:
    session = _new_session(rbac_env)
    user_id = f"r2-{uuid.uuid4().hex[:8]}"
    _seed_role(session, org_id=TEST_ORG, user_id=user_id, permission_keys=["workflow:read"])
    machine_name = f"wf_r2_{uuid.uuid4().hex[:8]}"
    _create_machine(rbac_env, machine_name)
    entity_id = _create_entity(rbac_env)

    with pytest.raises(AuthorizationError):
        rbac_env["manager"].enroll_entity_for_actor(_actor(user_id), machine_name, entity_id)


# ── R3 — write-only, no read: must fail at the existing scope check first ──

def test_r3_write_only_no_read_fails_at_scope_check_not_new_check(rbac_env) -> None:
    session = _new_session(rbac_env)
    user_id = f"r3-{uuid.uuid4().hex[:8]}"
    _seed_role(session, org_id=TEST_ORG, user_id=user_id, permission_keys=["workflow:write"])
    machine_name = f"wf_r3_{uuid.uuid4().hex[:8]}"
    _create_machine(rbac_env, machine_name)
    entity_id = _create_entity(rbac_env)

    with pytest.raises(NotFoundError):
        rbac_env["manager"].enroll_entity_for_actor(_actor(user_id), machine_name, entity_id)


# ── R4 — neither: blocked ───────────────────────────────────────────────────

def test_r4_no_workflow_permissions_is_denied(rbac_env) -> None:
    session = _new_session(rbac_env)
    user_id = f"r4-{uuid.uuid4().hex[:8]}"
    _seed_role(session, org_id=TEST_ORG, user_id=user_id, permission_keys=[])
    machine_name = f"wf_r4_{uuid.uuid4().hex[:8]}"
    _create_machine(rbac_env, machine_name)
    entity_id = _create_entity(rbac_env)

    with pytest.raises(NotFoundError):
        rbac_env["manager"].enroll_entity_for_actor(_actor(user_id), machine_name, entity_id)


# ── R5 — is_system role: unconditional pass ─────────────────────────────────

def test_r5_is_system_role_passes_unconditionally(rbac_env) -> None:
    session = _new_session(rbac_env)
    user_id = f"r5-{uuid.uuid4().hex[:8]}"
    _seed_role(session, org_id=TEST_ORG, user_id=user_id, permission_keys=[], is_system=True)
    machine_name = f"wf_r5_{uuid.uuid4().hex[:8]}"
    _create_machine(rbac_env, machine_name)
    entity_id = _create_entity(rbac_env)

    result = rbac_env["manager"].enroll_entity_for_actor(_actor(user_id), machine_name, entity_id)
    assert result.entity_id == entity_id


# ── R6 — two roles combined, neither alone sufficient ───────────────────────

def test_r6_combined_roles_grant_full_access(rbac_env) -> None:
    session = _new_session(rbac_env)
    user_id = f"r6-{uuid.uuid4().hex[:8]}"
    _seed_role(session, org_id=TEST_ORG, user_id=user_id, permission_keys=["workflow:read"])
    _seed_role(session, org_id=TEST_ORG, user_id=user_id, permission_keys=["workflow:write"])
    machine_name = f"wf_r6_{uuid.uuid4().hex[:8]}"
    _create_machine(rbac_env, machine_name)
    entity_id = _create_entity(rbac_env)

    result = rbac_env["manager"].enroll_entity_for_actor(_actor(user_id), machine_name, entity_id)
    assert result.entity_id == entity_id


# ── R7 — scoped role: existing scope check must be unaffected ──────────────

def test_r7_scoped_role_in_scope_succeeds(rbac_env) -> None:
    session = _new_session(rbac_env)
    user_id = f"r7a-{uuid.uuid4().hex[:8]}"
    machine_name = f"wf_alpha_{uuid.uuid4().hex[:8]}"
    _seed_role(
        session,
        org_id=TEST_ORG,
        user_id=user_id,
        permission_keys=["workflow:read", "workflow:write"],
        workflow_scope=[machine_name],
    )
    _create_machine(rbac_env, machine_name)
    entity_id = _create_entity(rbac_env)

    result = rbac_env["manager"].enroll_entity_for_actor(_actor(user_id), machine_name, entity_id)
    assert result.entity_id == entity_id


def test_r7_scoped_role_out_of_scope_fails_at_scope_check(rbac_env) -> None:
    session = _new_session(rbac_env)
    user_id = f"r7b-{uuid.uuid4().hex[:8]}"
    in_scope_machine = f"wf_alpha_{uuid.uuid4().hex[:8]}"
    out_of_scope_machine = f"wf_beta_{uuid.uuid4().hex[:8]}"
    _seed_role(
        session,
        org_id=TEST_ORG,
        user_id=user_id,
        permission_keys=["workflow:read", "workflow:write"],
        workflow_scope=[in_scope_machine],
    )
    _create_machine(rbac_env, out_of_scope_machine)
    entity_id = _create_entity(rbac_env)

    with pytest.raises(NotFoundError):
        rbac_env["manager"].enroll_entity_for_actor(_actor(user_id), out_of_scope_machine, entity_id)


# ── System actor (scheduler): unaffected by this fix ────────────────────────

def test_system_actor_bypasses_both_checks(rbac_env) -> None:
    from common.auth import build_system_actor

    machine_name = f"wf_sys_{uuid.uuid4().hex[:8]}"
    _create_machine(rbac_env, machine_name)
    entity_id = _create_entity(rbac_env)

    actor = build_system_actor(TEST_ORG, source="scheduler")
    result = rbac_env["manager"].enroll_entity_for_actor(actor, machine_name, entity_id)
    assert result.entity_id == entity_id


# ── Live, not cached: permission changes take effect on the very next call ─

def test_permission_grant_takes_effect_immediately(rbac_env) -> None:
    session = _new_session(rbac_env)
    user_id = f"live-grant-{uuid.uuid4().hex[:8]}"
    role_id = _seed_role(session, org_id=TEST_ORG, user_id=user_id, permission_keys=["workflow:read"])
    machine_name = f"wf_live_grant_{uuid.uuid4().hex[:8]}"
    _create_machine(rbac_env, machine_name)
    entity_id = _create_entity(rbac_env)

    with pytest.raises(AuthorizationError):
        rbac_env["manager"].enroll_entity_for_actor(_actor(user_id), machine_name, entity_id)

    session.add(RolePermission(id=str(uuid.uuid4()), role_id=role_id, permission_key="workflow:write", allowed=True))
    session.commit()

    result = rbac_env["manager"].enroll_entity_for_actor(_actor(user_id), machine_name, entity_id)
    assert result.entity_id == entity_id


def test_permission_revoke_takes_effect_immediately(rbac_env) -> None:
    session = _new_session(rbac_env)
    user_id = f"live-revoke-{uuid.uuid4().hex[:8]}"
    role_id = _seed_role(
        session, org_id=TEST_ORG, user_id=user_id, permission_keys=["workflow:read", "workflow:write"]
    )
    machine_name = f"wf_live_revoke_{uuid.uuid4().hex[:8]}"
    _create_machine(rbac_env, machine_name)
    entity_one = _create_entity(rbac_env)
    entity_two = _create_entity(rbac_env)

    first = rbac_env["manager"].enroll_entity_for_actor(_actor(user_id), machine_name, entity_one)
    assert first.entity_id == entity_one

    session.query(RolePermission).filter(
        RolePermission.role_id == role_id, RolePermission.permission_key == "workflow:write"
    ).delete()
    session.commit()

    with pytest.raises(AuthorizationError):
        rbac_env["manager"].enroll_entity_for_actor(_actor(user_id), machine_name, entity_two)


# ── Conflict must not be masked by (or mistaken for) authorization denial ──

def test_duplicate_enrollment_raises_conflict_not_authorization_error(rbac_env) -> None:
    session = _new_session(rbac_env)
    user_id = f"conflict-{uuid.uuid4().hex[:8]}"
    _seed_role(session, org_id=TEST_ORG, user_id=user_id, permission_keys=["workflow:read", "workflow:write"])
    machine_name = f"wf_conflict_{uuid.uuid4().hex[:8]}"
    _create_machine(rbac_env, machine_name)
    entity_id = _create_entity(rbac_env)

    first = rbac_env["manager"].enroll_entity_for_actor(_actor(user_id), machine_name, entity_id)
    assert first.entity_id == entity_id

    with pytest.raises(ConflictError):
        rbac_env["manager"].enroll_entity_for_actor(_actor(user_id), machine_name, entity_id)
