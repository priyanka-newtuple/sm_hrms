from __future__ import annotations

from typing import Any

from entities.manager import EntitiesServiceManager
from entities.models.response import EntityRecordResponse


class _FieldRestrictedRolesManager:
    def get_visible_fields(
        self, db: Any, user_id: str, org_id: str, entity_type: str
    ) -> list[str]:
        return ["visible_field"]

    def get_masked_fields(
        self, db: Any, user_id: str, org_id: str, entity_type: str
    ) -> list[str]:
        return ["identifier", "visible_field"]


class _NoInheritanceDbModelService:
    """This test's `candidate` entity type has no relation declarations at all —
    `_apply_field_permissions` now looks these up (via
    `InheritedFieldPermissionsService`) for every entity type, so the fake must
    answer that lookup, not just be a bare `object()`."""

    def get_active_relation_declarations_by_to_type(
        self, *, organization_id: str, to_entity_type_id: str
    ) -> list[Any]:
        return []


def test_entity_field_filter_always_preserves_unmasked_identifier() -> None:
    manager = EntitiesServiceManager(
        entities_db_model_service=_NoInheritanceDbModelService(),
        database_service_manager=None,
        config=None,
        roles_manager=_FieldRestrictedRolesManager(),
    )
    response = EntityRecordResponse(
        entity_id="entity-1",
        organization_id="org-1",
        entity_type_id="type-1",
        data={
            "identifier": "CAND-001",
            "visible_field": "visible",
            "hidden_field": "hidden",
        },
    )

    filtered = manager._apply_field_permissions(
        db=object(),
        actor={"user_id": "viewer-1"},
        org_id="org-1",
        entity_type_name="candidate",
        response=response,
    )

    assert filtered.data == {
        "identifier": "CAND-001",
        "visible_field": "***",
    }
