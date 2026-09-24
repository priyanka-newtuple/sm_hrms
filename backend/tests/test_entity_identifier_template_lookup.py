from __future__ import annotations

from entities.manager import EntitiesServiceManager

ACTOR = {"organization_id": "org-1", "user_id": "user-1"}


class _FakeEntitiesDbModelService:
    def __init__(self, *, template: str | None, taken_identifiers: set[str]) -> None:
        self.template = template
        self.taken_identifiers = taken_identifiers

    def get_identifier_template(self, organization_id: str, entity_type_id: str) -> str | None:
        return self.template

    def identifier_exists(self, organization_id: str, entity_type_id: str, identifier: str) -> bool:
        return identifier in self.taken_identifiers


def _manager(*, template: str | None = None, taken: set[str] | None = None) -> EntitiesServiceManager:
    return EntitiesServiceManager(
        entities_db_model_service=_FakeEntitiesDbModelService(
            template=template, taken_identifiers=taken or set()
        ),
        database_service_manager=None,
        config=None,
    )


def test_get_identifier_template_for_actor_returns_none_in_manual_mode() -> None:
    manager = _manager(template=None)

    assert manager.get_identifier_template_for_actor(ACTOR, "type-1") is None


def test_get_identifier_template_for_actor_returns_the_configured_template() -> None:
    manager = _manager(template="CUST-{{seq}}")

    assert manager.get_identifier_template_for_actor(ACTOR, "type-1") == "CUST-{{seq}}"


def test_is_identifier_taken_for_actor_true_when_identifier_exists() -> None:
    manager = _manager(taken={"CAND-001"})

    assert manager.is_identifier_taken_for_actor(ACTOR, "type-1", "CAND-001") is True


def test_is_identifier_taken_for_actor_false_when_identifier_is_free() -> None:
    manager = _manager(taken={"CAND-001"})

    assert manager.is_identifier_taken_for_actor(ACTOR, "type-1", "CAND-002") is False
