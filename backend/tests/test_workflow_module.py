"""Tests for the workflow module.

The workflow manager reads/writes entity records through the entities
service manager (runtime.entities + runtime.entity_state + audit timeline +
audit transition attempts). These tests exercise that flow end-to-end
against the real Postgres test database.
"""

from __future__ import annotations

import os
import socket
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import Mock
from urllib.parse import urlparse

import pytest

from common.protocols import (
    EntityConditionSpec,
    EntityReadPolicy,
    record_satisfies_any_condition,
)
from entities.db_models import EntitiesModelService
from entities.manager import EntitiesServiceManager
from entities.models.request import (
    EntityRecordCreateRequest,
    EntityRelationDeclarationCreateRequest,
    EntityRelationCreateRequest,
    EntityTypeCreateRequest,
)
from entities.models.interface import RelationType
from exceptions import NotFoundError, ValidationError
from workflow.db_models import WorkflowEnrollmentSummaryRow, WorkflowModelService
from workflow.services.enrollment_summary import EnrollmentSummaryService
from workflow.models.interface import (
    EntityReadAccess,
    FormFieldType,
    ScanLimit,
    EntityField,
    EntityFieldType,
    EntitySchema,
    Guard,
    GuardType,
    State,
    StateMachineDefinition,
    Transition,
    matches_workflow_value,
)
from workflow.services import (
    DefinitionAnalysisService,
    EntitySchemaService,
    SimulationService,
    TransitionEvaluationService,
)
from workflow_manager_factory import AllowAllEntityRolesManager, make_workflow_manager
from workflow.models.request import (
    StateMachineCreateRequest,
    TransitionExecuteRequest,
    WorkflowDraftUpdateRequest,
)

if TYPE_CHECKING:
    from workflow.manager import WorkflowServiceManager


class _AlwaysAllowAuth:
    class _Decision:
        allowed = True
        reason = ""

    def check_access(self, _payload: dict[str, object]) -> _AlwaysAllowAuth._Decision:
        return self._Decision()


def _db_is_reachable() -> bool:
    """Return whether DATABASE_URL host appears reachable in this environment."""
    url = (
        os.environ.get("DATABASE_URL")
        or "postgresql://statemachine:statemachine@modular-db:5432/statemachine"
    )
    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432
    try:
        socket.getaddrinfo(host, port)
    except OSError:
        return False
    return True


# ── Pure (no-DB) validation tests ────────────────────────────────────────────


def test_entity_field_accepts_number_alias_and_normalizes_to_int() -> None:
    field = EntityField(field="priority_score", type="number", required=False, nullable=True)
    assert field.type == "int"


def test_entity_field_accepts_integer_alias_and_normalizes_to_int() -> None:
    field = EntityField(field="priority_score", type="integer", required=False, nullable=True)
    assert field.type == "int"


def test_dry_run_synthesizes_valid_email_when_schema_default_is_blank() -> None:
    field = EntityField(
        field="client_email",
        type="email",
        required=True,
        nullable=False,
        default="",
    )
    synthesized = SimulationService(
        TransitionEvaluationService(), DefinitionAnalysisService()
    ).default_value_for_field(field, prefer_concrete=True)
    assert synthesized == "mock_client_email@example.com"


def test_entity_field_preserves_phone_type_and_dry_run_value() -> None:
    field = EntityField(
        field="mobile_number",
        type="phone",
        required=True,
        nullable=False,
    )

    assert field.type == "phone"
    assert EntitySchemaService._normalize_form_field_type(field.type) == "phone"
    assert matches_workflow_value(field.type, "+15551234567") is True
    assert (
SimulationService(
            TransitionEvaluationService(), DefinitionAnalysisService()
        ).default_value_for_field(field, prefer_concrete=True)
        == "+15551234567"
    )


def test_multi_select_and_json_array_normalize_to_real_type_codes() -> None:
    """Form field types must normalize to codes `EntityFieldType` actually accepts.

    Both previously normalized to "array", which is not a member of `EntityFieldType`, so a
    workflow field could never declare a matching type and the form-drift comparison in
    `_validate_entity_schema_against_active_forms` reported every multi_select field as drifted
    for as long as the workflow existed.
    """
    assert EntitySchemaService._normalize_form_field_type("multi_select") == "multi_select"
    assert EntitySchemaService._normalize_form_field_type("json_array") == "json"

    valid = {member.value for member in EntityFieldType}
    for form_type in ("multi_select", "json_array", "json", "select", "number", "date", "text"):
        normalized = EntitySchemaService._normalize_form_field_type(form_type)
        assert normalized in valid, f"'{form_type}' normalizes to '{normalized}', not a real type"


def test_number_form_fields_normalize_to_the_type_a_field_actually_stores() -> None:
    """A form `number` field must normalize to the same code `EntityField` stores for it.

    The sibling test above only checks the result is *a* real member, and "integer" is one
    (`INTEGER_ALIAS`), so it passed while the drift comparison was still broken: `EntityField`
    stores both "number" and "integer" as INTEGER, whose value is "int". Returning "integer"
    meant the form side never equalled the stored side and every number field reported drift.
    """
    stored = EntityField(field="severity", type="number").type.value
    assert stored == EntityFieldType.INTEGER.value

    for form_type in (FormFieldType.NUMBER, FormFieldType.INTEGER):
        assert EntitySchemaService._normalize_form_field_type(form_type) == stored


def test_entity_field_preserves_and_validates_url_type() -> None:
    field = EntityField(
        field="portfolio_url",
        type="url",
        required=True,
        nullable=False,
    )

    assert field.type == "url"
    assert EntitySchemaService._normalize_form_field_type(field.type) == "url"
    assert matches_workflow_value(field.type, "https://example.com/profile") is True
    assert matches_workflow_value(field.type, "example.com/profile") is False
    assert (
SimulationService(
            TransitionEvaluationService(), DefinitionAnalysisService()
        ).default_value_for_field(field, prefer_concrete=True)
        == "https://example.com/portfolio_url"
    )


def test_enrollment_summary_context_resolves_bulk_data_once_per_page() -> None:
    """Summary enrichment remains page-scoped after manager decomposition."""
    definition = StateMachineDefinition(
        machine_key="bulk_summary",
        name="Bulk Summary",
        description="",
        entity_type="candidate",
        entity_schema=EntitySchema(entity_type="candidate", fields=[]),
        states=[State(name="screening", tags=["initial"], order=1)],
        initial_state="screening",
        transitions=[],
    )

    def summary_row(index: int) -> WorkflowEnrollmentSummaryRow:
        return WorkflowEnrollmentSummaryRow(
            state_id=f"state-{index}",
            organization_id="org-1",
            entity_id=f"entity-{index}",
            entity_type_id="candidate-type",
            entity_type="candidate",
            entity_data={"identifier": f"C-{index}"},
            owner_id=None,
            assignee_id=None,
            due_date=None,
            entity_created_at=None,
            entity_updated_at=None,
            archived_at=None,
            workflow_id="workflow-1",
            machine_name="bulk_summary",
            machine_display_name="Bulk Summary",
            machine_version=1,
            machine_definition=definition,
            current_state="screening",
            state_version=1,
            enrollment_created_at=None,
            state_entered_at=None,
            last_transition_at=None,
            sla_due_at=None,
        )

    rows = [summary_row(1), summary_row(2)]
    resolve_policies = Mock(
        return_value={"candidate-type": EntityReadPolicy()}
    )
    resolve_inherited = Mock(
        return_value={"entity-1": {}, "entity-2": {}}
    )
    services = Mock()
    services.resolve_read_policies = resolve_policies
    services.db_model_service.resolve_inherited_fields_for_records = resolve_inherited
    preview_manager = Mock()
    preview_manager.get_entity_preview_thumbnail_urls.return_value = {}
    manager = make_workflow_manager(None, filehandler_service_manager=preview_manager)
    request = manager.enrollment_summary.build_request(
        "bulk_summary", None, None, None, False, None, {"identifier"}, None, 50
    )

    manager.enrollment_summary._resolve_enrollment_summary_context(
        {"organization_id": "org-1"},
        "org-1",
        rows,
        request,
        services,
    )

    resolve_policies.assert_called_once()
    resolve_inherited.assert_called_once()
    resolved_records = resolve_inherited.call_args.kwargs["records"]
    assert {record.entity_id for record in resolved_records} == {
        "entity-1",
        "entity-2",
    }
    preview_manager.get_entity_preview_thumbnail_urls.assert_called_once_with(
        "org-1", {"entity-1", "entity-2"}
    )


# The access `_readable_entity_policies` would resolve for these tests' single
# entity type. `needs_row_scan` is forced on: these exercise the walk itself,
# not the decision to take it.
ACCESS = EntityReadAccess(
    policies={"candidate-type": EntityReadPolicy()},
    sql_conditions={},
    scan_type_ids=frozenset({"candidate-type"}),
    needs_row_scan=True,
)


def _row_conditioned_manager() -> tuple[WorkflowServiceManager, Any, set[str]]:
    """Manager over 40 enrollment rows where a read condition hides every other one.

    Returns the manager, the stubbed entities service, and the visible ids.
    """
    definition = StateMachineDefinition(
        machine_key="conditioned",
        name="Conditioned",
        description="",
        entity_type="candidate",
        entity_schema=EntitySchema(entity_type="candidate", fields=[]),
        states=[State(name="screening", tags=["initial"], order=1)],
        initial_state="screening",
        transitions=[],
    )
    raw_rows = [
        WorkflowEnrollmentSummaryRow(
            state_id=f"state-{index}",
            organization_id="org-1",
            entity_id=f"entity-{index}",
            entity_type_id="candidate-type",
            entity_type="candidate",
            entity_data={"identifier": f"C-{index:02d}"},
            owner_id=None,
            assignee_id=None,
            due_date=None,
            entity_created_at=None,
            entity_updated_at=None,
            archived_at=None,
            workflow_id="workflow-1",
            machine_name="conditioned",
            machine_display_name="Conditioned",
            machine_version=1,
            machine_definition=definition,
            current_state="screening",
            state_version=1,
            enrollment_created_at=None,
            state_entered_at=None,
            last_transition_at=None,
            sla_due_at=None,
        )
        for index in range(40)
    ]
    visible_ids = {f"entity-{index}" for index in range(0, 40, 2)}

    workflow_db = Mock()
    workflow_db.list_enrollment_summary_rows.side_effect = (
        lambda *, offset=None, limit=51, **_: raw_rows[(offset or 0):(offset or 0) + limit]
    )
    services = Mock()
    services.resolve_read_policies.return_value = {"candidate-type": EntityReadPolicy()}
    services.db_model_service.resolve_inherited_fields_for_records.return_value = {}
    services.apply_read_policy_to_data.side_effect = (
        lambda _policy, *, entity_id, data, projected_fields=None: (
            dict(data) if entity_id in visible_ids else None
        )
    )
    services.summary_display_name.side_effect = lambda data, entity_id: entity_id
    preview_manager = Mock()
    preview_manager.get_entity_preview_thumbnail_urls.return_value = {}

    manager = make_workflow_manager(workflow_db, filehandler_service_manager=preview_manager)
    return manager, services, visible_ids


def test_row_condition_pages_slice_visible_rows_not_raw_rows() -> None:
    """Row-level read conditions must be applied before the page is sliced.

    40 raw rows, every other one hidden by a read condition -> 20 visible.
    `total_count` counts visible rows, so the table offers exactly one page;
    that page therefore has to carry all 20. Slicing raw rows instead would
    return only the visible half of raw rows 0-19 and strand the rest past
    the last reachable offset.
    """
    manager, services, visible_ids = _row_conditioned_manager()
    request = manager.enrollment_summary.build_request(
        "conditioned", None, None, None, False, None, {"identifier"}, None, 20
    )

    items, has_more = manager.enrollment_summary.scan_visible_enrollment_page(
        {"organization_id": "org-1"}, "org-1", request, None, ACCESS, services, ScanLimit()
    )

    assert {item.entity_id for item in items} == visible_ids
    assert has_more is False

    second = manager.enrollment_summary.build_request(
        "conditioned", None, None, None, False, None, {"identifier"}, None, 20, offset=20
    )
    assert manager.enrollment_summary.scan_visible_enrollment_page(
        {"organization_id": "org-1"}, "org-1", second, None, ACCESS, services, ScanLimit()
    ) == ([], False)


def test_identifier_options_exclude_rows_hidden_by_read_conditions() -> None:
    """The identifier dropdown must not list values from unreadable records.

    A row-level read condition can only be evaluated on a loaded row, so the
    DISTINCT-over-SQL facet would hand back identifiers of records the actor
    cannot open — leaking both their existence and their identifier value.
    """
    manager, services, visible_ids = _row_conditioned_manager()
    request = manager.enrollment_summary.build_request(
        "conditioned", None, None, None, False, None, {"identifier"}, None, 20,
        include_identifier_options=True,
    )

    options = manager.enrollment_summary.visible_identifier_options(
        {"organization_id": "org-1"},
        "org-1",
        request,
        None,
        services,
        ACCESS,
        ScanLimit(),
    )

    assert options == sorted(
        f"C-{int(entity_id.removeprefix('entity-')):02d}" for entity_id in visible_ids
    )
    manager.workflow_db.list_enrollment_summary_identifier_options.assert_not_called()


def test_facet_scan_reads_in_chunks_and_stops_when_the_consumer_does() -> None:
    """The aggregates must not materialise the whole matched set at once.

    `_visible_facet_rows` batches its relation walk per call, so a single
    100k-row read built one `IN` list that size. Chunked, peak memory is one
    chunk — and because the walk is lazy, a consumer that stops early (the
    identifier-option cap) stops the reads too.
    """
    manager, services, _ = _row_conditioned_manager()
    request = manager.enrollment_summary.build_request(
        "conditioned", None, None, None, False, None, {"identifier"}, None, 20
    )
    access = EntityReadAccess(
        policies={"candidate-type": EntityReadPolicy()},
        sql_conditions={},
        scan_type_ids=frozenset({"candidate-type"}),
        needs_row_scan=True,
    )

    walk = manager.enrollment_summary._scan_visible_facet_rows(
        {"organization_id": "org-1"},
        "org-1",
        request,
        None,
        access,
        services,
        ScanLimit(),
        current_state=None,
        identifier=None,
    )

    # Lazy: nothing is read until the first row is pulled.
    manager.workflow_db.list_enrollment_summary_rows.assert_not_called()
    next(walk)
    reads = manager.workflow_db.list_enrollment_summary_rows.call_args_list
    assert len(reads) == 1
    assert reads[0].kwargs["limit"] == 500 and reads[0].kwargs["offset"] == 0

    # Abandoning the generator issues no further reads.
    walk.close()
    assert len(manager.workflow_db.list_enrollment_summary_rows.call_args_list) == 1


def test_scan_cap_is_reported_instead_of_silently_truncating(monkeypatch) -> None:
    """Hitting the row cap must set `scan_truncated`, not return a quiet prefix.

    Past the cap the counts understate and `has_more` can be a false negative.
    Without a signal the caller reads a truncated page as the end of the list.
    """
    manager, services, _ = _row_conditioned_manager()
    # 40 raw rows, chunked 10 at a time, capped at 20 -> the walk stops on the
    # cap with rows still unread.
    from common.configuration import get_configuration

    scan_config = get_configuration().workflow_configuration
    monkeypatch.setattr(scan_config, "row_condition_scan_chunk", 10)
    monkeypatch.setattr(scan_config, "row_condition_scan_cap", 20)
    request = manager.enrollment_summary.build_request(
        "conditioned", None, None, None, False, None, {"identifier"}, None, 20
    )
    access = EntityReadAccess(
        policies={"candidate-type": EntityReadPolicy()},
        sql_conditions={},
        scan_type_ids=frozenset({"candidate-type"}),
        needs_row_scan=True,
    )

    scan_limit = ScanLimit()
    manager.enrollment_summary.scan_visible_enrollment_page(
        {"organization_id": "org-1"}, "org-1", request, None, access, services, scan_limit
    )
    assert scan_limit.exhausted is True

    # A walk that reaches the end of the data is not truncated.
    monkeypatch.setattr(scan_config, "row_condition_scan_cap", 10_000)
    unbounded = ScanLimit()
    manager.enrollment_summary.scan_visible_enrollment_page(
        {"organization_id": "org-1"}, "org-1", request, None, access, services, unbounded
    )
    assert unbounded.exhausted is False


def test_search_is_scoped_to_fields_the_read_policy_leaves_visible() -> None:
    """`search` must not match on fields the actor's role cannot view.

    It is a SQL predicate, so it runs before `apply_read_policy_to_data` strips
    invisible fields and masks the rest. Matching the whole JSONB blob would let
    an actor probe a hidden field's contents by watching which rows come back.
    """
    searchable = EnrollmentSummaryService.searchable_fields_by_type(
        {
            "candidate-type": EntityReadPolicy(
                visible_fields={"email", "salary", "name"},
                masked_fields={"salary"},
            ),
            "job-type": EntityReadPolicy(),
        }
    )

    # Masked and never-visible fields are both out; the identifier is always in
    # because the read policy exempts it from both rules.
    assert searchable["candidate-type"] == {"email", "name", "identifier"}
    # `visible_fields is None` = system role, no field restriction at all.
    assert searchable["job-type"] is None


def _access_manager(policies: dict[str, EntityReadPolicy], inheritable: dict[str, set[str]]):
    """Manager whose entity service reports `policies` and `inheritable`."""
    services = Mock()
    services.list_entity_type_records.return_value = [
        SimpleNamespace(entity_type_id=type_id, name=type_id.removesuffix("-type"))
        for type_id in policies
    ]
    services.resolve_read_policies.return_value = policies
    services.db_model_service.inheritable_field_names_by_type.return_value = inheritable
    manager = make_workflow_manager(WorkflowModelService(None))
    return manager, services


def test_own_field_read_conditions_go_to_sql_and_skip_the_row_walk() -> None:
    """A condition on the record's own JSONB is a plain predicate — no scan."""
    manager, services = _access_manager(
        {
            "candidate-type": EntityReadPolicy(
                conditions=[
                    EntityConditionSpec(
                        entity_field="department", operator="==", condition_value="Engineering"
                    )
                ]
            )
        },
        inheritable={},
    )

    access = manager.enrollment_summary.readable_entity_policies(
        {"user_id": "u1"}, "org-1", services
    )

    assert access.needs_row_scan is False
    assert set(access.sql_conditions) == {"candidate-type"}


def test_inherited_field_read_conditions_still_need_the_row_walk() -> None:
    """`department` inherited from a related Job is not on the row being filtered.

    `resolve_inherited_fields_for_records` merges it *over* the record's own
    JSONB, so the stored value — if any — is not the one the condition is
    evaluated against. It cannot become a predicate on that row.
    """
    manager, services = _access_manager(
        {
            "application-type": EntityReadPolicy(
                conditions=[
                    EntityConditionSpec(
                        entity_field="department", operator="==", condition_value="Engineering"
                    )
                ]
            )
        },
        inheritable={"application-type": {"department"}},
    )

    access = manager.enrollment_summary.readable_entity_policies(
        {"user_id": "u1"}, "org-1", services
    )

    assert access.needs_row_scan is True
    assert access.sql_conditions == {}


def test_row_scan_is_dropped_when_no_reachable_row_needs_it() -> None:
    """One conditioned entity type must not put every query in the org on the scan.

    `scan_type_ids` comes from the actor's roles across the whole org, so a
    board that cannot return a single row of that type would otherwise pay a
    100k-row walk for nothing.
    """
    manager, _ = _access_manager(
        {
            "application-type": EntityReadPolicy(
                conditions=[
                    EntityConditionSpec(
                        entity_field="department", operator="==", condition_value="Engineering"
                    )
                ]
            ),
            "candidate-type": EntityReadPolicy(),
        },
        inheritable={"application-type": {"department"}},
    )
    # Both references must point at the stub: the narrowing probe runs on the service, so
    # patching only the manager would leave the real row source in play.
    manager.workflow_db = manager.enrollment_summary.workflow_db = Mock()
    access = EntityReadAccess(
        policies={"application-type": EntityReadPolicy(), "candidate-type": EntityReadPolicy()},
        sql_conditions={},
        scan_type_ids=frozenset({"application-type"}),
        needs_row_scan=True,
    )
    request = manager.enrollment_summary.build_request(
        "hiring", "screening", None, None, False, None, {"identifier"}, None, 20
    )
    narrow = manager.enrollment_summary.narrow_row_scan_to_reachable_types

    manager.workflow_db.enrollment_rows_exist.return_value = False
    assert narrow("org-1", request, None, access).needs_row_scan is False
    # The probe spans what all three surfaces can reach, so it must not carry
    # the page's own `current_state`/`identifier` narrowing.
    probe = manager.workflow_db.enrollment_rows_exist.call_args.kwargs
    assert probe["entity_type_ids"] == {"application-type"}
    assert "current_state" not in probe and "identifier" not in probe

    manager.workflow_db.enrollment_rows_exist.return_value = True
    assert narrow("org-1", request, None, access).needs_row_scan is True


def test_row_scan_narrowing_never_probes_when_nothing_needs_a_scan() -> None:
    """No scan-only type, no probe — the common case adds no query."""
    manager, _ = _access_manager({"candidate-type": EntityReadPolicy()}, inheritable={})
    # Both references must point at the stub: the narrowing probe runs on the service, so
    # patching only the manager would leave the real row source in play.
    manager.workflow_db = manager.enrollment_summary.workflow_db = Mock()
    access = EntityReadAccess(
        policies={"candidate-type": EntityReadPolicy()},
        sql_conditions={},
        scan_type_ids=frozenset(),
        needs_row_scan=False,
    )
    request = manager.enrollment_summary.build_request(
        "hiring", None, None, None, False, None, {"identifier"}, None, 20
    )

    narrowed = manager.enrollment_summary.narrow_row_scan_to_reachable_types(
        "org-1", request, None, access
    )
    assert narrowed is access
    manager.workflow_db.enrollment_rows_exist.assert_not_called()


def test_unconditional_policies_never_query_inheritable_fields() -> None:
    """No conditions, no extra round-trip — the common case stays one query."""
    manager, services = _access_manager({"candidate-type": EntityReadPolicy()}, inheritable={})

    access = manager.enrollment_summary.readable_entity_policies(
        {"user_id": "u1"}, "org-1", services
    )

    assert access.needs_row_scan is False
    assert access.sql_conditions == {}
    services.db_model_service.inheritable_field_names_by_type.assert_not_called()


# ── Real-DB integration: rewired entity flow ─────────────────────────────────


@pytest.fixture
def workflow_manager(entities_db_service_manager, clean_entities_tables):
    """Build a WorkflowServiceManager wired to the real entities + workflow DB.

    Reuses the entities-suite Postgres fixture. The workflow_db service holds
    state-machine definitions; the entities_service_manager owns runtime
    entity records, enrollments, audit timeline, and transition attempts.

    Workflow definitions persist across test runs in workflow_state_machines,
    so we clean rows for the test orgs ourselves — clean_entities_tables only
    handles the entities-suite tables.
    """
    from sqlalchemy import text

    from tests.conftest import ENTITIES_TEST_ORG_IDS

    engine = entities_db_service_manager.postgres_db_service().engine
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM workflow_state_machines WHERE organization_id = ANY(:ids)"),
            {"ids": list(ENTITIES_TEST_ORG_IDS)},
        )

    workflow_db = WorkflowModelService(database_service_manager=entities_db_service_manager)
    entities_db = EntitiesModelService(database_service_manager=entities_db_service_manager)
    entities = EntitiesServiceManager(
        entities_db,
        database_service_manager=entities_db_service_manager,
        config=None,
        roles_manager=AllowAllEntityRolesManager(),
    )
    entities.start()
    manager = make_workflow_manager(
        workflow_db,
        entities_db_service_manager,
        entities_service_manager=entities,
    )
    manager.start()
    yield manager


def _admin_actor(org_id: str = "test-org-1") -> dict[str, Any]:
    return {"user_id": "admin-1", "organization_id": org_id, "roles": ["admin"]}


def _register_entity_type(
    workflow_manager: WorkflowServiceManager, *, name: str, org_id: str = "test-org-1"
) -> str:
    """Auto-register an entity_type via the entities service so the workflow
    create path can resolve the runtime registry."""
    services = workflow_manager.entities_service_manager

    response = services.create_entity_type_for_actor(
        _admin_actor(org_id),
        EntityTypeCreateRequest(name=name, description=f"test type {name}"),
    )
    return response.entity_type_id


@pytest.mark.skipif(
    not _db_is_reachable(), reason="Postgres host is not reachable in this environment"
)
def test_pushed_read_conditions_agree_with_the_python_evaluator(workflow_manager) -> None:
    """The SQL predicate must decide exactly what `resolve_and_compare` decides.

    A read condition pushed into SQL replaces the row walk, so `offset` and
    `total_count` are computed from it. If the two evaluators disagree, paging
    desynchronises from what the projection actually returns — the failure the
    row scan exists to prevent.

    Covers the guards (missing key, empty string) and the one representation
    that differs between the two (`str(True)` == "True", Postgres' "true").
    """
    entity_type_id = _register_entity_type(workflow_manager, name="cond_push_type")
    definition = StateMachineDefinition(
        machine_key="cond_push",
        name="Cond Push",
        description="",
        entity_type="cond_push_type",
        entity_schema=EntitySchema(entity_type="cond_push_type", fields=[]),
        states=[State(name="alpha", tags=["initial"], order=1)],
        initial_state="alpha",
        transitions=[],
    )
    workflow_manager.workflow_db.create_state_machine_published(
        StateMachineCreateRequest(
            machine_name="cond_push", version=1, is_active=True, definition=definition
        ),
        organization_id="test-org-1",
    )
    services = workflow_manager.entities_service_manager
    records = {
        "R-eng": {"department": "Engineering"},
        "R-sales": {"department": "Sales"},
        "R-empty": {"department": ""},
        "R-absent": {},
        "R-true": {"department": True},
        "R-num": {"department": 42},
    }
    for identifier, extra in records.items():
        created = services.create_entity_record(
            EntityRecordCreateRequest(
                organization_id="test-org-1",
                entity_type_id=entity_type_id,
                data={"identifier": identifier, **extra},
            )
        )
        workflow_manager.enroll_entity_for_actor(
            _admin_actor(), machine_name="cond_push", entity_id=created.entity_id
        )

    def _sql(condition: EntityConditionSpec) -> set[str]:
        rows = workflow_manager.workflow_db.list_enrollment_summary_rows(
            organization_id="test-org-1",
            machine_name="cond_push",
            read_conditions_by_type={entity_type_id: [condition]},
            limit=50,
        )
        return {row.entity_data["identifier"] for row in rows}

    def _python(condition: EntityConditionSpec) -> set[str]:
        return {
            identifier
            for identifier, data in records.items()
            if record_satisfies_any_condition([condition], data, entity_id=identifier)
        }

    for condition in (
        EntityConditionSpec(entity_field="department", operator="==", condition_value="Engineering"),
        EntityConditionSpec(entity_field="department", operator="!=", condition_value="Engineering"),
        EntityConditionSpec(entity_field="department", operator="in", condition_value="Sales, Legal"),
        EntityConditionSpec(entity_field="department", operator="==", condition_value="True"),
        EntityConditionSpec(entity_field="department", operator="==", condition_value="42"),
        EntityConditionSpec(entity_field="missing_key", operator="!=", condition_value="x"),
    ):
        assert _sql(condition) == _python(condition), condition

    # Sanity: the guards actually bite — neither evaluator lets an empty or
    # absent value satisfy anything, not even `!=`.
    inequality = EntityConditionSpec(
        entity_field="department", operator="!=", condition_value="Engineering"
    )
    assert _sql(inequality) == {"R-sales", "R-true", "R-num"}

    # The reachability probe runs the same filter chain against real SQL.
    probe = workflow_manager.workflow_db.enrollment_rows_exist
    assert probe(organization_id="test-org-1", machine_name="cond_push") is True
    assert (
        probe(
            organization_id="test-org-1",
            machine_name="cond_push",
            entity_type_ids={"a-type-with-no-rows-here"},
        )
        is False
    )


@pytest.mark.skipif(
    not _db_is_reachable(), reason="Postgres host is not reachable in this environment"
)
def test_search_predicate_never_matches_fields_outside_the_readable_set(
    workflow_manager,
) -> None:
    """The SQL half of the search fix: a hidden field's value must not match.

    `search` is applied before the read policy projects the row, so an
    unrestricted blob match would let an actor probe a field they cannot view
    by watching which rows the filter returns.
    """
    entity_type_id = _register_entity_type(workflow_manager, name="search_scope_type")
    definition = StateMachineDefinition(
        machine_key="search_scope",
        name="Search Scope",
        description="",
        entity_type="search_scope_type",
        entity_schema=EntitySchema(entity_type="search_scope_type", fields=[]),
        states=[State(name="alpha", tags=["initial"], order=1)],
        initial_state="alpha",
        transitions=[],
    )
    workflow_manager.workflow_db.create_state_machine_published(
        StateMachineCreateRequest(
            machine_name="search_scope",
            version=1,
            is_active=True,
            definition=definition,
        ),
        organization_id="test-org-1",
    )
    services = workflow_manager.entities_service_manager
    for identifier, data in (
        ("S-visible", {"email": "needle@example.com"}),
        ("S-hidden", {"secret_note": "needle in a hidden field"}),
    ):
        created = services.create_entity_record(
            EntityRecordCreateRequest(
                organization_id="test-org-1",
                entity_type_id=entity_type_id,
                data={"identifier": identifier, **data},
            )
        )
        workflow_manager.enroll_entity_for_actor(
            _admin_actor(), machine_name="search_scope", entity_id=created.entity_id
        )

    def _search(searchable: dict[str, set[str] | None] | None) -> set[str]:
        rows = workflow_manager.workflow_db.list_enrollment_summary_rows(
            organization_id="test-org-1",
            machine_name="search_scope",
            search="needle",
            searchable_fields_by_type=searchable,
            limit=50,
        )
        return {row.entity_data.get("identifier") for row in rows}

    # No field restriction (system role) still matches the whole blob.
    assert _search(None) == {"S-visible", "S-hidden"}
    # A role that cannot view `secret_note` must not be able to match on it.
    assert _search({entity_type_id: {"email", "identifier"}}) == {"S-visible"}
    # Identifier stays searchable even when it is the only readable key.
    assert _search({entity_type_id: {"identifier"}}) == set()
    assert (
        workflow_manager.workflow_db.list_enrollment_summary_rows(
            organization_id="test-org-1",
            machine_name="search_scope",
            search="S-visible",
            searchable_fields_by_type={entity_type_id: {"identifier"}},
            limit=50,
        )[0].entity_data["identifier"]
        == "S-visible"
    )


@pytest.mark.skipif(
    not _db_is_reachable(), reason="Postgres host is not reachable in this environment"
)
def test_field_filters_are_exact_and_respect_field_visibility(workflow_manager) -> None:
    """Custom board filters match their named JSON field without exposing hidden fields."""
    entity_type_id = _register_entity_type(workflow_manager, name="field_filter_type")
    definition = StateMachineDefinition(
        machine_key="field_filter",
        name="Field Filter",
        description="",
        entity_type="field_filter_type",
        entity_schema=EntitySchema(entity_type="field_filter_type", fields=[]),
        states=[State(name="alpha", tags=["initial"], order=1)],
        initial_state="alpha",
        transitions=[],
    )
    workflow_manager.workflow_db.create_state_machine_published(
        StateMachineCreateRequest(
            machine_name="field_filter", version=1, is_active=True, definition=definition
        ),
        organization_id="test-org-1",
    )
    services = workflow_manager.entities_service_manager
    for identifier, department, active in (
        ("F-eng", "Engineering", True),
        ("F-sales", "Sales", True),
        ("F-inactive", "Engineering", False),
    ):
        created = services.create_entity_record(
            EntityRecordCreateRequest(
                organization_id="test-org-1",
                entity_type_id=entity_type_id,
                data={"identifier": identifier, "department": department, "active": active},
            )
        )
        workflow_manager.enroll_entity_for_actor(
            _admin_actor(), machine_name="field_filter", entity_id=created.entity_id
        )

    def _filter(filters: dict[str, str], visible: set[str] | None) -> set[str]:
        rows = workflow_manager.workflow_db.list_enrollment_summary_rows(
            organization_id="test-org-1",
            machine_name="field_filter",
            field_filters=filters,
            searchable_fields_by_type={entity_type_id: visible},
            limit=50,
        )
        return {row.entity_data["identifier"] for row in rows}

    assert _filter({"department": "Engineering"}, {"identifier", "department"}) == {
        "F-eng", "F-inactive"
    }
    assert _filter(
        {"department": "Engineering", "active": "true"},
        {"identifier", "department", "active"},
    ) == {"F-eng"}
    assert _filter({"department": "Eng"}, {"identifier", "department"}) == set()
    assert _filter({"department": "Engineering"}, {"identifier"}) == set()


@pytest.mark.skipif(
    not _db_is_reachable(), reason="Postgres host is not reachable in this environment"
)
def test_field_filters_match_multi_select_array_values(workflow_manager) -> None:
    """A `multi_select`/`picklist_multi` field stores its value as a JSON array
    (e.g. ["high","medium"]), not a plain string like `select` fields do. The
    filter must find it there too — not just when the field happens to be a
    scalar — and combining it with another (scalar) filter must not silently
    zero the whole result the way a strict `.astext ==` equality check did."""
    entity_type_id = _register_entity_type(workflow_manager, name="multi_select_filter_type")
    definition = StateMachineDefinition(
        machine_key="multi_select_filter",
        name="Multi Select Filter",
        description="",
        entity_type="multi_select_filter_type",
        entity_schema=EntitySchema(entity_type="multi_select_filter_type", fields=[]),
        states=[State(name="alpha", tags=["initial"], order=1)],
        initial_state="alpha",
        transitions=[],
    )
    workflow_manager.workflow_db.create_state_machine_published(
        StateMachineCreateRequest(
            machine_name="multi_select_filter", version=1, is_active=True, definition=definition
        ),
        organization_id="test-org-1",
    )
    services = workflow_manager.entities_service_manager
    for identifier, labels, priority in (
        ("M-high-medium", ["high", "medium"], "high"),
        ("M-low", ["low"], "high"),
        ("M-none", [], "medium"),
    ):
        created = services.create_entity_record(
            EntityRecordCreateRequest(
                organization_id="test-org-1",
                entity_type_id=entity_type_id,
                data={"identifier": identifier, "labels": labels, "priority": priority},
            )
        )
        workflow_manager.enroll_entity_for_actor(
            _admin_actor(), machine_name="multi_select_filter", entity_id=created.entity_id
        )

    def _filter(filters: dict[str, str]) -> set[str]:
        rows = workflow_manager.workflow_db.list_enrollment_summary_rows(
            organization_id="test-org-1",
            machine_name="multi_select_filter",
            field_filters=filters,
            limit=50,
        )
        return {row.entity_data["identifier"] for row in rows}

    # Array-valued field alone: matches whichever rows contain "high".
    assert _filter({"labels": "high"}) == {"M-high-medium"}
    # Combined with a scalar (`select`) field filter — must still match on
    # both conditions truly holding, not unconditionally return nothing.
    assert _filter({"labels": "high", "priority": "high"}) == {"M-high-medium"}
    # "medium" is in M-high-medium's array too, and its priority is "high".
    assert _filter({"labels": "medium", "priority": "high"}) == {"M-high-medium"}
    # No row has both "high" in its labels array AND priority "medium".
    assert _filter({"labels": "high", "priority": "medium"}) == set()


@pytest.mark.skipif(
    not _db_is_reachable(), reason="Postgres host is not reachable in this environment"
)
def test_field_filters_support_multi_value_or_across_a_single_field(workflow_manager) -> None:
    """Selecting multiple values for ONE field (e.g. filtering by labels
    "high" OR "medium") must OR them together — a row matches if it has ANY
    of the selected values. Regression for the frontend/backend contract only
    supporting one value per field key: `field_filters` values can now also
    be a list, and combining a multi-value field filter with another field's
    filter must still AND correctly, not silently drop to zero results."""
    entity_type_id = _register_entity_type(workflow_manager, name="multi_value_or_filter_type")
    definition = StateMachineDefinition(
        machine_key="multi_value_or_filter",
        name="Multi Value Or Filter",
        description="",
        entity_type="multi_value_or_filter_type",
        entity_schema=EntitySchema(entity_type="multi_value_or_filter_type", fields=[]),
        states=[State(name="alpha", tags=["initial"], order=1)],
        initial_state="alpha",
        transitions=[],
    )
    workflow_manager.workflow_db.create_state_machine_published(
        StateMachineCreateRequest(
            machine_name="multi_value_or_filter", version=1, is_active=True, definition=definition
        ),
        organization_id="test-org-1",
    )
    services = workflow_manager.entities_service_manager
    for identifier, labels, priority in (
        ("V-high", ["high"], "p1"),
        ("V-medium", ["medium"], "p1"),
        ("V-low", ["low"], "p1"),
        ("V-none", [], "p2"),
    ):
        created = services.create_entity_record(
            EntityRecordCreateRequest(
                organization_id="test-org-1",
                entity_type_id=entity_type_id,
                data={"identifier": identifier, "labels": labels, "priority": priority},
            )
        )
        workflow_manager.enroll_entity_for_actor(
            _admin_actor(), machine_name="multi_value_or_filter", entity_id=created.entity_id
        )

    def _filter(filters: dict) -> set[str]:
        rows = workflow_manager.workflow_db.list_enrollment_summary_rows(
            organization_id="test-org-1",
            machine_name="multi_value_or_filter",
            field_filters=filters,
            limit=50,
        )
        return {row.entity_data["identifier"] for row in rows}

    # A list of values on the same field is an OR — matches ANY, not ALL.
    assert _filter({"labels": ["high", "medium"]}) == {"V-high", "V-medium"}
    # OR-ing on the array field still combines with an AND against a
    # different (scalar) field filter.
    assert _filter({"labels": ["high", "medium"], "priority": "p1"}) == {"V-high", "V-medium"}
    assert _filter({"labels": ["high", "medium"], "priority": "p2"}) == set()
    # Same OR semantics on a plain scalar (`select`-style) field.
    assert _filter({"priority": ["p1", "p2"]}) == {"V-high", "V-medium", "V-low", "V-none"}
    # An explicit empty selection is provably empty, not "no filter" / everything.
    assert _filter({"labels": []}) == set()


@pytest.mark.skipif(
    not _db_is_reachable(), reason="Postgres host is not reachable in this environment"
)
def test_list_all_enrollments_spans_workflows_and_carries_owner(workflow_manager) -> None:
    """Org-wide aggregate lists entities across all workflows, each carrying its
    own machine_name + owner_id, and honors the entity_type filter."""

    def _build_def(machine_key: str, entity_type: str) -> StateMachineDefinition:
        return StateMachineDefinition(
            machine_key=machine_key,
            name=machine_key,
            description="",
            entity_type=entity_type,
            entity_schema=EntitySchema(entity_type=entity_type, fields=[]),
            states=[
                State(name="alpha", tags=["initial"], order=1),
                State(name="omega", tags=["terminal"], order=2),
            ],
            initial_state="alpha",
            transitions=[
                Transition(
                    key="go",
                    trigger="go",
                    label="go",
                    from_state="alpha",
                    to_state="omega",
                    required_fields=[],
                    guards=[],
                    pre_transition_tasks=[],
                    post_transition_tasks=[],
                    auto_transition=None,
                    sla_seconds=None,
                    description="",
                ),
            ],
        )

    type_a = _register_entity_type(workflow_manager, name="agg_type_a")
    type_b = _register_entity_type(workflow_manager, name="agg_type_b")

    workflow_db = workflow_manager.workflow_db
    workflow_db.create_state_machine_published(
        StateMachineCreateRequest(
            machine_name="agg_wf_a",
            version=1,
            is_active=True,
            definition=_build_def("agg_wf_a", "agg_type_a"),
        ),
        organization_id="test-org-1",
    )
    workflow_db.create_state_machine_published(
        StateMachineCreateRequest(
            machine_name="agg_wf_b",
            version=1,
            is_active=True,
            definition=_build_def("agg_wf_b", "agg_type_b"),
        ),
        organization_id="test-org-1",
    )

    services = workflow_manager.entities_service_manager
    agg_a_1 = services.create_entity_record(
        EntityRecordCreateRequest(
            organization_id="test-org-1",
            entity_id="agg-a-1",
            entity_type_id=type_a,
            data={},
            owner_id="admin-1",
        )
    )
    agg_b_1 = services.create_entity_record(
        EntityRecordCreateRequest(
            organization_id="test-org-1",
            entity_id="agg-b-1",
            entity_type_id=type_b,
            data={},
        )
    )
    agg_b_2 = services.create_entity_record(
        EntityRecordCreateRequest(
            organization_id="test-org-1",
            entity_id="agg-b-2",
            entity_type_id=type_b,
            data={},
        )
    )
    services.db_model_service.create_entity_relation(
        EntityRelationCreateRequest(
            organization_id="test-org-1",
            from_entity_id=agg_a_1.entity_id,
            to_entity_id=agg_b_1.entity_id,
            relation_type="RELATED_TO",
        )
    )
    workflow_manager.enroll_entity_for_actor(
        _admin_actor(), machine_name="agg_wf_a", entity_id=agg_a_1.entity_id
    )
    workflow_manager.enroll_entity_for_actor(
        _admin_actor(), machine_name="agg_wf_b", entity_id=agg_b_1.entity_id
    )
    workflow_manager.enroll_entity_for_actor(
        _admin_actor(), machine_name="agg_wf_b", entity_id=agg_b_2.entity_id
    )

    result = workflow_manager.list_enrollment_summaries_for_actor(_admin_actor(), limit=50)
    by_id = {item.entity_id: item for item in result.items}
    assert {agg_a_1.entity_id, agg_b_1.entity_id} <= set(by_id)
    assert by_id[agg_a_1.entity_id].machine_name == "agg_wf_a"
    assert by_id[agg_b_1.entity_id].machine_name == "agg_wf_b"
    assert by_id[agg_a_1.entity_id].owner_id == "admin-1"

    filtered = workflow_manager.list_enrollment_summaries_for_actor(
        _admin_actor(), entity_type_name="agg_type_a"
    )
    ids = {item.entity_id for item in filtered.items}
    assert agg_a_1.entity_id in ids
    assert agg_b_1.entity_id not in ids

    anchor_filtered = workflow_manager.list_enrollment_summaries_for_actor(
        _admin_actor(), anchor_entity_id=agg_a_1.entity_id
    )
    anchor_ids = {item.entity_id for item in anchor_filtered.items}
    assert agg_a_1.entity_id in anchor_ids
    assert agg_b_1.entity_id in anchor_ids
    assert agg_b_2.entity_id not in anchor_ids


@pytest.mark.skipif(
    not _db_is_reachable(), reason="Postgres host is not reachable in this environment"
)
def test_enrollment_summary_is_paginated_counted_and_query_bounded(
    workflow_manager, entities_db_service_manager
) -> None:
    """The board read remains set-based as enrollment volume grows."""
    from sqlalchemy import event

    entity_type = "summary_candidate"
    entity_type_id = _register_entity_type(workflow_manager, name=entity_type)
    definition = StateMachineDefinition(
        machine_key="summary_board",
        name="Summary Board",
        description="",
        entity_type=entity_type,
        entity_schema=EntitySchema(entity_type=entity_type, fields=[]),
        states=[
            State(name="alpha", tags=["initial"], order=1),
            State(name="omega", tags=["terminal"], order=2),
        ],
        initial_state="alpha",
        transitions=[
            Transition(
                key="advance",
                trigger="advance",
                label="Advance",
                from_state="alpha",
                to_state="omega",
                required_fields=[],
                guards=[],
                pre_transition_tasks=[],
                post_transition_tasks=[],
                auto_transition=None,
                sla_seconds=None,
                description="",
            )
        ],
    )
    workflow_manager.workflow_db.create_state_machine_published(
        StateMachineCreateRequest(
            machine_name="summary_board",
            version=1,
            is_active=True,
            definition=definition,
        ),
        organization_id="test-org-1",
    )
    services = workflow_manager.entities_service_manager
    entity_ids: list[str] = []
    for index in range(3):
        created = services.create_entity_record(
            EntityRecordCreateRequest(
                organization_id="test-org-1",
                entity_type_id=entity_type_id,
                data={"identifier": f"C-{index}", "private_note": "not requested"},
            )
        )
        entity_ids.append(created.entity_id)
        workflow_manager.enroll_entity_for_actor(
            _admin_actor(), machine_name="summary_board", entity_id=created.entity_id
        )

    statements = 0
    engine = entities_db_service_manager.postgres_db_service().engine

    def _count_statement(*_args) -> None:
        nonlocal statements
        statements += 1

    event.listen(engine, "before_cursor_execute", _count_statement)
    try:
        first = workflow_manager.list_enrollment_summaries_for_actor(
            _admin_actor(),
            machine_name="summary_board",
            current_state="alpha",
            fields="identifier",
            include="state_counts",
            limit=2,
        )
    finally:
        event.remove(engine, "before_cursor_execute", _count_statement)

    assert len(first.items) == 2
    assert first.has_more is True
    assert first.state_counts == {"alpha": 3}
    assert {item.display_name for item in first.items} <= {"C-0", "C-1", "C-2"}
    assert all(item.summary_fields.keys() == {"identifier"} for item in first.items)
    assert all(
        [(option.trigger, option.label, option.to_state, option.allowed) for option in item.transition_options]
        == [("advance", "Advance", "omega", True)]
        for item in first.items
    )
    assert statements <= 8

    second = workflow_manager.list_enrollment_summaries_for_actor(
        _admin_actor(),
        machine_name="summary_board",
        current_state="alpha",
        fields="identifier",
        limit=2,
        offset=2,
    )
    assert len(second.items) == 1
    assert second.has_more is False
    assert {item.entity_id for item in first.items + second.items} == set(entity_ids)

    detail = services.get_entity_record(
        organization_id="test-org-1", entity_id=entity_ids[0]
    )
    assert detail is not None
    assert detail.data["private_note"] == "not requested"

    aggregate_first = workflow_manager.list_enrollment_summaries_for_actor(
        _admin_actor(), machine_name="summary_board", fields="identifier", limit=2
    )
    moved = aggregate_first.items[0]
    workflow_manager.execute_transition_for_actor(
        _admin_actor(),
        moved.entity_id,
        TransitionExecuteRequest(
            entity_id=moved.entity_id,
            workflow_id=moved.workflow_id,
            trigger="advance",
        ),
    )
    aggregate_second = workflow_manager.list_enrollment_summaries_for_actor(
        _admin_actor(),
        machine_name="summary_board",
        fields="identifier",
        limit=2,
        offset=2,
    )
    assert moved.state_id not in {item.state_id for item in aggregate_second.items}
    assert len({
        *(item.state_id for item in aggregate_first.items),
        *(item.state_id for item in aggregate_second.items),
    }) == 3


def test_summary_transition_preview_does_not_infer_masked_fields(workflow_manager) -> None:
    definition = StateMachineDefinition(
        machine_key="masked_preview",
        name="Masked Preview",
        description="",
        entity_type="entity",
        entity_schema=EntitySchema(
            entity_type="entity",
            fields=[EntityField(field="salary", type="int", required=False, nullable=True)],
        ),
        states=[
            State(name="review", tags=["initial"], order=1),
            State(name="approved", tags=["terminal"], order=2),
        ],
        initial_state="review",
        transitions=[
            Transition(
                key="approve",
                trigger="approve",
                label="Approve",
                from_state="review",
                to_state="approved",
                required_fields=[],
                guards=[Guard(type=GuardType.NUMERICAL_VALUE_GTE, field="salary", value=100)],
                pre_transition_tasks=[],
                post_transition_tasks=[],
                auto_transition=None,
                sla_seconds=None,
                description="",
            )
        ],
    )
    hidden = TransitionEvaluationService().summary_options(
        definition,
        "review",
        {"salary": 150},
        EntityReadPolicy(visible_fields={"identifier"}, masked_fields={"salary"}),
    )
    assert hidden[0].availability_known is False
    assert hidden[0].guards == []
    assert hidden[0].blocked_reasons == []

    visible = TransitionEvaluationService().summary_options(
        definition,
        "review",
        {"salary": 150},
        EntityReadPolicy(visible_fields={"salary"}),
    )
    assert visible[0].availability_known is True
    assert visible[0].allowed is True


@pytest.mark.skipif(
    not _db_is_reachable(), reason="Postgres host is not reachable in this environment"
)
def test_stat414_local_500_enrollment_benchmark(
    workflow_manager, entities_db_service_manager
) -> None:
    """Local acceptance benchmark; setup time is intentionally not measured."""
    from statistics import median
    from time import perf_counter

    from sqlalchemy import event

    entity_type = "stat414_benchmark_candidate"
    entity_type_id = _register_entity_type(workflow_manager, name=entity_type)
    definition = StateMachineDefinition(
        machine_key="stat414_benchmark_board",
        name="STAT-414 Benchmark Board",
        description="",
        entity_type=entity_type,
        entity_schema=EntitySchema(entity_type=entity_type, fields=[]),
        states=[State(name="screening", tags=["initial"], order=1)],
        initial_state="screening",
        transitions=[],
    )
    workflow_manager.workflow_db.create_state_machine_published(
        StateMachineCreateRequest(
            machine_name="stat414_benchmark_board",
            version=1,
            is_active=True,
            definition=definition,
        ),
        organization_id="test-org-1",
    )
    services = workflow_manager.entities_service_manager
    parent_type_id = _register_entity_type(workflow_manager, name="stat414_department")
    parent = services.create_entity_record(
        EntityRecordCreateRequest(
            organization_id="test-org-1",
            entity_type_id=parent_type_id,
            data={"identifier": "DEPT-1", "department": "Engineering"},
        )
    )
    services.db_model_service.create_entity_relation_declaration(
        EntityRelationDeclarationCreateRequest(
            organization_id="test-org-1",
            from_entity_type_id=parent_type_id,
            to_entity_type_id=entity_type_id,
            relation_type=RelationType.REFERENCE,
            relation_metadata={"department": "department_name"},
        ),
        default_relation_type=RelationType.REFERENCE.value,
    )
    for index in range(500):
        entity = services.create_entity_record(
            EntityRecordCreateRequest(
                organization_id="test-org-1",
                entity_type_id=entity_type_id,
                data={
                    "identifier": f"C-{index:04d}",
                    "email": f"candidate-{index}@example.com",
                    "private_note": "must not appear in a card summary",
                },
                source_entity_ids=[parent.entity_id],
            )
        )
        workflow_manager.enroll_entity_for_actor(
            _admin_actor(),
            machine_name="stat414_benchmark_board",
            entity_id=entity.entity_id,
        )

    engine = entities_db_service_manager.postgres_db_service().engine

    def read_complete_board() -> tuple[float, int, int, int]:
        statements = 0

        def count_statement(*_args) -> None:
            nonlocal statements
            statements += 1

        offset = 0
        item_count = 0
        payload_bytes = 0
        first_page = True
        event.listen(engine, "before_cursor_execute", count_statement)
        started = perf_counter()
        try:
            while True:
                page = workflow_manager.list_enrollment_summaries_for_actor(
                    _admin_actor(),
                    machine_name="stat414_benchmark_board",
                    current_state="screening",
                    fields="identifier,email,department_name",
                    include="state_counts" if first_page else None,
                    limit=200,
                    offset=offset,
                )
                assert all(
                    item.summary_fields.get("department_name") == "Engineering"
                    and "private_note" not in item.summary_fields
                    for item in page.items
                )
                payload_bytes += len(page.model_dump_json().encode("utf-8"))
                item_count += len(page.items)
                first_page = False
                if not page.has_more:
                    break
                offset += 200
        finally:
            elapsed = perf_counter() - started
            event.remove(engine, "before_cursor_execute", count_statement)
        return elapsed, statements, item_count, payload_bytes

    cold = read_complete_board()
    warm_runs = [read_complete_board() for _ in range(5)]
    warm = warm_runs[-1]
    warm_seconds = [run[0] for run in warm_runs]
    print(
        "STAT414_BENCHMARK "
        f"cold_seconds={cold[0]:.4f} cold_queries={cold[1]} "
        f"warm_min_seconds={min(warm_seconds):.4f} "
        f"warm_median_seconds={median(warm_seconds):.4f} "
        f"warm_max_seconds={max(warm_seconds):.4f} warm_queries={warm[1]} "
        f"items={warm[2]} payload_bytes={warm[3]}"
    )
    assert cold[2] == warm[2] == 500
    # Guards against per-row queries, not against a fixed constant: each page
    # now also resolves the actor's read policies once (the entity-type
    # registry read that makes offset paging RBAC-correct), which is O(1) per
    # request regardless of how many rows the page holds.
    assert cold[1] <= 18
    assert cold[3] < 1_000_000
    assert cold[0] < 1.0


@pytest.mark.skipif(
    not _db_is_reachable(), reason="Postgres host is not reachable in this environment"
)
def test_enroll_entity_returns_just_created_enrollment(workflow_manager) -> None:
    """Regression: when an entity is already enrolled in workflow A and we
    enroll it in workflow B, the response from the B-enrollment must reflect
    workflow B (not whichever enrollment happens to be states[0]).
    """

    _register_entity_type(workflow_manager, name="shared_entity")

    def _build_def(machine_key: str) -> StateMachineDefinition:
        return StateMachineDefinition(
            machine_key=machine_key,
            name=machine_key,
            description="",
            entity_type="shared_entity",
            entity_schema=EntitySchema(entity_type="shared_entity", fields=[]),
            states=[
                State(name="alpha", tags=["initial"], order=1),
                State(name="omega", tags=["terminal"], order=2),
            ],
            initial_state="alpha",
            transitions=[
                Transition(
                    key="go",
                    trigger="go",
                    label="go",
                    from_state="alpha",
                    to_state="omega",
                    required_fields=[],
                    guards=[],
                    pre_transition_tasks=[],
                    post_transition_tasks=[],
                    auto_transition=None,
                    sla_seconds=None,
                    description="",
                ),
            ],
        )

    workflow_db = workflow_manager.workflow_db
    workflow_db.create_state_machine_published(
        StateMachineCreateRequest(
            machine_name="wf_a", version=1, is_active=True, definition=_build_def("wf_a")
        ),
        organization_id="test-org-1",
    )
    workflow_db.create_state_machine_published(
        StateMachineCreateRequest(
            machine_name="wf_b", version=1, is_active=True, definition=_build_def("wf_b")
        ),
        organization_id="test-org-1",
    )

    services = workflow_manager.entities_service_manager
    created = services.create_entity_record(
        EntityRecordCreateRequest(
            organization_id="test-org-1",
            entity_id="multi-enrol-1",
            entity_type_id=services.get_entity_type_record(
                organization_id="test-org-1", name="shared_entity"
            ).entity_type_id,
            data={},
        )
    )

    first = workflow_manager.enroll_entity_for_actor(
        _admin_actor(), machine_name="wf_a", entity_id=created.entity_id
    )
    assert first.machine_name == "wf_a"
    assert first.current_state == "alpha"

    second = workflow_manager.enroll_entity_for_actor(
        _admin_actor(), machine_name="wf_b", entity_id=created.entity_id
    )
    assert second.machine_name == "wf_b", (
        f"second enroll returned machine_name={second.machine_name!r} — "
        f"likely fell back to states[0] (wf_a) instead of the just-created enrollment"
    )
    assert second.current_state == "alpha"
    assert second.entity_type == "shared_entity"
    assert second.workflow_id is not None

    workflow_manager.execute_transition_for_actor(
        _admin_actor(),
        created.entity_id,
        TransitionExecuteRequest(
            entity_id=created.entity_id,
            workflow_id=second.workflow_id,
            trigger="go",
        ),
    )
    states = services.db_model_service.list_entity_states_for_entity(
        organization_id="test-org-1", entity_id=created.entity_id
    )
    state_by_workflow = {state.workflow_id: state.current_state for state in states}
    first_workflow = workflow_db.get_active_state_machine(
        organization_id="test-org-1", machine_name="wf_a"
    )
    assert first_workflow is not None
    assert state_by_workflow[first_workflow.id] == "alpha"
    assert state_by_workflow[second.workflow_id] == "omega"


@pytest.mark.skipif(
    not _db_is_reachable(), reason="Postgres host is not reachable in this environment"
)
def test_save_workflow_draft_preserves_canvas_metadata_when_field_omitted(workflow_manager) -> None:

    definition = StateMachineDefinition(
        machine_key="wf_canvas_preserve",
        name="Canvas Preserve",
        description="",
        entity_type="entity",
        entity_schema=EntitySchema(entity_type="entity", fields=[]),
        states=[
            State(name="draft", tags=["initial"], order=1),
            State(name="done", tags=["terminal"], order=2),
        ],
        initial_state="draft",
        transitions=[
            Transition(
                key="draft_to_done",
                trigger="complete",
                label="Complete",
                from_state="draft",
                to_state="done",
                required_fields=[],
                guards=[],
                pre_transition_tasks=[],
                post_transition_tasks=[],
                auto_transition=None,
                sla_seconds=None,
                description="",
            ),
        ],
    )

    # Seeded as a version-0 draft: `update_workflow_draft_for_actor` refuses any row
    # that is not a draft ("Only draft rows (version 0) can be updated"), a guard that
    # predates this branch. The original setup published version 1 and could never
    # reach the canvas_metadata behaviour it means to assert.
    created = workflow_manager.workflow_db.create_state_machine_draft(
        organization_id="test-org-1",
        machine_key="wf_canvas_preserve",
        machine_name="wf_canvas_preserve",
        definition=definition.model_dump(mode="json"),
        canvas_metadata={"nodes": {"draft": {"x": 40, "y": 60}}, "viewport": {"zoom": 1.1}},
    )
    assert created.id is not None

    result = workflow_manager.update_workflow_draft_for_actor(
        _admin_actor(),
        created.id,
        WorkflowDraftUpdateRequest(definition=definition.model_dump(mode="json")),
    )

    assert result.record.canvas_metadata == {
        "nodes": {"draft": {"x": 40, "y": 60}},
        "viewport": {"zoom": 1.1},
    }


@pytest.mark.skipif(
    not _db_is_reachable(), reason="Postgres host is not reachable in this environment"
)
def test_save_workflow_draft_can_clear_canvas_metadata_with_null(workflow_manager) -> None:

    definition = StateMachineDefinition(
        machine_key="wf_canvas_clear",
        name="Canvas Clear",
        description="",
        entity_type="entity",
        entity_schema=EntitySchema(entity_type="entity", fields=[]),
        states=[
            State(name="draft", tags=["initial"], order=1),
            State(name="done", tags=["terminal"], order=2),
        ],
        initial_state="draft",
        transitions=[
            Transition(
                key="draft_to_done",
                trigger="complete",
                label="Complete",
                from_state="draft",
                to_state="done",
                required_fields=[],
                guards=[],
                pre_transition_tasks=[],
                post_transition_tasks=[],
                auto_transition=None,
                sla_seconds=None,
                description="",
            ),
        ],
    )

    # Seeded as a version-0 draft: `update_workflow_draft_for_actor` refuses any row
    # that is not a draft ("Only draft rows (version 0) can be updated"), a guard that
    # predates this branch. The original setup published version 1 and could never
    # reach the canvas_metadata behaviour it means to assert.
    created = workflow_manager.workflow_db.create_state_machine_draft(
        organization_id="test-org-1",
        machine_key="wf_canvas_clear",
        machine_name="wf_canvas_clear",
        definition=definition.model_dump(mode="json"),
        canvas_metadata={"nodes": {"draft": {"x": 10, "y": 20}}, "viewport": {"zoom": 0.9}},
    )
    assert created.id is not None

    result = workflow_manager.update_workflow_draft_for_actor(
        _admin_actor(),
        created.id,
        WorkflowDraftUpdateRequest(
            definition=definition.model_dump(mode="json"),
            canvas_metadata=None,
        ),
    )

    assert result.record.canvas_metadata is None


# ── Archive (soft-delete) tests ───────────────────────────────────────────────


def _simple_definition(machine_key: str) -> StateMachineDefinition:
    return StateMachineDefinition(
        machine_key=machine_key,
        name=machine_key,
        description="",
        entity_type="entity",
        entity_schema=EntitySchema(entity_type="entity", fields=[]),
        states=[
            State(name="start", tags=["initial"], order=1),
            State(name="end", tags=["terminal"], order=2),
        ],
        initial_state="start",
        transitions=[
            Transition(
                key="go",
                trigger="go",
                label="go",
                from_state="start",
                to_state="end",
                required_fields=[],
                guards=[],
                pre_transition_tasks=[],
                post_transition_tasks=[],
                auto_transition=None,
                sla_seconds=None,
                description="",
            ),
        ],
    )


@pytest.mark.skipif(
    not _db_is_reachable(), reason="Postgres host is not reachable in this environment"
)
def test_archive_workflow_disappears_from_listing(workflow_manager) -> None:
    """Archiving a workflow removes it from the default listing."""
    workflow_db = workflow_manager.workflow_db
    created = workflow_db.create_state_machine_published(
        StateMachineCreateRequest(
            machine_name="wf_archive_listing",
            version=1,
            is_active=True,
            definition=_simple_definition("wf_archive_listing"),
        ),
        organization_id="test-org-1",
    )
    assert created.id is not None

    workflow_manager.delete_workflow_for_actor(_admin_actor(), created.id)

    rows = workflow_db.list_state_machines(organization_id="test-org-1", scope="all")
    assert not any(r.machine_name == "wf_archive_listing" for r in rows)


@pytest.mark.skipif(
    not _db_is_reachable(), reason="Postgres host is not reachable in this environment"
)
def test_archive_workflow_visible_with_include_archived(workflow_manager) -> None:
    """Archived workflows appear when include_archived=True."""
    workflow_db = workflow_manager.workflow_db
    created = workflow_db.create_state_machine_published(
        StateMachineCreateRequest(
            machine_name="wf_archive_visible",
            version=1,
            is_active=True,
            definition=_simple_definition("wf_archive_visible"),
        ),
        organization_id="test-org-1",
    )
    assert created.id is not None

    workflow_manager.delete_workflow_for_actor(_admin_actor(), created.id)

    rows = workflow_db.list_state_machines(
        organization_id="test-org-1", scope="all", include_archived=True
    )
    assert any(r.machine_name == "wf_archive_visible" for r in rows)


@pytest.mark.skipif(
    not _db_is_reachable(), reason="Postgres host is not reachable in this environment"
)
def test_archive_nonexistent_workflow_raises_not_found(workflow_manager) -> None:
    """Archiving a row_id that does not exist raises NotFoundError."""
    with pytest.raises(NotFoundError):
        workflow_manager.delete_workflow_for_actor(
            _admin_actor(), "00000000-0000-0000-0000-000000000000"
        )


@pytest.mark.skipif(
    not _db_is_reachable(), reason="Postgres host is not reachable in this environment"
)
def test_archive_draft_keeps_published_version(workflow_manager) -> None:
    """Archiving the draft row does not affect the published version."""
    workflow_db = workflow_manager.workflow_db
    definition = _simple_definition("wf_archive_draft_only")

    published = workflow_db.create_state_machine_published(
        StateMachineCreateRequest(
            machine_name="wf_archive_draft_only",
            version=1,
            is_active=True,
            definition=definition,
        ),
        organization_id="test-org-1",
    )
    draft = workflow_db.create_state_machine_draft(
        organization_id="test-org-1",
        machine_key="wf_archive_draft_only",
        machine_name="wf_archive_draft_only",
        definition=definition.model_dump(mode="json"),
    )
    assert draft.id is not None

    workflow_manager.delete_workflow_for_actor(_admin_actor(), draft.id)

    rows = workflow_db.list_state_machines(organization_id="test-org-1", scope="all")
    names = [r.machine_name for r in rows]
    assert "wf_archive_draft_only" in names

    active = workflow_db.get_active_state_machine(
        organization_id="test-org-1", machine_name="wf_archive_draft_only"
    )
    assert active is not None
    assert active.id == published.id


@pytest.mark.skipif(
    not _db_is_reachable(), reason="Postgres host is not reachable in this environment"
)
def test_archive_published_keeps_draft(workflow_manager) -> None:
    """Archiving the published version does not affect the draft row."""
    workflow_db = workflow_manager.workflow_db
    definition = _simple_definition("wf_archive_pub_only")

    published = workflow_db.create_state_machine_published(
        StateMachineCreateRequest(
            machine_name="wf_archive_pub_only",
            version=1,
            is_active=True,
            definition=definition,
        ),
        organization_id="test-org-1",
    )
    draft = workflow_db.create_state_machine_draft(
        organization_id="test-org-1",
        machine_key="wf_archive_pub_only",
        machine_name="wf_archive_pub_only",
        definition=definition.model_dump(mode="json"),
    )

    workflow_manager.delete_workflow_for_actor(_admin_actor(), published.id)

    rows = workflow_db.list_state_machines(organization_id="test-org-1", scope="draft")
    assert any(r.id == draft.id for r in rows)

    active = workflow_db.get_active_state_machine(
        organization_id="test-org-1", machine_name="wf_archive_pub_only"
    )
    assert active is None


@pytest.mark.skipif(
    not _db_is_reachable(), reason="Postgres host is not reachable in this environment"
)
def test_archive_blocked_when_entity_in_non_terminal_state(workflow_manager) -> None:
    """Archiving is rejected when an entity is still in a non-terminal state."""

    entity_type_id = _register_entity_type(workflow_manager, name="archive_block_entity")

    definition = _simple_definition("wf_archive_block")
    definition = definition.model_copy(
        update={
            "entity_type": "archive_block_entity",
            "entity_schema": definition.entity_schema.model_copy(
                update={"entity_type": "archive_block_entity"}
            ),
        }
    )

    workflow_db = workflow_manager.workflow_db
    published = workflow_db.create_state_machine_published(
        StateMachineCreateRequest(
            machine_name="wf_archive_block",
            version=1,
            is_active=True,
            definition=definition,
        ),
        organization_id="test-org-1",
    )
    assert published.id is not None

    services = workflow_manager.entities_service_manager
    entity = services.create_entity_record(
        EntityRecordCreateRequest(
            organization_id="test-org-1",
            entity_type_id=entity_type_id,
            data={},
        )
    )

    enrollment = workflow_manager.enroll_entity_for_actor(
        _admin_actor(), machine_name="wf_archive_block", entity_id=entity.entity_id
    )
    assert enrollment.current_state == "start"

    with pytest.raises(ValidationError, match="Cannot archive"):
        workflow_manager.delete_workflow_for_actor(_admin_actor(), published.id)

    rows = workflow_db.list_state_machines(organization_id="test-org-1", scope="all")
    assert any(r.id == published.id for r in rows), (
        "workflow should still exist after blocked archive"
    )


@pytest.mark.skipif(
    not _db_is_reachable(), reason="Postgres host is not reachable in this environment"
)
def test_archive_allowed_when_all_entities_in_terminal_state(workflow_manager) -> None:
    """Archiving succeeds once all enrolled entities have reached terminal states."""

    entity_type_id = _register_entity_type(workflow_manager, name="archive_terminal_entity")

    definition = _simple_definition("wf_archive_terminal")
    definition = definition.model_copy(
        update={
            "entity_type": "archive_terminal_entity",
            "entity_schema": definition.entity_schema.model_copy(
                update={"entity_type": "archive_terminal_entity"}
            ),
        }
    )

    workflow_db = workflow_manager.workflow_db
    published = workflow_db.create_state_machine_published(
        StateMachineCreateRequest(
            machine_name="wf_archive_terminal",
            version=1,
            is_active=True,
            definition=definition,
        ),
        organization_id="test-org-1",
    )

    services = workflow_manager.entities_service_manager
    entity = services.create_entity_record(
        EntityRecordCreateRequest(
            organization_id="test-org-1",
            entity_type_id=entity_type_id,
            data={},
        )
    )

    workflow_manager.enroll_entity_for_actor(
        _admin_actor(), machine_name="wf_archive_terminal", entity_id=entity.entity_id
    )
    workflow_manager.execute_transition_for_actor(
        _admin_actor(),
        entity_id=entity.entity_id,
        payload=TransitionExecuteRequest(entity_id=entity.entity_id, trigger="go"),
    )

    workflow_manager.delete_workflow_for_actor(_admin_actor(), published.id)

    rows = workflow_db.list_state_machines(organization_id="test-org-1", scope="all")
    assert not any(r.id == published.id for r in rows), (
        "archived workflow should be hidden from default listing"
    )


@pytest.mark.skipif(
    not _db_is_reachable(), reason="Postgres host is not reachable in this environment"
)
def test_enrollment_summaries_come_back_with_owner_and_assignee_names(
    workflow_manager, entities_db_service_manager
) -> None:
    """Names must come back from the public listing, not just the helper.

    Goes through `list_enrollment_summaries_for_actor` so the line that calls
    the helper is covered too.
    """

    class _UserServiceStub:
        def get_user_display_info(self, user_id: str) -> tuple[str | None, str | None]:
            return {"admin-1": "Vinay Kumar"}.get(user_id), None

    entity_type = "owner_names_type"
    entity_type_id = _register_entity_type(workflow_manager, name=entity_type)
    definition = _simple_definition("wf_owner_names")
    definition.entity_type = entity_type
    definition.entity_schema = EntitySchema(entity_type=entity_type, fields=[])
    workflow_manager.workflow_db.create_state_machine_published(
        StateMachineCreateRequest(
            machine_name="wf_owner_names",
            version=1,
            is_active=True,
            definition=definition,
        ),
        organization_id="test-org-1",
    )
    record = workflow_manager.entities_service_manager.create_entity_record(
        EntityRecordCreateRequest(
            organization_id="test-org-1",
            entity_id="owner-names-1",
            entity_type_id=entity_type_id,
            data={},
        )
    )
    workflow_manager.enroll_entity_for_actor(
        _admin_actor(), machine_name="wf_owner_names", entity_id=record.entity_id
    )
    workflow_manager.user_service_manager = _UserServiceStub()

    result = workflow_manager.list_enrollment_summaries_for_actor(
        _admin_actor(), machine_name="wf_owner_names", limit=50
    )

    row = next(item for item in result.items if item.entity_id == record.entity_id)
    assert row.owner_id == "admin-1"
    assert row.owner_name == "Vinay Kumar"

# ===========================================================================
# Role transition permissions follow the definition on publish
#
# Until recently every cascade was rolled back: publish handed the roles service a request
# session that nobody committed. Nothing covered it either, because the workflow test factory
# substitutes an allow-all roles double, so an end-to-end publish never reached the real code.
# These use the real RolesServiceManager against the database and assert on stored rows.
# ===========================================================================

_CASC_ORG = "test-org-1"
_CASC_MACHINE = "cascade_test_machine"
_CASC_KEY_ONE = "applied__to__screening"
_CASC_KEY_ONE_REPLACED = "applied__to__screening_2"
_CASC_KEY_TWO = "screening__to__done"


def _casc_transition(key: str, source: str, target: str) -> Transition:
    return Transition(
        key=key, trigger=key, label=key, from_state=source, to_state=target,
        required_fields=[], guards=[], pre_transition_tasks=[], post_transition_tasks=[],
        auto_transition=None, sla_seconds=None, description="",
    )


def _casc_definition(transitions: list[Transition]) -> StateMachineDefinition:
    return StateMachineDefinition(
        machine_key=_CASC_MACHINE, name=_CASC_MACHINE, description="", entity_type="patient",
        entity_schema=EntitySchema(
            entity_type="patient",
            fields=[EntityField(field="identifier", label="Identifier", type="string")],
        ),
        states=[
            State(name="APPLIED", tags=["initial"], order=1),
            State(name="SCREENING", order=2),
            State(name="DONE", tags=["terminal"], order=3),
        ],
        initial_state="APPLIED", transitions=transitions,
    )


_CASC_BOTH = _casc_definition(
    [_casc_transition(_CASC_KEY_ONE, "APPLIED", "SCREENING"),
     _casc_transition(_CASC_KEY_TWO, "SCREENING", "DONE")]
)
_CASC_REPLACED = _casc_definition(
    [_casc_transition(_CASC_KEY_ONE_REPLACED, "APPLIED", "SCREENING"),
     _casc_transition(_CASC_KEY_TWO, "SCREENING", "DONE")]
)
_CASC_DELETED = _casc_definition([_casc_transition(_CASC_KEY_TWO, "SCREENING", "DONE")])


@pytest.fixture
def casc_roles_manager(entities_db_service_manager):
    """The real roles manager over the real database."""
    from roles.db_models import RolesModelService
    from roles.manager import RolesServiceManager

    return RolesServiceManager(
        RolesModelService(database_service_manager=entities_db_service_manager),
        database_service_manager=entities_db_service_manager,
        config=None,
    )


@pytest.fixture
def casc_granted_role(entities_db_service_manager):
    """A role holding a transition permission on the first transition."""
    import uuid as _uuid

    from sqlalchemy import text

    engine = entities_db_service_manager.postgres_db_service().engine
    role_id = str(_uuid.uuid4())
    with engine.begin() as conn:
        if conn.execute(
            text("SELECT 1 FROM organizations WHERE id = :org"), {"org": _CASC_ORG}
        ).fetchone() is None:
            pytest.skip("no organizations row for the test org in this environment")
        conn.execute(
            text(
                "INSERT INTO roles (id, organization_id, name, display_name, is_system, priority) "
                "VALUES (:id, :org, :name, :name, false, 100)"
            ),
            {"id": role_id, "org": _CASC_ORG, "name": f"cascade-{role_id[:8]}"},
        )
        conn.execute(
            text(
                "INSERT INTO transition_permissions (id, role_id, machine_name, transition_key) "
                "VALUES (:id, :role, :machine, :key)"
            ),
            {"id": str(_uuid.uuid4()), "role": role_id, "machine": _CASC_MACHINE,
             "key": _CASC_KEY_ONE},
        )
    yield role_id
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM transition_permissions WHERE role_id = :r"), {"r": role_id})
        conn.execute(text("DELETE FROM roles WHERE id = :r"), {"r": role_id})


def _casc_stored_keys(entities_db_service_manager, role_id: str) -> list[str]:
    """Read the permission rows straight from the table."""
    from sqlalchemy import text

    engine = entities_db_service_manager.postgres_db_service().engine
    with engine.begin() as conn:
        return sorted(
            row[0] for row in conn.execute(
                text("SELECT transition_key FROM transition_permissions WHERE role_id = :r"),
                {"r": role_id},
            )
        )


def test_publish_rename_moves_the_permission_row_to_the_new_key(
    casc_roles_manager, casc_granted_role, entities_db_service_manager
):
    """Replacing a transition on the same route carries its permission to the new key."""
    assert _casc_stored_keys(entities_db_service_manager, casc_granted_role) == [_CASC_KEY_ONE]

    casc_roles_manager.cascade_workflow_publish(
        org_id=_CASC_ORG, machine_name=_CASC_MACHINE,
        old_definition=_CASC_BOTH, new_definition=_CASC_REPLACED,
    )

    assert _casc_stored_keys(entities_db_service_manager, casc_granted_role) == [
        _CASC_KEY_ONE_REPLACED
    ]


def test_publish_delete_removes_the_orphaned_grant(
    casc_roles_manager, casc_granted_role, entities_db_service_manager
):
    """Deleting a transition drops the permission that pointed at it."""
    casc_roles_manager.cascade_workflow_publish(
        org_id=_CASC_ORG, machine_name=_CASC_MACHINE,
        old_definition=_CASC_BOTH, new_definition=_CASC_DELETED,
    )

    assert _casc_stored_keys(entities_db_service_manager, casc_granted_role) == []


def test_publish_without_transition_changes_leaves_permissions_alone(
    casc_roles_manager, casc_granted_role, entities_db_service_manager
):
    """The common case: republishing an unchanged transition set touches nothing.

    Permissions key on machine name and transition key, with no version, so they carry across
    versions on their own. The cascade must not interfere with that.
    """
    casc_roles_manager.cascade_workflow_publish(
        org_id=_CASC_ORG, machine_name=_CASC_MACHINE,
        old_definition=_CASC_BOTH, new_definition=_CASC_BOTH,
    )

    assert _casc_stored_keys(entities_db_service_manager, casc_granted_role) == [_CASC_KEY_ONE]


def test_cascade_sync_failure_rolls_back_and_raises(
    casc_granted_role, entities_db_service_manager
):
    """A failure part-way through leaves the rows as they were and reports itself."""
    from exceptions import PersistenceError
    from roles.db_models import RolesModelService

    service = RolesModelService(database_service_manager=entities_db_service_manager)

    with pytest.raises(PersistenceError):
        service.sync_transition_permissions_on_publish(
            org_id=_CASC_ORG,
            machine_name=_CASC_MACHINE,
            renames=[(_CASC_KEY_ONE, _CASC_KEY_ONE_REPLACED)],
            valid_keys=[object()],  # a value the column cannot hold
        )

    assert _casc_stored_keys(entities_db_service_manager, casc_granted_role) == [_CASC_KEY_ONE]


# ===========================================================================
# POST /workflow-state-machines/{machine}/{version}/dry-run-entity
#
# This endpoint returned 500 on every well-formed request for a long time: the manager read a
# field the request model has never declared, and nothing tested the endpoint. These go through
# the real controller, so routing, request model, status codes and response model are exercised.
# ===========================================================================

_DRY_ORG = "test-org-1"
_DRY_ENTITY_TYPE = "dry_run_patient"
_DRY_MACHINE = "dry_run_test_machine"


def _dry_definition() -> StateMachineDefinition:
    """A definition the simulator can walk: ADMITTED -> DIAGNOSED -> TREATED."""
    from workflow.models.interface import RequiredField

    return StateMachineDefinition(
        machine_key=_DRY_MACHINE, name=_DRY_MACHINE, description="",
        entity_type=_DRY_ENTITY_TYPE,
        entity_schema=EntitySchema(
            entity_type=_DRY_ENTITY_TYPE,
            fields=[
                EntityField(field="identifier", label="Identifier", type="string"),
                EntityField(field="severity", label="Severity", type=EntityFieldType.NUMBER),
            ],
        ),
        states=[
            State(name="ADMITTED", tags=["initial"], order=1),
            State(name="DIAGNOSED", order=2),
            State(name="TREATED", tags=["terminal"], order=3),
        ],
        initial_state="ADMITTED",
        transitions=[
            Transition(
                key="admitted__to__diagnosed", trigger="diagnose", label="Diagnose",
                from_state="ADMITTED", to_state="DIAGNOSED",
                required_fields=[RequiredField(field="severity", required=True)],
                guards=[Guard(type=GuardType.NUMERICAL_VALUE_GTE, field="severity", value=1)],
                pre_transition_tasks=[], post_transition_tasks=[], auto_transition=None,
                sla_seconds=None, description="",
            ),
            Transition(
                key="diagnosed__to__treated", trigger="treat", label="Treat",
                from_state="DIAGNOSED", to_state="TREATED",
                required_fields=[], guards=[], pre_transition_tasks=[],
                post_transition_tasks=[], auto_transition=None, sla_seconds=None, description="",
            ),
        ],
    )


@pytest.fixture
def dry_run_client(entities_db_service_manager, clean_entities_tables):
    """TestClient over the real workflow router, with one published version 1."""
    from fastapi import APIRouter, FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy import text

    import workflow.controller as workflow_controller
    from common.deps import get_db
    from tests.conftest import ENTITIES_TEST_ORG_IDS

    engine = entities_db_service_manager.postgres_db_service().engine
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM workflow_state_machines WHERE organization_id = ANY(:ids)"),
            {"ids": list(ENTITIES_TEST_ORG_IDS)},
        )

    workflow_db = WorkflowModelService(database_service_manager=entities_db_service_manager)
    manager = make_workflow_manager(workflow_db, entities_db_service_manager)
    manager.start()
    workflow_db.create_state_machine_published(
        StateMachineCreateRequest(
            machine_name=_DRY_MACHINE, version=1, is_active=True, definition=_dry_definition()
        ),
        organization_id=_DRY_ORG,
    )

    controller = workflow_controller.WorkflowRestController(workflow_service_manager=manager)
    router = APIRouter()
    controller.prepare(router, security=None)
    app = FastAPI()
    app.include_router(router)

    actor = {
        "user_id": "user-dry-run", "organization_id": _DRY_ORG,
        "email": "dry-run@example.com", "is_system": True,
    }
    for annotated in (
        workflow_controller.WorkflowReadActor,
        workflow_controller.WorkflowWriteActor,
    ):
        app.dependency_overrides[annotated.__metadata__[0].dependency] = lambda: actor
    app.dependency_overrides[get_db] = lambda: None
    return TestClient(app, raise_server_exceptions=False)


def _dry_post(client, body: dict, version: object = 1):
    return client.post(f"/workflow-state-machines/{_DRY_MACHINE}/{version}/dry-run-entity", json=body)


def test_dry_run_simulates_the_supplied_snapshot(dry_run_client):
    """The happy path. This returned 500 on every request before the fix."""
    response = _dry_post(
        dry_run_client,
        {"entity_type": _DRY_ENTITY_TYPE, "current_state": "ADMITTED", "data": {"severity": 5}},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert sorted(body) == [
        "definition", "dry_run_summary", "machine_name", "validation_report", "version",
    ]
    assert body["machine_name"] == _DRY_MACHINE
    assert body["version"] == 1

    summary = body["dry_run_summary"]
    assert summary["initial_states_checked"] == ["ADMITTED"]
    assert summary["terminal_states_reached"] == ["TREATED"]
    assert summary["successful_paths_count"] >= 1
    assert {check["transition_key"] for check in summary["transition_checks"]} == {
        "admitted__to__diagnosed", "diagnosed__to__treated",
    }


def test_dry_run_unknown_current_state_is_rejected(dry_run_client):
    """The simulator resolves its start state with next(); an unknown name used to be a 500."""
    response = _dry_post(
        dry_run_client,
        {"entity_type": _DRY_ENTITY_TYPE, "current_state": "NO_SUCH_STATE", "data": {}},
    )

    assert response.status_code == 400, response.text
    assert "NO_SUCH_STATE" in response.json()["detail"]


def test_dry_run_entity_type_mismatch_is_rejected(dry_run_client):
    """The snapshot has to belong to the workflow's entity type."""
    response = _dry_post(
        dry_run_client, {"entity_type": "some_other_type", "current_state": "ADMITTED"}
    )

    assert response.status_code == 400, response.text
    assert "entity_type" in response.json()["detail"]


def test_dry_run_unknown_field_is_rejected(dry_run_client):
    """Data is validated against the pinned version's schema."""
    response = _dry_post(
        dry_run_client,
        {"entity_type": _DRY_ENTITY_TYPE, "current_state": "ADMITTED", "data": {"not_a_field": 1}},
    )

    assert response.status_code == 400, response.text
    assert "unknown entity fields" in response.json()["detail"]


def test_dry_run_wrong_value_type_is_rejected(dry_run_client):
    """`severity` is a number, so a string is refused."""
    response = _dry_post(
        dry_run_client,
        {"entity_type": _DRY_ENTITY_TYPE, "current_state": "ADMITTED", "data": {"severity": "high"}},
    )

    assert response.status_code == 400, response.text


def test_dry_run_blank_current_state_is_a_422(dry_run_client):
    """Empty strings are refused by the request model, before the manager sees them."""
    response = _dry_post(
        dry_run_client, {"entity_type": _DRY_ENTITY_TYPE, "current_state": "   ", "data": {}}
    )

    assert response.status_code == 422, response.text


@pytest.mark.parametrize("version", ["99", "0", "-1", "abc"])
def test_dry_run_unusable_version_never_reaches_the_simulator(dry_run_client, version):
    """An unknown or malformed version is a 404 or 422, never a 500."""
    response = _dry_post(
        dry_run_client,
        {"entity_type": _DRY_ENTITY_TYPE, "current_state": "ADMITTED", "data": {}},
        version,
    )

    assert response.status_code in (404, 422), f"version={version} gave {response.status_code}"


def test_dry_run_writes_nothing(dry_run_client, entities_db_service_manager):
    """A dry run is read-only: it must not persist a definition report."""
    from sqlalchemy import text

    engine = entities_db_service_manager.postgres_db_service().engine

    def report_count() -> int:
        with engine.begin() as conn:
            return conn.execute(
                text(
                    "SELECT count(*) FROM workflow_definition_reports WHERE organization_id = :org"
                ),
                {"org": _DRY_ORG},
            ).scalar_one()

    before = report_count()
    response = _dry_post(
        dry_run_client,
        {"entity_type": _DRY_ENTITY_TYPE, "current_state": "ADMITTED", "data": {"severity": 5}},
    )

    assert response.status_code == 200, response.text
    assert report_count() == before


# ===========================================================================
# render_workflow_paths — the arrow strings a user reads in the path preview
#
# Moved verbatim during the simulation extraction, so it only had indirect coverage through
# dry-run issue codes. These pin the four rendered variants and their suffixes directly, since
# they are user-visible text: a silent wording change is exactly what slipped through earlier in
# this series.
# ===========================================================================


def _dry_run_path(**overrides):
    """One explored dry-run path, terminal by default."""
    from workflow.models.interface import DryRunPath, DryRunStep

    fields: dict = {
        "path_id": "p-1",
        "start_state": "ADMITTED",
        "end_state": "TREATED",
        "terminal_reached": True,
        "steps": [
            DryRunStep(
                from_state="ADMITTED",
                trigger="diagnose",
                to_state="DIAGNOSED",
                actor_role=None,
                synthesized_inputs={},
            ),
            DryRunStep(
                from_state="DIAGNOSED",
                trigger="treat",
                to_state="TREATED",
                actor_role=None,
                synthesized_inputs={},
            ),
        ],
    }
    fields.update(overrides)
    return DryRunPath(**fields)


def _render_one(path):
    from workflow.models.interface import WorkflowDryRunSummary

    summary = WorkflowDryRunSummary(explored_paths=[path])
    lines = SimulationService(
        TransitionEvaluationService(), DefinitionAnalysisService()
    ).render_workflow_paths(summary)
    assert len(lines) == 1
    return lines[0]


def test_render_workflow_paths_renders_a_completed_path():
    """A path that reaches a terminal state ends with (END)."""
    line = _render_one(_dry_run_path())

    assert line.path_type == "terminal"
    assert line.rendered == (
        "(STARTING)ADMITTED -> (diagnose) -> DIAGNOSED -> (treat) -> TREATED (END)"
    )
    assert line.start_state == "ADMITTED"
    assert line.end_state == "TREATED"
    assert line.blocked_reasons == []


def test_render_workflow_paths_marks_a_loop():
    """loop_detected wins over the other suffixes and sets path_type."""
    line = _render_one(
        _dry_run_path(terminal_reached=False, loop_detected=True, end_state="DIAGNOSED")
    )

    assert line.path_type == "loop"
    assert line.rendered.endswith(" (LOOP)")


def test_render_workflow_paths_lists_blocked_reasons():
    """A blocked path names why, joined with '; ' inside the suffix."""
    line = _render_one(
        _dry_run_path(
            terminal_reached=False,
            blocked=True,
            blocked_reasons=["severity is missing", "guard not satisfiable"],
            end_state="DIAGNOSED",
        )
    )

    assert line.path_type == "blocked"
    assert line.rendered.endswith(" (BLOCKED: severity is missing; guard not satisfiable)")
    assert line.blocked_reasons == ["severity is missing", "guard not satisfiable"]


def test_render_workflow_paths_blocked_without_a_reason_has_a_bare_suffix():
    """No reasons means no colon, not an empty one."""
    line = _render_one(
        _dry_run_path(terminal_reached=False, blocked=True, blocked_reasons=[], end_state="DIAGNOSED")
    )

    assert line.rendered.endswith(" (BLOCKED)")


def test_render_workflow_paths_renders_a_single_state_path():
    """A path that never moved is just the starting state."""
    line = _render_one(_dry_run_path(steps=[], terminal_reached=False, end_state="ADMITTED"))

    assert line.rendered == "(STARTING)ADMITTED"
    assert line.path_type == "terminal"


def test_render_workflow_paths_renders_every_explored_path():
    """One line per explored path, in order."""
    from workflow.models.interface import WorkflowDryRunSummary

    summary = WorkflowDryRunSummary(
        explored_paths=[
            _dry_run_path(path_id="p-1"),
            _dry_run_path(path_id="p-2", terminal_reached=False, loop_detected=True),
        ]
    )

    lines = SimulationService(
        TransitionEvaluationService(), DefinitionAnalysisService()
    ).render_workflow_paths(summary)

    assert [line.path_type for line in lines] == ["terminal", "loop"]


# ===========================================================================
# compare_dates synthesis — the counterpart date a dry run invents
#
# A dry run has to invent both dates to answer "could this step ever pass?". It takes the
# record's own date as the base, or a fixed constant when there is none, then offsets a day in
# whichever direction the operator needs. Fixed rather than clock-derived so the same definition
# always simulates the same way.
# ===========================================================================


def _synth_other(primary, operator):
    from workflow.models.interface import EntityFieldType
    from workflow.services import (
        DefinitionAnalysisService,
        SimulationService,
        TransitionEvaluationService,
    )

    field = EntityField(field="discharge", label="Discharge", type=EntityFieldType.DATETIME)
    return SimulationService(
        TransitionEvaluationService(), DefinitionAnalysisService()
    )._synthesize_compare_dates_other(primary, operator, field)


@pytest.mark.parametrize(
    ("operator", "expect_later"),
    [("lt", True), ("lte", True), ("gt", False), ("gte", False)],
)
def test_compare_dates_synthesis_offsets_in_the_direction_the_operator_needs(
    operator, expect_later
):
    """`before` operators need a later counterpart; `after` operators need an earlier one."""
    base = "2026-05-05T00:00:00Z"
    other = _synth_other(base, operator)

    assert other is not None
    assert (other > base) is expect_later, f"{operator} produced {other} against {base}"


def test_compare_dates_synthesis_matches_for_equality():
    """`eq` is satisfied by the same date."""
    base = "2026-05-05T00:00:00Z"
    assert _synth_other(base, "eq") == base


def test_compare_dates_synthesis_differs_for_inequality():
    """`ne` needs a DIFFERENT date, or the rule can never be satisfied.

    Before this was fixed the function returned the base unchanged for `ne`, so
    `other != primary` was always false and any workflow with a "these two dates must differ"
    rule reported that step as unreachable in every dry run — while working fine in reality.
    """
    base = "2026-05-05T00:00:00Z"
    other = _synth_other(base, "ne")

    assert other is not None
    assert other != base, "ne must synthesize a date that differs from the base"


def test_compare_dates_synthesis_falls_back_to_the_shared_constant():
    """With no usable date on the record, the base is the shared dry-run constant."""
    from workflow.models.interface import DRY_RUN_DATETIME

    assert _synth_other(None, "eq") == DRY_RUN_DATETIME
    assert _synth_other(12345, "eq") == DRY_RUN_DATETIME


def test_compare_dates_synthesis_gives_up_on_an_unparseable_date():
    """An unparseable string yields nothing rather than a wrong date."""
    assert _synth_other("not-a-date", "lte") is None
    assert _synth_other("", "lte") is None
