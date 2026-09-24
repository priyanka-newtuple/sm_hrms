"""Single-pass RBAC behavior proof for inherited-field source-permission resolution.

Reuses the Vehicle_Company/Car use case from
`design_docs/tony_inherited_field_source_permission_resolution_notes.md` (same
fields, same sample rows, same 3-role permission matrix), turned into an
automated, repeatable check against the real production code path: real
Postgres, real `EntitiesModelService` + `EntitiesServiceManager`, real entity
types/relation-declarations/records created and read through the actual
manager methods behind every fixed endpoint (list x2 variants, get-one,
summary, create, update). Only `roles_manager` is a test double — driven by
an explicit, in-memory permission matrix (`FakeRolesManager`) instead of real
`roles`/`field_permissions` rows, so a role's permissions can be edited and
the exact same request re-run within one test, proving the check is resolved
live rather than cached.

Two entity types feed off Vehicle_Company: `Car` (REFERENCE — inherited
fields always read the company's current data) and `CarLeaseSnapshot`
(SNAPSHOT — inherited fields frozen at link time), so both relation types
are exercised against the identical permission matrix. A 4th role
(`outside_viewer`) has no entity-level `view` access to Vehicle_Company at
all, proving the entity-level gate independently of the field-level gate the
3-role matrix alone would cover.

Run:
    cd backend
    DATABASE_URL=postgresql://statemachine:statemachine@localhost:5455/statemachine \\
    POSTGRES_APP_SCHEMA=modular_backend \\
    uv run pytest tests/test_inherited_field_rbac_matrix.py -v
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field

import pytest
from sqlalchemy import text

from common.configuration import Configuration
from common.protocols import (
    MASKED_FIELD_VALUE,
    EntityAccessCheck,
    EntityConditionSpec,
    EntityReadPolicy,
)
from entities.db_models import EntitiesModelService
from entities.manager import EntitiesServiceManager
from entities.models.request import (
    EntityRecordCreateRequest,
    EntityRecordUpdateRequest,
    EntityRelationDeclarationCreateRequest,
    EntityTypeCreateRequest,
)
from exceptions import AuthorizationError

MASKED = MASKED_FIELD_VALUE
APP_SCHEMA = os.environ.get("POSTGRES_APP_SCHEMA", "modular_backend")


# ── Seed data — 3 Vehicle_Companies, 12 Cars ────────────────────────────────
# CAR-1/CAR-2 are the original 2 cars every existing test already keys off of
# (fixture_data.car1_id/car2_id, unchanged) — CAR-3..CAR-12 are 10 more, added
# to give the row-condition tests below a real, varied dataset to filter over.


@dataclass(frozen=True)
class CompanySeed:
    key: str
    identifier: str
    name: str
    registration_number: str
    safety_rating: str
    fleet_size: int


COMPANY_SEED = [
    CompanySeed("green", "VC-GREEN", "GreenLine Logistics", "VC-2291-KA", "A", 120),
    CompanySeed("metro", "VC-METRO", "Metro Freight Co", "VC-4410-MH", "C", 45),
    CompanySeed("silver", "VC-SILVER", "Silverline Transport", "VC-7788-DL", "A", 80),
]


@dataclass(frozen=True)
class CarSeed:
    identifier: str
    plate: str
    model: str
    mileage: int
    company_key: str  # "green" | "metro" | "silver"


CAR_SEED = [
    CarSeed("CAR-1", "KA-05-HH-1234", "Tata Ace", 82000, "green"),
    CarSeed("CAR-2", "MH-12-XY-7788", "Ashok Leyland Dost", 45000, "metro"),
    CarSeed("CAR-3", "KA-05-HH-5566", "Mahindra Bolero", 12000, "green"),
    CarSeed("CAR-4", "DL-8C-AB-1111", "Tata 407", 95000, "silver"),
    CarSeed("CAR-5", "DL-8C-AB-2222", "Ashok Leyland Partner", 30000, "silver"),
    CarSeed("CAR-6", "MH-12-XY-3333", "Eicher Pro", 60000, "metro"),
    CarSeed("CAR-7", "KA-05-HH-4444", "Tata Ace Gold", 15000, "green"),
    CarSeed("CAR-8", "MH-12-XY-5555", "Bharat Benz", 110000, "metro"),
    CarSeed("CAR-9", "DL-8C-AB-6666", "Mahindra Furio", 5000, "silver"),
    CarSeed("CAR-10", "KA-05-HH-7777", "Tata 1109", 72000, "green"),
    CarSeed("CAR-11", "MH-12-XY-8888", "Ashok Leyland Ecomet", 88000, "metro"),
    CarSeed("CAR-12", "DL-8C-AB-9999", "Eicher Skyline", 40000, "silver"),
]
TATA_MODELS = {seed.model for seed in CAR_SEED if seed.model.startswith("Tata")}


# ── Fake roles manager — an explicit, editable permission matrix ────────────


@dataclass
class FieldRule:
    can_view: bool = False
    mask_value: bool = False
    can_edit: bool = False


@dataclass
class RolePermissions:
    """One role's configured access, in the exact shape `roles_manager` normally
    computes from DB rows — `entity_access` keyed by (entity_type_name, action),
    `fields` keyed by entity_type_name then field_name, `conditions` keyed by
    entity_type_name (a row-scoping filter — real data example: `eye_nurse`'s
    condition on `patient.doctor_department == 'Eyee'`, where `doctor_department`
    is itself an inherited field — the condition doesn't care where a field came
    from, only its value on the fully-merged record)."""

    entity_access: dict[tuple[str, str], bool] = field(default_factory=dict)
    fields: dict[str, dict[str, FieldRule]] = field(default_factory=dict)
    conditions: dict[str, list[EntityConditionSpec]] = field(default_factory=dict)

    def allow(self, entity_type: str, *actions: str) -> "RolePermissions":
        for action in actions:
            self.entity_access[(entity_type, action)] = True
        return self

    def field(
        self,
        entity_type: str,
        field_name: str,
        *,
        view: bool = False,
        masked: bool = False,
        edit: bool = False,
    ) -> "RolePermissions":
        self.fields.setdefault(entity_type, {})[field_name] = FieldRule(view, masked, edit)
        return self

    def condition(
        self, entity_type: str, entity_field: str, operator: str, condition_value: str
    ) -> "RolePermissions":
        """Row-scoping filter on `entity_type` — `entity_field` can be a native or
        an inherited field name, matching real usage (`eye_nurse`/`leg_nurse` scope
        `patient` by `doctor_department`, an inherited field)."""
        self.conditions.setdefault(entity_type, []).append(
            EntityConditionSpec(
                entity_field=entity_field, operator=operator, condition_value=condition_value
            )
        )
        return self


class FakeRolesManager:
    """Implements the exact `RolesServiceProtocol` surface `entities/manager.py`
    calls, backed by an in-memory `{role_name: RolePermissions}` matrix instead
    of real `roles`/`field_permissions` rows — a role's permissions can be
    edited between two calls in the same test, with no DB round-trip at all.
    A role with zero rows for a field (not present in `fields`) behaves like a
    real non-system role with no configured row: no view access, same as
    production `get_visible_fields`/`get_masked_fields` for that field."""

    def __init__(self) -> None:
        self.roles: dict[str, RolePermissions] = {}
        self.workflow_service_manager = None

    def set_role(self, role_name: str, permissions: RolePermissions) -> None:
        self.roles[role_name] = permissions

    def get_workflow_access_scope(self, actor: dict[str, object]) -> set[str] | None:
        return None

    def evaluate_entity_access(self, db, user_id, org_id, entity_type, action) -> EntityAccessCheck:
        allowed = self.roles[user_id].entity_access.get((entity_type, action), False)
        return EntityAccessCheck(allowed=allowed, conditions=[])

    def check_entity_permission(self, db, user_id, org_id, entity_type, action) -> bool:
        return self.roles[user_id].entity_access.get((entity_type, action), False)

    def get_visible_fields(self, db, user_id, org_id, entity_type) -> list[str]:
        fields = self.roles[user_id].fields.get(entity_type, {})
        return [name for name, rule in fields.items() if rule.can_view]

    def get_masked_fields(self, db, user_id, org_id, entity_type) -> list[str]:
        fields = self.roles[user_id].fields.get(entity_type, {})
        return [name for name, rule in fields.items() if rule.can_view and rule.mask_value]

    def get_editable_fields(self, db, user_id, org_id, entity_type) -> list[str]:
        fields = self.roles[user_id].fields.get(entity_type, {})
        return [name for name, rule in fields.items() if rule.can_edit]

    def resolve_entity_read_policies(self, db, user_id, org_id, entity_types) -> dict[str, EntityReadPolicy]:
        role = self.roles[user_id]
        policies: dict[str, EntityReadPolicy] = {}
        for entity_type in entity_types:
            if not role.entity_access.get((entity_type, "view"), False):
                continue
            fields = role.fields.get(entity_type, {})
            policies[entity_type] = EntityReadPolicy(
                conditions=list(role.conditions.get(entity_type, [])),
                visible_fields={n for n, r in fields.items() if r.can_view},
                masked_fields={n for n, r in fields.items() if r.can_view and r.mask_value},
            )
        return policies


def _actor(user_id: str, org_id: str) -> dict[str, object]:
    return {"user_id": user_id, "organization_id": org_id, "actor_type": "user"}


def _assert_fields(data: dict[str, object], expected: dict[str, object | None]) -> None:
    """Check only the fields this test cares about — `None` means the key must
    be completely absent (denied), otherwise the value must match exactly
    (real value, or `MASKED_FIELD_VALUE`). Fields not mentioned (e.g. the
    auto-exposed `<parent_type>_id`, unrelated to this feature) are ignored."""
    for key, value in expected.items():
        if value is None:
            assert key not in data, f"expected '{key}' to be absent, got {data.get(key)!r}"
        else:
            assert data.get(key) == value, f"'{key}': expected {value!r}, got {data.get(key)!r}"


# ── Fixtures — real Postgres, real manager, fresh throwaway org ─────────────


@pytest.fixture(scope="module")
def rbac_org(entities_db_service_manager) -> Iterator[str]:
    engine = entities_db_service_manager.postgres_db_service().engine
    org_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text(
                f'INSERT INTO "{APP_SCHEMA}".organizations (id, name, slug, settings, status) '
                f"VALUES (:id, :name, :slug, '{{}}', 'active')"
            ),
            {"id": org_id, "name": "Inherited Field RBAC Matrix Org", "slug": f"ifr-matrix-{org_id[:8]}"},
        )
    yield org_id
    with engine.begin() as conn:
        conn.execute(
            text(f'DELETE FROM "{APP_SCHEMA}_runtime".entity_relations WHERE organization_id = :id'),
            {"id": org_id},
        )
        conn.execute(
            text(f'DELETE FROM "{APP_SCHEMA}_runtime".entities WHERE organization_id = :id'),
            {"id": org_id},
        )
        conn.execute(
            text(f'DELETE FROM "{APP_SCHEMA}_definitions".entity_type_relations WHERE organization_id = :id'),
            {"id": org_id},
        )
        conn.execute(
            text(f'DELETE FROM "{APP_SCHEMA}_definitions".entity_types WHERE organization_id = :id'),
            {"id": org_id},
        )
        conn.execute(text(f'DELETE FROM "{APP_SCHEMA}".organizations WHERE id = :id'), {"id": org_id})


@pytest.fixture(scope="module")
def roles_manager() -> FakeRolesManager:
    return FakeRolesManager()


@pytest.fixture(scope="module")
def manager(entities_db_service_manager, roles_manager) -> EntitiesServiceManager:
    db_service = EntitiesModelService(database_service_manager=entities_db_service_manager)
    svc = EntitiesServiceManager(
        db_service,
        database_service_manager=entities_db_service_manager,
        config=Configuration(),
        roles_manager=roles_manager,
    )
    svc.start()
    return svc


@dataclass
class Fixture:
    org_id: str
    vehicle_company_type_id: str
    car_type_id: str
    car_snapshot_type_id: str
    empty_type_id: str
    green_id: str
    metro_id: str
    silver_id: str
    car1_id: str
    car2_id: str
    car_snapshot1_id: str
    company_ids: dict[str, str]  # company_key -> entity_id, all 3
    car_ids: dict[str, str]  # identifier -> entity_id, all 12


SETUP_ACTOR_ID = "setup_admin"


@pytest.fixture(scope="module")
def fixture_data(manager: EntitiesServiceManager, roles_manager: FakeRolesManager, rbac_org: str) -> Fixture:
    """Build the Vehicle_Company / Car / CarLeaseSnapshot use case once for the
    whole module: two entity types feeding a REFERENCE accepter (Car) and a
    SNAPSHOT accepter (CarLeaseSnapshot), plus the sample rows from the design
    doc. Uses a throwaway, fully-privileged `setup_admin` role — the actual
    roles under test are configured fresh per test via `configured_roles`."""
    org_id = rbac_org
    setup_actor = _actor(SETUP_ACTOR_ID, org_id)
    roles_manager.set_role(
        SETUP_ACTOR_ID,
        RolePermissions()
        .allow("Vehicle_Company", "view", "create", "edit")
        .allow("Car", "view", "create", "edit")
        .allow("CarLeaseSnapshot", "view", "create", "edit")
        .field("Vehicle_Company", "company_name", view=True, edit=True)
        .field("Vehicle_Company", "registration_number", view=True, edit=True)
        .field("Vehicle_Company", "safety_rating", view=True, edit=True)
        .field("Vehicle_Company", "fleet_size", view=True, edit=True)
        .field("Car", "license_plate", view=True, edit=True)
        .field("Car", "model", view=True, edit=True)
        .field("Car", "mileage", view=True, edit=True)
        .field("CarLeaseSnapshot", "lease_id", view=True, edit=True),
    )

    vehicle_company = manager.create_entity_type_for_actor(
        setup_actor,
        EntityTypeCreateRequest(
            organization_id=org_id,
            name="Vehicle_Company",
            schema_definition={
                "fields": [
                    {"name": "company_name", "type": "string"},
                    {"name": "registration_number", "type": "string"},
                    {"name": "safety_rating", "type": "string"},
                    {"name": "fleet_size", "type": "number"},
                ]
            },
        ),
    )
    car = manager.create_entity_type_for_actor(
        setup_actor,
        EntityTypeCreateRequest(
            organization_id=org_id,
            name="Car",
            schema_definition={
                "fields": [
                    {"name": "license_plate", "type": "string"},
                    {"name": "model", "type": "string"},
                    {"name": "mileage", "type": "number"},
                ]
            },
        ),
    )
    car_snapshot = manager.create_entity_type_for_actor(
        setup_actor,
        EntityTypeCreateRequest(
            organization_id=org_id,
            name="CarLeaseSnapshot",
            schema_definition={"fields": [{"name": "lease_id", "type": "string"}]},
        ),
    )
    # No relation, no records, ever — exists purely so a list call against it
    # always returns zero rows, to prove permission is still checked even when
    # the fetch comes back empty (PR review finding, fixed 2026-08-14).
    empty_type = manager.create_entity_type_for_actor(
        setup_actor,
        EntityTypeCreateRequest(
            organization_id=org_id,
            name="EmptyType",
            schema_definition={"fields": [{"name": "note", "type": "string"}]},
        ),
    )

    inheritance_mapping = {
        "Vehicle_Company.company_name": "Car.owner_company_name",
        "Vehicle_Company.registration_number": "Car.owner_registration_number",
        "Vehicle_Company.safety_rating": "Car.owner_safety_rating",
    }
    manager.create_entity_relation_declaration_for_actor(
        setup_actor,
        EntityRelationDeclarationCreateRequest(
            organization_id=org_id,
            from_entity_type_id=vehicle_company.entity_type_id,
            to_entity_type_id=car.entity_type_id,
            relation_type="REFERENCE",
            relation_metadata=inheritance_mapping,
        ),
    )
    manager.create_entity_relation_declaration_for_actor(
        setup_actor,
        EntityRelationDeclarationCreateRequest(
            organization_id=org_id,
            from_entity_type_id=vehicle_company.entity_type_id,
            to_entity_type_id=car_snapshot.entity_type_id,
            relation_type="SNAPSHOT",
            relation_metadata={
                "Vehicle_Company.company_name": "CarLeaseSnapshot.owner_company_name",
                "Vehicle_Company.registration_number": "CarLeaseSnapshot.owner_registration_number",
                "Vehicle_Company.safety_rating": "CarLeaseSnapshot.owner_safety_rating",
            },
        ),
    )

    def _create_company(identifier: str, name: str, reg: str, rating: str, fleet: int) -> str:
        record = manager.create_entity_record_for_actor(
            setup_actor,
            EntityRecordCreateRequest(
                organization_id=org_id,
                entity_type_id=vehicle_company.entity_type_id,
                data={
                    "identifier": identifier,
                    "company_name": name,
                    "registration_number": reg,
                    "safety_rating": rating,
                    "fleet_size": fleet,
                },
            ),
        )
        return record.entity_id

    company_ids: dict[str, str] = {
        seed.key: _create_company(
            seed.identifier, seed.name, seed.registration_number, seed.safety_rating, seed.fleet_size
        )
        for seed in COMPANY_SEED
    }
    green_id = company_ids["green"]
    metro_id = company_ids["metro"]
    silver_id = company_ids["silver"]

    def _create_car(identifier: str, plate: str, model: str, mileage: int, source_id: str) -> str:
        record = manager.create_entity_record_for_actor(
            setup_actor,
            EntityRecordCreateRequest(
                organization_id=org_id,
                entity_type_id=car.entity_type_id,
                data={"identifier": identifier, "license_plate": plate, "model": model, "mileage": mileage},
                source_entity_ids=[source_id],
            ),
        )
        return record.entity_id

    car_ids: dict[str, str] = {
        seed.identifier: _create_car(
            seed.identifier, seed.plate, seed.model, seed.mileage, company_ids[seed.company_key]
        )
        for seed in CAR_SEED
    }
    car1_id = car_ids["CAR-1"]
    car2_id = car_ids["CAR-2"]

    snapshot_record = manager.create_entity_record_for_actor(
        setup_actor,
        EntityRecordCreateRequest(
            organization_id=org_id,
            entity_type_id=car_snapshot.entity_type_id,
            data={"identifier": "LEASE-1", "lease_id": "LEASE-001"},
            source_entity_ids=[green_id],
        ),
    )

    return Fixture(
        org_id=org_id,
        vehicle_company_type_id=vehicle_company.entity_type_id,
        car_type_id=car.entity_type_id,
        car_snapshot_type_id=car_snapshot.entity_type_id,
        empty_type_id=empty_type.entity_type_id,
        green_id=green_id,
        metro_id=metro_id,
        silver_id=silver_id,
        car1_id=car1_id,
        car2_id=car2_id,
        car_snapshot1_id=snapshot_record.entity_id,
        company_ids=company_ids,
        car_ids=car_ids,
    )


@pytest.fixture
def configured_roles(roles_manager: FakeRolesManager) -> FakeRolesManager:
    """Reset the 4 roles under test to the design doc's matrix before every
    test, so no test can leak a mid-test permission edit into the next one."""
    fleet_auditor = (
        RolePermissions()
        .allow("Vehicle_Company", "view")
        .allow("Car", "view", "create", "edit")
        .allow("CarLeaseSnapshot", "view")
        .field("Vehicle_Company", "company_name", view=True)
        .field("Vehicle_Company", "registration_number", view=True)
        .field("Vehicle_Company", "safety_rating", view=True)
        .field("Car", "license_plate", view=True, edit=True)
        .field("Car", "model", view=True, edit=True)
        .field("Car", "mileage", view=True, edit=True)
    )
    sales_rep = (
        RolePermissions()
        .allow("Vehicle_Company", "view")
        .allow("Car", "view", "create", "edit")
        .allow("CarLeaseSnapshot", "view")
        .field("Vehicle_Company", "company_name", view=True)
        .field("Vehicle_Company", "safety_rating", view=True, masked=True)
        .field("Car", "license_plate", view=True, edit=True)
        .field("Car", "model", view=True, edit=True)
    )
    compliance_officer = (
        RolePermissions()
        .allow("Vehicle_Company", "view")
        .allow("Car", "view", "create", "edit")
        .allow("CarLeaseSnapshot", "view")
        .field("Vehicle_Company", "company_name", view=True)
        .field("Vehicle_Company", "registration_number", view=True)
        .field("Vehicle_Company", "safety_rating", view=True)
        .field("Vehicle_Company", "fleet_size", view=True, masked=True)
        .field("Car", "license_plate", view=True, edit=True)
        .field("Car", "model", view=True, edit=True)
        .field("Car", "mileage", view=True, masked=True, edit=True)
    )
    outside_viewer = (
        RolePermissions()
        .allow("Car", "view")
        .field("Car", "license_plate", view=True)
        .field("Car", "model", view=True)
        .field("Car", "mileage", view=True)
        # Deliberately no `.allow("Vehicle_Company", "view")` at all — the
        # entity-level gate, not the field-level one, must be what blocks this.
    )
    # regional_auditor: mirrors real `eye_nurse`/`leg_nurse` usage — a row
    # condition on the TARGET type (Car), scoped by an INHERITED field name
    # (owner_safety_rating, sourced from Vehicle_Company.safety_rating). Proves
    # field-value filtration doesn't care whether a field is owned or inherited —
    # once merged, it's just a field on the Car record, checked against the
    # condition on Car's own policy (see Edge Case M in the design doc).
    regional_auditor = (
        RolePermissions()
        .allow("Vehicle_Company", "view")
        .allow("Car", "view")
        .field("Vehicle_Company", "safety_rating", view=True)
        .field("Car", "license_plate", view=True)
        .field("Car", "model", view=True)
        .field("Car", "mileage", view=True)
        .condition("Car", "owner_safety_rating", "==", "A")
    )
    # fleet_manager: the symmetric case — a row condition on Car scoped by an
    # OWNED field (model), using the "in" operator over a comma-separated list.
    # No Vehicle_Company access needed at all here — proves the condition
    # mechanism doesn't care about inheritance one way or the other; it just
    # checks the merged record's value for whatever field the condition names.
    fleet_manager = (
        RolePermissions()
        .allow("Car", "view")
        .field("Car", "license_plate", view=True)
        .field("Car", "model", view=True)
        .field("Car", "mileage", view=True)
        .condition("Car", "model", "in", ",".join(sorted(TATA_MODELS)))
    )
    roles_manager.set_role("fleet_auditor", fleet_auditor)
    roles_manager.set_role("sales_rep", sales_rep)
    roles_manager.set_role("compliance_officer", compliance_officer)
    roles_manager.set_role("outside_viewer", outside_viewer)
    roles_manager.set_role("regional_auditor", regional_auditor)
    roles_manager.set_role("fleet_manager", fleet_manager)
    return roles_manager


ROLES = ["fleet_auditor", "sales_rep", "compliance_officer"]

# Expected Car inherited-field projection per role, keyed by role name — the
# governing table from the design doc's RBAC matrix.
EXPECTED_CAR_INHERITED = {
    "fleet_auditor": {
        "owner_company_name": "GreenLine Logistics",
        "owner_registration_number": "VC-2291-KA",
        "owner_safety_rating": "A",
    },
    "sales_rep": {
        "owner_company_name": "GreenLine Logistics",
        "owner_registration_number": None,
        "owner_safety_rating": MASKED,
    },
    "compliance_officer": {
        "owner_company_name": "GreenLine Logistics",
        "owner_registration_number": "VC-2291-KA",
        "owner_safety_rating": "A",
    },
}
EXPECTED_CAR_OWN = {
    "fleet_auditor": {"license_plate": "KA-05-HH-1234", "model": "Tata Ace", "mileage": 82000},
    "sales_rep": {"license_plate": "KA-05-HH-1234", "model": "Tata Ace", "mileage": None},
    "compliance_officer": {"license_plate": "KA-05-HH-1234", "model": "Tata Ace", "mileage": MASKED},
}
EXPECTED_VEHICLE_COMPANY = {
    "fleet_auditor": {
        "company_name": "GreenLine Logistics",
        "registration_number": "VC-2291-KA",
        "safety_rating": "A",
        "fleet_size": None,
    },
    "sales_rep": {
        "company_name": "GreenLine Logistics",
        "registration_number": None,
        "safety_rating": MASKED,
        "fleet_size": None,
    },
    "compliance_officer": {
        "company_name": "GreenLine Logistics",
        "registration_number": "VC-2291-KA",
        "safety_rating": "A",
        "fleet_size": MASKED,
    },
}


# ═════════════════════════════════════════════════════════════════════════
# GET /entity-records (list, by entity_type_id) — Vehicle_Company (the source
# itself — a plain regression guard that native-field masking is unaffected)
# ═════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("role", ROLES)
def test_list_vehicle_company_own_fields_unaffected(
    manager, configured_roles, fixture_data: Fixture, role: str
) -> None:
    actor = _actor(role, fixture_data.org_id)
    result = manager.list_entity_records_for_actor(
        actor, entity_type_id=fixture_data.vehicle_company_type_id
    )
    by_id = {item.entity_id: item.data for item in result.items}
    assert fixture_data.green_id in by_id
    _assert_fields(by_id[fixture_data.green_id], EXPECTED_VEHICLE_COMPANY[role])


# ═════════════════════════════════════════════════════════════════════════
# GET /entity-records (list, by entity_type_id) — Car: the inherited fields
# must follow Vehicle_Company's own rules, never Car's own field_permissions
# ═════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("role", ROLES)
def test_list_car_by_type_id_inherits_source_permission(
    manager, configured_roles, fixture_data: Fixture, role: str
) -> None:
    actor = _actor(role, fixture_data.org_id)
    result = manager.list_entity_records_for_actor(actor, entity_type_id=fixture_data.car_type_id)
    by_id = {item.entity_id: item.data for item in result.items}
    assert {fixture_data.car1_id, fixture_data.car2_id} <= set(by_id)
    _assert_fields(by_id[fixture_data.car1_id], EXPECTED_CAR_OWN[role])
    _assert_fields(by_id[fixture_data.car1_id], EXPECTED_CAR_INHERITED[role])
    # fleet_size was never part of the relation — must never appear, for anyone.
    assert "fleet_size" not in by_id[fixture_data.car1_id]
    assert "owner_fleet_size" not in by_id[fixture_data.car1_id]


def test_list_car_by_type_name_matches_by_type_id(
    manager, configured_roles, fixture_data: Fixture
) -> None:
    """Path B (`entity_type_name=`) must agree with Path A on the same record —
    same manager method (`_apply_field_permissions`), different type lookup."""
    actor = _actor("sales_rep", fixture_data.org_id)
    by_name = manager.list_entity_records_by_type_name_for_actor(actor, "Car")
    by_id = manager.list_entity_records_for_actor(actor, entity_type_id=fixture_data.car_type_id)
    name_data = {item.entity_id: item.data for item in by_name.items}
    id_data = {item.entity_id: item.data for item in by_id.items}
    assert name_data[fixture_data.car1_id] == id_data[fixture_data.car1_id]


# ═════════════════════════════════════════════════════════════════════════
# GET /entity-records/{id} — get-one, both Vehicle_Company and Car
# ═════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("role", ROLES)
def test_get_one_vehicle_company(manager, configured_roles, fixture_data: Fixture, role: str) -> None:
    actor = _actor(role, fixture_data.org_id)
    record = manager.get_entity_record_for_actor(actor, fixture_data.green_id)
    _assert_fields(record.data, EXPECTED_VEHICLE_COMPANY[role])


@pytest.mark.parametrize("role", ROLES)
def test_get_one_car_reference(manager, configured_roles, fixture_data: Fixture, role: str) -> None:
    actor = _actor(role, fixture_data.org_id)
    record = manager.get_entity_record_for_actor(actor, fixture_data.car1_id)
    _assert_fields(record.data, EXPECTED_CAR_OWN[role])
    _assert_fields(record.data, EXPECTED_CAR_INHERITED[role])


@pytest.mark.parametrize("role", ROLES)
def test_get_one_car_snapshot_same_rule_as_reference(
    manager, configured_roles, fixture_data: Fixture, role: str
) -> None:
    """SNAPSHOT accepter: the inherited *value* is frozen at link time, but the
    governing rule (design doc) is that the *permission* decision is still the
    source type's own current rule, resolved live — identical outcome to the
    REFERENCE case for the same role/source-field."""
    actor = _actor(role, fixture_data.org_id)
    record = manager.get_entity_record_for_actor(actor, fixture_data.car_snapshot1_id)
    _assert_fields(record.data, EXPECTED_CAR_INHERITED[role])


def test_get_one_car_denied_when_actor_has_no_entity_access_to_source_type(
    manager, configured_roles, fixture_data: Fixture
) -> None:
    """The entity-level gate: `outside_viewer` can read Car directly, has no
    per-field rows configured for the inherited keys at all (irrelevant —
    there's no view access to Vehicle_Company as a type, full stop), so every
    inherited field must be dropped regardless of any field-level state."""
    actor = _actor("outside_viewer", fixture_data.org_id)
    record = manager.get_entity_record_for_actor(actor, fixture_data.car1_id)
    assert record.data["license_plate"] == "KA-05-HH-1234"
    _assert_fields(
        record.data,
        {"owner_company_name": None, "owner_registration_number": None, "owner_safety_rating": None},
    )


def test_list_denied_target_raises_even_with_zero_records(
    manager, configured_roles, fixture_data: Fixture
) -> None:
    """PR review finding, fixed 2026-08-14: the entity-level gate must raise for a
    denied actor regardless of whether the type currently has any records at all.
    Before the fix, `resolve_records_for_actor` only checked permission by looking
    at the fetched records — an empty fetch meant no records to derive a type
    from, so the check was skipped entirely and a denied actor got a silent,
    empty 200 instead of a 403. `EmptyType` has zero records, ever, and
    `outside_viewer` has no `view` access to it at all — must still 403, not
    return an empty list, proving the check no longer depends on record count."""
    actor = _actor("outside_viewer", fixture_data.org_id)
    with pytest.raises(AuthorizationError):
        manager.list_entity_records_for_actor(actor, entity_type_id=fixture_data.empty_type_id)


# ═════════════════════════════════════════════════════════════════════════
# Field-value filtration (Gate 4), across the full 12-car dataset — two roles,
# two different kinds of condition field, same mechanism:
#   - regional_auditor: condition on an INHERITED field (owner_safety_rating,
#     sourced from Vehicle_Company.safety_rating). Mirrors real `eye_nurse`/
#     `leg_nurse` usage (their condition is on `patient.doctor_department`,
#     also inherited).
#   - fleet_manager: condition on an OWNED field (model), the symmetric case —
#     proves the same mechanism works identically regardless of field origin.
# Field origin (owned vs inherited) is irrelevant; only the merged record's
# value matters.
# ═════════════════════════════════════════════════════════════════════════

REGIONAL_AUDITOR_KEPT = {
    seed.identifier for seed in CAR_SEED
    if next(c.safety_rating for c in COMPANY_SEED if c.key == seed.company_key) == "A"
}
FLEET_MANAGER_KEPT = {seed.identifier for seed in CAR_SEED if seed.model in TATA_MODELS}


def test_list_car_filters_by_condition_on_inherited_field(
    manager, configured_roles, fixture_data: Fixture
) -> None:
    actor = _actor("regional_auditor", fixture_data.org_id)
    result = manager.list_entity_records_for_actor(actor, entity_type_id=fixture_data.car_type_id)
    by_id = {item.entity_id for item in result.items}
    kept_ids = {fixture_data.car_ids[identifier] for identifier in REGIONAL_AUDITOR_KEPT}
    discarded_ids = {
        entity_id for identifier, entity_id in fixture_data.car_ids.items()
        if identifier not in REGIONAL_AUDITOR_KEPT
    }
    assert kept_ids <= by_id, "every car linked to an 'A'-rated company must be kept"
    assert not (discarded_ids & by_id), "every car linked to a non-'A'-rated company must be filtered out"


def test_get_one_car_matching_condition_on_inherited_field_is_kept(
    manager, configured_roles, fixture_data: Fixture
) -> None:
    actor = _actor("regional_auditor", fixture_data.org_id)
    record = manager.get_entity_record_for_actor(actor, fixture_data.car1_id)
    assert record.data["owner_safety_rating"] == "A"


def test_get_one_car_failing_condition_on_inherited_field_is_denied(
    manager, configured_roles, fixture_data: Fixture
) -> None:
    actor = _actor("regional_auditor", fixture_data.org_id)
    with pytest.raises(AuthorizationError):
        manager.get_entity_record_for_actor(actor, fixture_data.car2_id)


def test_list_car_filters_by_condition_on_owned_field(
    manager, configured_roles, fixture_data: Fixture
) -> None:
    actor = _actor("fleet_manager", fixture_data.org_id)
    result = manager.list_entity_records_for_actor(actor, entity_type_id=fixture_data.car_type_id)
    by_id = {item.entity_id for item in result.items}
    kept_ids = {fixture_data.car_ids[identifier] for identifier in FLEET_MANAGER_KEPT}
    discarded_ids = {
        entity_id for identifier, entity_id in fixture_data.car_ids.items()
        if identifier not in FLEET_MANAGER_KEPT
    }
    assert kept_ids <= by_id, "every Tata-model car must be kept"
    assert not (discarded_ids & by_id), "every non-Tata-model car must be filtered out"
    assert len(kept_ids) == 4, "sanity check on the seed data itself, not just the filter"


def test_get_one_car_matching_condition_on_owned_field_is_kept(
    manager, configured_roles, fixture_data: Fixture
) -> None:
    actor = _actor("fleet_manager", fixture_data.org_id)
    tata_identifier = next(iter(FLEET_MANAGER_KEPT))
    record = manager.get_entity_record_for_actor(actor, fixture_data.car_ids[tata_identifier])
    assert record.data["model"] in TATA_MODELS


def test_get_one_car_failing_condition_on_owned_field_is_denied(
    manager, configured_roles, fixture_data: Fixture
) -> None:
    actor = _actor("fleet_manager", fixture_data.org_id)
    non_tata_identifier = next(
        seed.identifier for seed in CAR_SEED if seed.identifier not in FLEET_MANAGER_KEPT
    )
    with pytest.raises(AuthorizationError):
        manager.get_entity_record_for_actor(actor, fixture_data.car_ids[non_tata_identifier])


# ═════════════════════════════════════════════════════════════════════════
# GET /entity-records/summary — page-batched policy path
# ═════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("role", ROLES)
def test_summary_car_respects_source_permission(
    manager, configured_roles, fixture_data: Fixture, role: str
) -> None:
    actor = _actor(role, fixture_data.org_id)
    page = manager.list_entity_record_summaries_for_actor(
        actor,
        entity_type_id=fixture_data.car_type_id,
        fields={
            "license_plate",
            "model",
            "mileage",
            "owner_company_name",
            "owner_registration_number",
            "owner_safety_rating",
        },
        limit=20,
    )
    by_id = {item.entity_id: item.summary_fields for item in page.items}
    assert fixture_data.car1_id in by_id
    _assert_fields(by_id[fixture_data.car1_id], EXPECTED_CAR_OWN[role])
    _assert_fields(by_id[fixture_data.car1_id], EXPECTED_CAR_INHERITED[role])


def test_summary_explicit_field_request_does_not_bypass_denial(
    manager, configured_roles, fixture_data: Fixture
) -> None:
    """`fields=` is opt-in only, never a way around the permission — sales_rep
    has no view access to Vehicle_Company.registration_number at all, so
    explicitly asking for its inherited copy still yields nothing."""
    actor = _actor("sales_rep", fixture_data.org_id)
    page = manager.list_entity_record_summaries_for_actor(
        actor,
        entity_type_id=fixture_data.car_type_id,
        fields={"owner_registration_number"},
        limit=20,
    )
    by_id = {item.entity_id: item.summary_fields for item in page.items}
    assert "owner_registration_number" not in by_id[fixture_data.car1_id]


# ═════════════════════════════════════════════════════════════════════════
# POST /entity-records — create response must match a subsequent GET
# ═════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("role", ROLES)
def test_create_car_response_matches_subsequent_get(
    manager, configured_roles, fixture_data: Fixture, role: str
) -> None:
    # Only license_plate/model are sent — every role in the matrix can edit
    # both; mileage is deliberately excluded here since sales_rep has no edit
    # access to it at all (a write-boundary concern, not what this test
    # covers — this test is about the create *response's* masking, not which
    # fields a role may send).
    actor = _actor(role, fixture_data.org_id)
    created = manager.create_entity_record_for_actor(
        actor,
        EntityRecordCreateRequest(
            organization_id=fixture_data.org_id,
            entity_type_id=fixture_data.car_type_id,
            data={
                "identifier": f"CAR-CREATE-{role}",
                "license_plate": "KA-99-ZZ-0001",
                "model": "Mahindra Bolero",
            },
            source_entity_ids=[fixture_data.green_id],
        ),
    )
    fetched = manager.get_entity_record_for_actor(actor, created.entity_id)
    assert created.data == fetched.data, (
        "create response must never show more (or less) than a subsequent GET "
        "of the same record would"
    )
    _assert_fields(created.data, EXPECTED_CAR_INHERITED[role])


# ═════════════════════════════════════════════════════════════════════════
# PUT /entity-records/{id} — update response reuses the same masking as GET
# ═════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("role", ROLES)
def test_update_car_response_still_masks_inherited_fields(
    manager, configured_roles, fixture_data: Fixture, role: str
) -> None:
    actor = _actor(role, fixture_data.org_id)
    updated = manager.update_entity_record_for_actor(
        actor,
        fixture_data.car1_id,
        EntityRecordUpdateRequest(data={"model": "Tata Ace (Updated)"}),
    )
    assert updated.data["model"] == "Tata Ace (Updated)"
    _assert_fields(updated.data, EXPECTED_CAR_INHERITED[role])
    # Restore for subsequent tests sharing this fixture record.
    manager.update_entity_record_for_actor(
        actor, fixture_data.car1_id, EntityRecordUpdateRequest(data={"model": "Tata Ace"})
    )


# ═════════════════════════════════════════════════════════════════════════
# Live-resolution proof — a permission change is reflected immediately, on
# both the REFERENCE (Car) and SNAPSHOT (CarLeaseSnapshot) accepters, even
# though the SNAPSHOT's own inherited *value* is frozen and never changes
# ═════════════════════════════════════════════════════════════════════════


def test_permission_change_is_reflected_live_not_cached(
    manager, configured_roles, fixture_data: Fixture
) -> None:
    actor = _actor("compliance_officer", fixture_data.org_id)

    # Baseline: compliance_officer's Vehicle_Company.safety_rating is visible,
    # unmasked — both accepters show the real letter grade.
    before_car = manager.get_entity_record_for_actor(actor, fixture_data.car1_id)
    before_snapshot = manager.get_entity_record_for_actor(actor, fixture_data.car_snapshot1_id)
    assert before_car.data["owner_safety_rating"] == "A"
    assert before_snapshot.data["owner_safety_rating"] == "A"

    # Admin changes compliance_officer's access to Vehicle_Company.safety_rating
    # from visible to masked — no re-login, no cache to invalidate.
    configured_roles.roles["compliance_officer"].field(
        "Vehicle_Company", "safety_rating", view=True, masked=True
    )

    after_car = manager.get_entity_record_for_actor(actor, fixture_data.car1_id)
    after_snapshot = manager.get_entity_record_for_actor(actor, fixture_data.car_snapshot1_id)
    assert after_car.data["owner_safety_rating"] == MASKED, (
        "REFERENCE accepter must reflect the new source-side rule immediately"
    )
    assert after_snapshot.data["owner_safety_rating"] == MASKED, (
        "SNAPSHOT accepter's inherited VALUE is frozen, but the PERMISSION "
        "decision is still resolved live against the source type's current "
        "rule — must flip exactly like the REFERENCE case"
    )
