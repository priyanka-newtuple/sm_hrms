"""Single construction point for `WorkflowServiceManager` in tests.

`WorkflowServiceManager.__init__` is keyword-only with ten required dependencies. Test
fixtures across four files had been constructing it positionally with a subset, which broke
silently at collection/setup time when the signature changed and left roughly fifty tests
dormant for months.

Every workflow test should build the manager through `make_workflow_manager` so that the
next constructor change is a one-line fix here instead of twenty-one scattered edits.

Deliberately not a pytest fixture: most call sites need a differently-configured DB fake per
test, which a factory expresses more directly than a fixture plus indirect parametrisation.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from common.protocols import EntityAccessCheck
from roles.models.interface import PermissionCheckResult
from workflow.manager import WorkflowServiceManager


class AllowAllRolesDbModelService:
    """Stands in for `RolesModelService` where the manager reaches through the roles manager.

    `_authorize_transition` calls `roles_manager.db_model_service.check_transition_permission`
    directly rather than through a manager method, so a roles double must expose this nested
    attribute to let any transition execute.
    """

    def check_transition_permission(self, *_args: Any, **_kwargs: Any) -> bool:
        return True


class UnrestrictedRolesManager:
    """Roles double that grants unrestricted workflow scope.

    `_authorize_workflow_access` dereferences `roles_manager` unconditionally, so a manager
    built without one cannot serve any actor-facing call. Returning `None` from
    `get_workflow_access_scope` matches the real contract's "no scoping rows configured"
    case, i.e. full access.
    """

    def __init__(self) -> None:
        self.cascade_calls: list[str] = []
        self.db_model_service = AllowAllRolesDbModelService()

    def get_workflow_access_scope(self, _actor: Any) -> set[str] | None:
        return None

    def check_permission_for_actor(self, _actor: Any, permission_key: str) -> PermissionCheckResult:
        """Grant every catalog permission.

        `enroll_entity_for_actor` gained an explicit `workflow:write` check (SEC-027), so a
        double that omits this method fails enrollment with an AttributeError rather than a
        permission decision.
        """
        return PermissionCheckResult.allow(permission_key)

    def cascade_workflow_publish(
        self,
        *,
        org_id: Any,
        machine_name: str,
        old_definition: Any,
        new_definition: Any,
    ) -> None:
        self.cascade_calls.append(machine_name)


class RecordingAuditService:
    """Audit double covering the two methods the workflow manager actually calls.

    Records emitted events so a test can assert audit side effects, and indexes them by
    idempotency key so the manager's replay short-circuit is exercisable. A double that always
    returned `None` from `find_by_idempotency_key` made idempotent replay untestable, because the
    audit store *is* the replay store.
    """

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.by_key: dict[str, Any] = {}

    def emit_audit_event(self, *args: Any, **kwargs: Any) -> Any:
        self.events.append({"args": args, "kwargs": kwargs})
        key = kwargs.get("idempotency_key")
        if key:
            # `find_successful_replay` reads `.entity_id`, `.event_type` and `.metadata` off the
            # stored record, so keep that shape rather than the raw call arguments.
            self.by_key.setdefault(
                str(key),
                SimpleNamespace(
                    entity_id=kwargs.get("entity_id"),
                    event_type=kwargs.get("event_type"),
                    # the manager emits this as `event_metadata`; the replay path reads `.metadata`
                    metadata=dict(kwargs.get("event_metadata") or kwargs.get("metadata") or {}),
                ),
            )
        return None

    def find_by_idempotency_key(self, *args: Any, **kwargs: Any) -> Any:
        key = kwargs.get("idempotency_key")
        if key is None and args:
            key = args[-1]
        return self.by_key.get(str(key)) if key is not None else None


class AllowAllEntityRolesManager(UnrestrictedRolesManager):
    """Roles double for an `EntitiesServiceManager` used inside workflow tests.

    `entities/manager.py` calls a wider surface than the workflow manager does. A test that
    wires an entities manager without a roles double fails with `AttributeError` on
    `evaluate_entity_access` rather than a permission decision, which reads like a product
    bug but is a fixture gap. Grants everything unconditionally and returns every requested
    field as visible, editable and unmasked.
    """

    def evaluate_entity_access(
        self, _db: Any, _user_id: Any, _org_id: Any, _entity_type: Any, _action: Any
    ) -> EntityAccessCheck:
        return EntityAccessCheck(allowed=True, conditions=[])

    def get_visible_fields(self, *_args: Any, **_kwargs: Any) -> None:
        """`None` means "no field restriction", distinct from `[]` which denies every field."""
        return None

    def get_editable_fields(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def get_masked_fields(self, *_args: Any, **_kwargs: Any) -> list[str]:
        return []


class NoActiveFormsManager:
    """Forms manager double: the entity type has no active form schema.

    The workflow manager asks the forms manager for the live form definition of an entity type
    so it can flag drift against a workflow's saved entity_schema. Tests that do not care about
    forms get this, which reports no active form and switches the drift check off — the same
    outcome as an entity type nobody has built a form for.
    """

    def __init__(self, schemas: list[Any] | None = None) -> None:
        self.schemas = schemas or []
        self.calls: list[tuple[str, str]] = []

    def get_active_entity_schemas(self, organization_id: str, entity_type: str) -> list[Any]:
        """Record the lookup and return whatever this double was seeded with."""
        self.calls.append((organization_id, entity_type))
        return [s for s in self.schemas if getattr(s, "entity_type", entity_type) == entity_type]


def make_workflow_manager(
    workflow_db_model_service: Any = None,
    database_service_manager: Any = None,
    **overrides: Any,
) -> WorkflowServiceManager:
    """Build a `WorkflowServiceManager` with test-safe defaults for every dependency.

    The two most commonly supplied dependencies are positional for convenience; everything
    else is an override. Unsupplied dependencies default to `None`, which is safe because
    the constructor only assigns them — except `roles_manager` and `audit_events_service`,
    which are dereferenced on common paths and therefore get working doubles.
    """
    dependencies: dict[str, Any] = {
        "workflow_db_model_service": workflow_db_model_service,
        "database_service_manager": database_service_manager,
        "config": None,
        "entities_service_manager": None,
        "roles_manager": UnrestrictedRolesManager(),
        "audit_events_service": RecordingAuditService(),
        "forms_service_manager": NoActiveFormsManager(),
        "filehandler_service_manager": None,
        "user_service_manager": None,
        "blob_storage_service": None,
        # Added on main by the Method Library feature; optional, so only publish flows that
        # pin methods need a real one.
        "method_library_db_model_service": None,
    }
    dependencies.update(overrides)
    return WorkflowServiceManager(**dependencies)
