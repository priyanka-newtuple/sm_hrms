"""Tests for dashboard data hydration."""

from __future__ import annotations

import os
import socket
from types import SimpleNamespace
from urllib.parse import urlparse

import pytest

from dashboard.db_models import DashboardModelService
from dashboard.manager import DashboardServiceManager
from entities.db_models import EntitiesModelService
from entities.manager import EntitiesServiceManager
from entities.models.request import (
    EntityRecordCreateRequest,
    EntityRelationCreateRequest,
    EntityTypeCreateRequest,
)
from exceptions import AuthorizationError, NotFoundError


class _AlwaysAllowAuth:
    class _Decision:
        allowed = True
        reason = ""

    def check_access(self, _payload: dict[str, object]) -> _AlwaysAllowAuth._Decision:
        return self._Decision()


def _db_is_reachable() -> bool:
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


def _entities_manager(database_service_manager) -> EntitiesServiceManager:
    return EntitiesServiceManager(
        EntitiesModelService(database_service_manager=database_service_manager),
        database_service_manager=database_service_manager,
        config=None,
        auth_service_manager=_AlwaysAllowAuth(),
    )


def test_dashboard_denies_workflow_restricted_roles() -> None:
    roles = SimpleNamespace(get_workflow_access_scope=lambda _actor: {"hiring"})
    manager = DashboardServiceManager(SimpleNamespace(), roles_manager=roles)
    with pytest.raises(AuthorizationError, match="workflow-restricted"):
        manager.list_metrics({"user_id": "u1", "organization_id": "org1"})


def test_dashboard_allows_dashboard_only_roles_without_workflow_read() -> None:
    roles = SimpleNamespace(get_workflow_access_scope=lambda _actor: set())
    manager = DashboardServiceManager(SimpleNamespace(), roles_manager=roles)
    manager._deny_restricted_workflow_actor(
        {"user_id": "u1", "organization_id": "org1"}
    )


@pytest.mark.skipif(not _db_is_reachable(), reason="database host is not reachable")
def test_dashboard_data_applies_global_entity_filter(
    entities_db_service_manager,
    clean_entities_tables,
) -> None:
    org_id = "test-org-1"
    actor = {"user_id": "admin-1", "organization_id": org_id, "roles": ["admin"]}

    entities = _entities_manager(entities_db_service_manager)
    account_type = entities.create_entity_type(
        EntityTypeCreateRequest(organization_id=org_id, name="dashboard_account")
    )
    case_type = entities.create_entity_type(
        EntityTypeCreateRequest(organization_id=org_id, name="dashboard_case")
    )

    account = entities.create_entity_record(
        EntityRecordCreateRequest(
            organization_id=org_id,
            entity_type_id=account_type.entity_type_id,
            data={"name": "Acme"},
        )
    )
    related_case = entities.create_entity_record(
        EntityRecordCreateRequest(
            organization_id=org_id,
            entity_type_id=case_type.entity_type_id,
            data={"name": "Related"},
        )
    )
    entities.create_entity_record(
        EntityRecordCreateRequest(
            organization_id=org_id,
            entity_type_id=case_type.entity_type_id,
            data={"name": "Unrelated"},
        )
    )
    entities.db_model_service.create_entity_relation(
        EntityRelationCreateRequest(
            organization_id=org_id,
            from_entity_id=account.entity_id,
            to_entity_id=related_case.entity_id,
            relation_type="related_to",
        )
    )

    dashboard = DashboardServiceManager(
        DashboardModelService(entities_db_service_manager),
        database_service_manager=entities_db_service_manager,
        config=None,
    )
    response = dashboard.get_data_for_actor(
        actor,
        [SimpleNamespace(widget_id="entity-count", metric="entities.count", filters={})],
        anchor_entity_id=account.entity_id,
    )

    assert response.results["entity-count"]["value"] == 2


@pytest.mark.skipif(not _db_is_reachable(), reason="database host is not reachable")
def test_dashboard_scopes_columns_and_states_to_picked_workflow(
    entities_db_service_manager,
    clean_entities_tables,
) -> None:
    """entity_data_fields/filter_options must narrow to one workflow's own
    entity type + declared states when a workflow_id is given (the widget
    builder's "Columns to show" / "Current State" pickers), and keep the
    existing org-wide union when it's omitted (the "All workflows" case)."""
    import json
    import uuid

    from workflow.db_models import WorkflowStateMachineModel

    org_id = "test-org-1"
    entities = _entities_manager(entities_db_service_manager)

    type_a = entities.create_entity_type(
        EntityTypeCreateRequest(
            organization_id=org_id,
            name="dashboard_vendor",
            schema_definition={
                "fields": [{"id": "vendor_name", "label": "Vendor Name", "type": "string"}]
            },
        )
    )
    type_b = entities.create_entity_type(
        EntityTypeCreateRequest(
            organization_id=org_id,
            name="dashboard_report",
            schema_definition={
                "fields": [{"id": "report_id", "label": "Report Id", "type": "string"}]
            },
        )
    )

    db = DashboardModelService(entities_db_service_manager)
    session = entities_db_service_manager.postgres_db_service().get_db_session()
    # Workflow A is a three-version family, mirroring real data, and the rows
    # are inserted worst-case-first so an unordered `.first()` reads the wrong
    # one rather than passing by luck of physical row order:
    #   v0 — the "entity" placeholder `_blank_draft_definition` writes, which
    #        names no real entity type (resolving it yields nothing at all);
    #   v1 — a *different real* entity type, as if an old version were bound
    #        elsewhere before being re-pointed (resolvable, but the wrong answer);
    #   v2 — ACTIVE, the live binding and the only correct answer.
    # So resolution must both skip unresolvable names and prefer the active
    # version; getting either wrong silently widens the column list to the
    # whole org (v0) or offers another entity type's fields (v1).
    wf_a_placeholder_id, wf_a_stale_id, wf_a_id = (
        str(uuid.uuid4()),
        str(uuid.uuid4()),
        str(uuid.uuid4()),
    )
    wf_b_id = str(uuid.uuid4())
    wf_ids = [wf_a_placeholder_id, wf_a_stale_id, wf_a_id, wf_b_id]
    a_states = json.dumps({"states": [{"name": "DRAFT"}, {"name": "APPROVED"}]})
    try:
        session.add_all(
            [
                WorkflowStateMachineModel(
                    id=wf_a_placeholder_id,
                    organization_id=org_id,
                    machine_key="dashboard_test_wf_a",
                    machine_name="dashboard_test_wf_a",
                    # entity_type stores the entity type's *name*, not its id —
                    # matches production data shape (see resolve_workflow_entity_type).
                    # `_blank_draft_definition`'s placeholder: deliberately not a
                    # registered entity type name.
                    entity_type="entity",
                    version=0,
                    is_active=False,
                    definition_json=a_states,
                ),
                WorkflowStateMachineModel(
                    id=wf_a_stale_id,
                    organization_id=org_id,
                    machine_key="dashboard_test_wf_a",
                    machine_name="dashboard_test_wf_a",
                    # Resolvable, but bound to the *other* entity type — only the
                    # active version below is the correct answer.
                    entity_type=type_b.name,
                    version=1,
                    is_active=False,
                    definition_json=a_states,
                ),
                WorkflowStateMachineModel(
                    id=wf_a_id,
                    organization_id=org_id,
                    machine_key="dashboard_test_wf_a",
                    machine_name="dashboard_test_wf_a",
                    entity_type=type_a.name,
                    version=2,
                    is_active=True,
                    definition_json=a_states,
                ),
                WorkflowStateMachineModel(
                    id=wf_b_id,
                    organization_id=org_id,
                    machine_key="dashboard_test_wf_b",
                    machine_name="dashboard_test_wf_b",
                    entity_type=type_b.name,
                    version=1,
                    is_active=True,
                    definition_json=json.dumps(
                        {"states": [{"name": "SUBMITTED"}, {"name": "CLOSED"}]}
                    ),
                ),
            ]
        )
        session.commit()

        # Scoped to workflow A's own entity type: only its field, not B's.
        fields_a = db.entity_data_fields(org_id, entity_type=type_a.entity_type_id)
        assert ("data.vendor_name", "Vendor Name") in fields_a
        assert not any(key == "data.report_id" for key, _ in fields_a)

        # Omitting entity_type ("All") keeps the org-wide union of both.
        fields_all = db.entity_data_fields(org_id)
        assert any(key == "data.vendor_name" for key, _ in fields_all)
        assert any(key == "data.report_id" for key, _ in fields_all)

        # Resolves to the ACTIVE version's binding — skipping the unresolvable
        # placeholder and the stale version bound to the other type — whichever
        # version row of the family the caller happens to pass.
        for passed_id in (wf_a_id, wf_a_placeholder_id, wf_a_stale_id):
            assert (
                db.resolve_workflow_entity_type(org_id, passed_id) == type_a.entity_type_id
            )

        # End-to-end: the reported symptom — the metric's selectable columns
        # must be A's own, not every data field in the org.
        # System actor: field-level RBAC is covered by test_dashboard_field_rbac;
        # this assertion is only about which workflow's fields are offered.
        actor = {"user_id": "admin-1", "organization_id": org_id, "actor_type": "system"}
        manager = DashboardServiceManager(
            db,
            database_service_manager=entities_db_service_manager,
            config=None,
            entities_service_manager=entities,
        )
        scoped = next(
            m
            for m in manager.list_metrics(actor, workflow_id=wf_a_id).metrics
            if m.key == "instances.list"
        )
        scoped_keys = {f.key for f in scoped.fields}
        assert "data.vendor_name" in scoped_keys
        assert "data.report_id" not in scoped_keys

        # ...while "All" still lists both.
        unscoped_keys = {
            f.key
            for m in manager.list_metrics(actor).metrics
            if m.key == "instances.list"
            for f in m.fields
        }
        assert {"data.vendor_name", "data.report_id"} <= unscoped_keys

        # Scoped to workflow A: only its declared states, not B's.
        options_a = db.filter_options(org_id, workflow_id=wf_a_id)
        assert {o["value"] for o in options_a["states"]} == {"DRAFT", "APPROVED"}

        # Regression: reported symptom — a workflow's own entity type/columns
        # picker leaking another workflow's entity type and its fields (e.g. a
        # sibling workflow's fields showing up while configuring a widget for
        # this one). `entity_types` and `entity_fields` must be scoped to the
        # workflow's own bound entity type, same as `states` already is.
        assert {o["value"] for o in options_a["entity_types"]} == {type_a.entity_type_id}
        assert {o["value"] for o in options_a["entity_fields"]} == {"data.vendor_name"}

        options_b = db.filter_options(org_id, workflow_id=wf_b_id)
        assert {o["value"] for o in options_b["entity_types"]} == {type_b.entity_type_id}
        assert {o["value"] for o in options_b["entity_fields"]} == {"data.report_id"}

        # Omitting workflow_id ("All") keeps the org-wide union of both.
        options_all = db.filter_options(org_id)
        assert {"DRAFT", "APPROVED", "SUBMITTED", "CLOSED"} <= {
            o["value"] for o in options_all["states"]
        }
        assert {type_a.entity_type_id, type_b.entity_type_id} <= {
            o["value"] for o in options_all["entity_types"]
        }
        assert {"data.vendor_name", "data.report_id"} <= {
            o["value"] for o in options_all["entity_fields"]
        }
    finally:
        session.query(WorkflowStateMachineModel).filter(
            WorkflowStateMachineModel.id.in_(wf_ids)
        ).delete(synchronize_session=False)
        session.commit()
        session.close()


@pytest.mark.skipif(not _db_is_reachable(), reason="database host is not reachable")
def test_global_filter_entity_ids_handles_empty_and_missing_anchor(
    entities_db_service_manager,
    clean_entities_tables,
) -> None:
    org_id = "test-org-1"
    actor = {"user_id": "admin-1", "organization_id": org_id, "roles": ["admin"]}
    entities = _entities_manager(entities_db_service_manager)

    assert entities.global_filter_entity_ids(
        actor=actor,
        organization_id=org_id,
        anchor_entity_id=None,
    ) is None

    with pytest.raises(NotFoundError):
        entities.global_filter_entity_ids(
            actor=actor,
            organization_id=org_id,
            anchor_entity_id="missing-anchor",
        )


@pytest.mark.skipif(not _db_is_reachable(), reason="database host is not reachable")
def test_global_filter_entity_ids_enforces_anchor_read_permission(
    entities_db_service_manager,
    clean_entities_tables,
    monkeypatch,
) -> None:
    org_id = "test-org-1"
    actor = {"user_id": "admin-1", "organization_id": org_id, "roles": ["admin"]}
    entities = _entities_manager(entities_db_service_manager)
    entity_type = entities.create_entity_type(
        EntityTypeCreateRequest(organization_id=org_id, name="dashboard_guarded")
    )
    record = entities.create_entity_record(
        EntityRecordCreateRequest(
            organization_id=org_id,
            entity_type_id=entity_type.entity_type_id,
            data={"name": "Guarded"},
        )
    )

    def deny_read(*_args, **_kwargs):
        raise AuthorizationError("denied")

    monkeypatch.setattr(entities, "guard_read", deny_read)

    with pytest.raises(AuthorizationError):
        entities.global_filter_entity_ids(
            actor=actor,
            organization_id=org_id,
            anchor_entity_id=record.entity_id,
        )


@pytest.mark.skipif(not _db_is_reachable(), reason="database host is not reachable")
def test_list_entity_records_by_ids_returns_requested_records_only(
    entities_db_service_manager,
    clean_entities_tables,
) -> None:
    org_id = "test-org-1"
    entities = _entities_manager(entities_db_service_manager)
    entity_type = entities.create_entity_type(
        EntityTypeCreateRequest(organization_id=org_id, name="dashboard_by_ids")
    )
    included = entities.create_entity_record(
        EntityRecordCreateRequest(
            organization_id=org_id,
            entity_type_id=entity_type.entity_type_id,
            data={"name": "Included"},
        )
    )
    entities.create_entity_record(
        EntityRecordCreateRequest(
            organization_id=org_id,
            entity_type_id=entity_type.entity_type_id,
            data={"name": "Excluded"},
        )
    )

    manager_rows = entities.list_entity_records_by_ids(
        organization_id=org_id,
        entity_ids={included.entity_id},
    )
    model_rows = entities.db_model_service.list_entity_records_by_ids(
        organization_id=org_id,
        entity_ids={included.entity_id},
    )

    assert [row.entity_id for row in manager_rows] == [included.entity_id]
    assert [row.entity_id for row in model_rows] == [included.entity_id]


@pytest.mark.skipif(not _db_is_reachable(), reason="database host is not reachable")
def test_field_picker_offers_form_fields_and_skips_keys_empty_everywhere(
    entities_db_service_manager,
    clean_entities_tables,
) -> None:
    """The widget builder's field picker must reflect what the entity type
    actually has, not every key ever written into a record's data column.

    Reported symptom: one legacy record kept another entity type's field keys
    (all blank) after a form edit, so the picker offered ~20 phantom columns,
    including another entity type's fields, for every record of that type.

    Two rules, both asserted here:
      * a field DECLARED in the entity type's form is always offered, even
        before any record fills it in;
      * a key only present as an empty value in every record is not offered
        (it could only ever render a blank column). `0`/`False` are real
        values and must survive.
    """
    import uuid

    from entities.db_models import EntityRecordModel, EntityTypeModel
    from forms.db_models import EntityTypeSchemaModel

    org_id = "test-org-1"
    db = DashboardModelService(entities_db_service_manager)
    session = entities_db_service_manager.postgres_db_service().get_db_session()

    type_name = f"picker_task_{uuid.uuid4().hex[:8]}"
    type_id = str(uuid.uuid4())
    # Mirrors production shape for a form-driven org: the entity type's own
    # `schema` column is empty and the real fields live in the forms module.
    form_fields = [
        {"field": "title", "label": "Summary", "type": "text"},
        {"field": "never_filled", "label": "Never Filled", "type": "text"},
    ]
    try:
        session.add(
            EntityTypeModel(
                entity_type_id=type_id,
                organization_id=org_id,
                name=type_name,
                schema={},
                version=1,
                is_active=True,
            )
        )
        session.commit()
        session.add(
            EntityTypeSchemaModel(
                id=str(uuid.uuid4()),
                organization_id=org_id,
                schema_key=f"{type_name}_form",
                name="Picker Form",
                entity_type=type_name,
                fields_json=form_fields,
                is_active=True,
                display_order=0,
            )
        )
        session.commit()
        session.add_all(
            [
                # Real data, including falsy-but-real values.
                EntityRecordModel(
                    entity_id=str(uuid.uuid4()),
                    organization_id=org_id,
                    entity_type_id=type_id,
                    data={"title": "real", "adhoc_key": "v", "story_points": 0, "flagged": False},
                ),
                # The legacy record: another entity type's keys, all blank.
                EntityRecordModel(
                    entity_id=str(uuid.uuid4()),
                    organization_id=org_id,
                    entity_type_id=type_id,
                    data={
                        "title": "legacy",
                        "total_jira_violations_last_week": "",
                        "overall_health": "   ",
                        "delivery_manager": None,
                        "empty_table": [],
                    },
                ),
            ]
        )
        session.commit()

        names = {
            key[len("data."):] for key, _ in db.entity_data_fields(org_id, entity_type=type_id)
        }

        # Declared in the form -> always offered, even with no data at all.
        assert "never_filled" in names
        # Ad-hoc keys carrying a real value -> still offered (not form-gated),
        # including falsy-but-real 0 / False.
        assert {"adhoc_key", "story_points", "flagged"} <= names
        # Empty in every record -> not offered, whatever the empty shape is.
        assert not (
            {
                "total_jira_violations_last_week",
                "overall_health",
                "delivery_manager",
                "empty_table",
            }
            & names
        )

        # The form's label wins over the humanized fallback.
        labels = dict(db.entity_data_fields(org_id, entity_type=type_id))
        assert labels["data.title"] == "Summary"
    finally:
        session.query(EntityRecordModel).filter(
            EntityRecordModel.entity_type_id == type_id
        ).delete(synchronize_session=False)
        session.query(EntityTypeSchemaModel).filter(
            EntityTypeSchemaModel.entity_type == type_name
        ).delete(synchronize_session=False)
        session.query(EntityTypeModel).filter(
            EntityTypeModel.entity_type_id == type_id
        ).delete(synchronize_session=False)
        session.commit()
        session.close()


# --- FT-0135: an unusable time window must not answer with an all-time number ---


def test_range_since_resolves_every_documented_preset() -> None:
    """The presets the tool description promises must all resolve."""
    from dashboard.metrics import TIME_RANGE_VALUES, _range_since

    assert _range_since({"time_range": "all"}) is None
    assert _range_since({}) is None
    assert _range_since({"time_range": ""}) is None
    for value in TIME_RANGE_VALUES:
        if value == "all":
            continue
        assert _range_since({"time_range": value}) is not None, value


def test_range_since_rejects_an_unrecognized_window() -> None:
    """A window we can't apply is an error, not a silent all-time answer.

    "last 5 days" used to fall through to no lower bound, so the caller got a
    full all-time count with nothing saying the range had been ignored.
    """
    from exceptions import ValidationError

    from dashboard.metrics import _range_since

    with pytest.raises(ValidationError) as excinfo:
        _range_since({"time_range": "last 5 days"})

    message = str(excinfo.value)
    assert "last_7d" in message
    assert "date_from" in message


def test_custom_date_range_still_wins_over_a_preset() -> None:
    """date_from takes precedence and is not subject to the preset vocabulary."""
    from dashboard.metrics import _range_since

    since = _range_since({"date_from": "2026-09-01", "time_range": "last_7d"})
    assert since is not None
    assert since.year == 2026 and since.month == 9 and since.day == 1


# --- FT-0135b: arbitrary trailing-day windows ---


def test_range_since_accepts_any_trailing_day_count() -> None:
    """"The last 5 days" must be expressible, not rounded to a preset.

    Only 7/30/90/180 were accepted, so the agent answered a 5-day question
    with last_7d and reported that widened window's number as the answer.
    """
    from dashboard.metrics import _range_since

    for days in (1, 2, 5, 45, 365):
        since = _range_since({"time_range": f"last_{days}d"})
        assert since is not None, days


def test_range_since_still_rejects_a_window_it_cannot_apply() -> None:
    """An unusable value stays an error, and the message names today."""
    from datetime import UTC, datetime

    from dashboard.metrics import _range_since
    from exceptions import ValidationError

    with pytest.raises(ValidationError) as excinfo:
        _range_since({"time_range": "sometime last spring"})

    message = str(excinfo.value)
    assert "last_<N>d" in message
    assert "date_from" in message
    # Today is named so the caller can work out a real range instead of
    # reaching for whichever preset looks closest.
    assert datetime.now(UTC).date().isoformat() in message


def test_range_since_rejects_a_day_count_out_of_range() -> None:
    """A trailing window has a bound, so a silly N is an error not a window."""
    from dashboard.metrics import _range_since
    from exceptions import ValidationError

    with pytest.raises(ValidationError):
        _range_since({"time_range": "last_0d"})
    with pytest.raises(ValidationError):
        _range_since({"time_range": "last_400d"})


def test_previous_range_understands_an_arbitrary_day_count() -> None:
    """The period-over-period delta must work for last_5d, not just the presets."""
    from dashboard.metrics import _previous_range, _range_since

    window = _previous_range({"time_range": "last_5d"})
    assert window is not None
    prev_start, prev_end = window
    # The previous window is the same length, ending where the current one
    # starts. Compared loosely because both ends are derived from now().
    assert (prev_end - prev_start).days == 5
    current_start = _range_since({"time_range": "last_5d"})
    assert current_start is not None
    assert abs((prev_end - current_start).total_seconds()) < 5


def test_last_month_is_a_calendar_month_not_thirty_days() -> None:
    """"Last month" asked with last_30d started mid-month and missed the rest.

    Four entities moved in August; last_30d began on the 23rd and found three.
    The window has to be the calendar month, so it needs its own value.
    """
    from datetime import UTC, datetime

    from dashboard.metrics import _range_since, _range_until

    since = _range_since({"time_range": "last_month"})
    until = _range_until({"time_range": "last_month"})
    today = datetime.now(UTC)

    assert since is not None and until is not None
    assert since.day == 1
    # Ends exactly where this month starts, so the two never overlap.
    assert until.day == 1
    assert (until.year, until.month) == (today.year, today.month)
    assert since < until


def test_this_month_and_last_month_do_not_overlap() -> None:
    """Consecutive calendar windows must partition, not double count."""
    from dashboard.metrics import _range_since, _range_until

    last_until = _range_until({"time_range": "last_month"})
    this_since = _range_since({"time_range": "this_month"})
    assert last_until == this_since


def test_last_month_is_offered_in_the_vocabulary() -> None:
    """The error message lists what is accepted, so it has to include this."""
    from dashboard.metrics import TIME_RANGE_VALUES

    assert "last_month" in TIME_RANGE_VALUES
