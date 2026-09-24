"""Table-view numeric summary row — backend behaviour.

Scenarios follow `design_docs/tony_table_view_summary_row_spec.md`.

Nothing about the aggregate or the permission decision is mocked: the SQL runs
against real Postgres over real seeded rows, and the permission helpers are
called with real `EntityReadPolicy` objects. The only stubs are collaborators a
totals query never consults (audit, blob storage, and friends), so that a
manager can be constructed at all.

Deliberately its own file rather than an addition to `test_workflow_module.py`:
that module cannot currently be collected — its manager fixtures predate the
current `WorkflowServiceManager.__init__` signature — so tests added there would
never run.
"""

from __future__ import annotations

import json
import os
import uuid
from decimal import Decimal
from unittest.mock import Mock

import pytest
from sqlalchemy import text

from common.configuration import Configuration, get_configuration
from common.protocols import EntityReadPolicy
from workflow_manager_factory import NoActiveFormsManager
from workflow.db_models import WorkflowEnrollmentSummaryRow, WorkflowModelService
from workflow.services.enrollment_summary import EnrollmentSummaryService
from workflow.manager import WorkflowServiceManager
from workflow.models.interface import (
    EnrollmentAggregateFilters,
    FieldNumericAggregate,
    FieldTotalAccumulator,
    FieldTotalErrorCode,
    ScanLimit,
)
from workflow.models.response import FieldTotalError, FieldTotalValue

ORG_ID = "test-org-1"
MACHINE_NAME = "totals_board"
ENTITY_TYPE_NAME = "totals_item"
STATE_ALPHA = "alpha"
STATE_BETA = "beta"

APP_SCHEMA = os.environ.get("POSTGRES_APP_SCHEMA", "modular_backend")
RUNTIME_SCHEMA = f"{APP_SCHEMA}_runtime"
DEFINITIONS_SCHEMA = f"{APP_SCHEMA}_definitions"


def _currency(amount: str, code: str) -> dict[str, str]:
    return {"__type": "currency", "amount": amount, "currency_code": code}


# One dataset covering every value shape the spec calls out, so the assertions
# below read as questions about behaviour rather than about fixture wiring.
#   budget          - clean numbers, a numeric string, a null, and garbage
#   fee             - one consistent currency
#   mixed_fee       - several currencies
#   blank_code_fee  - blank / whitespace currency codes
#   all_null        - present on no record at all
#   label           - text, never summable
SEEDED_RECORDS: list[dict[str, object]] = [
    {
        "state": STATE_ALPHA,
        "data": {
            "identifier": "R-1",
            "budget": 100,
            "fee": _currency("10", "USD"),
            "mixed_fee": _currency("10", "USD"),
            "blank_code_fee": _currency("10", "USD"),
            "label": "one",
        },
    },
    {
        "state": STATE_ALPHA,
        "data": {
            "identifier": "R-2",
            "budget": "250.50",
            "fee": _currency("20", "USD"),
            "mixed_fee": _currency("20", "EUR"),
            "blank_code_fee": _currency("20", " "),
            "label": "two",
        },
    },
    {
        "state": STATE_ALPHA,
        "data": {"identifier": "R-3", "budget": None, "fee": None, "label": "three"},
    },
    {
        "state": STATE_BETA,
        "data": {
            "identifier": "R-4",
            "budget": "not-a-number",
            "fee": _currency("30", "USD"),
            "mixed_fee": _currency("30", "MXN"),
            "blank_code_fee": _currency("30", ""),
            "label": "four",
        },
    },
    {
        "state": STATE_BETA,
        "data": {"identifier": "R-5", "budget": 49.5, "label": "five"},
    },
]

# budget: 100 + 250.50 + 49.5   (null, "not-a-number" and the missing key skipped)
EXPECTED_BUDGET_TOTAL = Decimal("400.00")
EXPECTED_BUDGET_ALPHA = Decimal("350.50")  # states are filtered independently
EXPECTED_FEE_TOTAL = Decimal("60")


@pytest.fixture(scope="module")
def seeded_workflow(entities_db_service_manager):
    """A real workflow with real enrollments, torn down afterwards."""
    engine = entities_db_service_manager.postgres_db_service().engine
    entity_type_id = str(uuid.uuid4())
    workflow_id = str(uuid.uuid4())
    entity_ids = [str(uuid.uuid4()) for _ in SEEDED_RECORDS]

    with engine.begin() as conn:
        conn.execute(
            text(
                f'INSERT INTO "{DEFINITIONS_SCHEMA}".entity_types '
                '(entity_type_id, organization_id, name, "schema") '
                "VALUES (:id, :org, :name, '{}')"
            ),
            {"id": entity_type_id, "org": ORG_ID, "name": ENTITY_TYPE_NAME},
        )
        conn.execute(
            text(
                f'INSERT INTO "{APP_SCHEMA}".workflow_state_machines '
                "(id, organization_id, machine_key, machine_name, entity_type, version, "
                "definition_json, is_active) "
                "VALUES (:id, :org, :key, :name, :etype, 1, :definition, TRUE)"
            ),
            {
                "id": workflow_id,
                "org": ORG_ID,
                "key": MACHINE_NAME,
                "name": MACHINE_NAME,
                "etype": ENTITY_TYPE_NAME,
                "definition": json.dumps({"name": MACHINE_NAME, "states": []}),
            },
        )
        for entity_id, record in zip(entity_ids, SEEDED_RECORDS, strict=True):
            conn.execute(
                text(
                    f'INSERT INTO "{RUNTIME_SCHEMA}".entities '
                    "(entity_id, organization_id, entity_type_id, data) "
                    "VALUES (:id, :org, :etype, CAST(:data AS jsonb))"
                ),
                {
                    "id": entity_id,
                    "org": ORG_ID,
                    "etype": entity_type_id,
                    "data": json.dumps(record["data"]),
                },
            )
            conn.execute(
                text(
                    f'INSERT INTO "{RUNTIME_SCHEMA}".entity_state '
                    "(state_id, organization_id, entity_id, workflow_id, current_state) "
                    "VALUES (:sid, :org, :eid, :wid, :state)"
                ),
                {
                    "sid": str(uuid.uuid4()),
                    "org": ORG_ID,
                    "eid": entity_id,
                    "wid": workflow_id,
                    "state": record["state"],
                },
            )

    yield {"entity_type_id": entity_type_id, "workflow_id": workflow_id}

    with engine.begin() as conn:
        conn.execute(
            text(f'DELETE FROM "{RUNTIME_SCHEMA}".entity_state WHERE workflow_id = :wid'),
            {"wid": workflow_id},
        )
        conn.execute(
            text(f'DELETE FROM "{RUNTIME_SCHEMA}".entities WHERE entity_id = ANY(:ids)'),
            {"ids": entity_ids},
        )
        conn.execute(
            text(f'DELETE FROM "{APP_SCHEMA}".workflow_state_machines WHERE id = :wid'),
            {"wid": workflow_id},
        )
        conn.execute(
            text(f'DELETE FROM "{DEFINITIONS_SCHEMA}".entity_types WHERE entity_type_id = :id'),
            {"id": entity_type_id},
        )


@pytest.fixture(scope="module")
def workflow_db(entities_db_service_manager) -> WorkflowModelService:
    return WorkflowModelService(database_service_manager=entities_db_service_manager)


def _filters(seeded, **overrides) -> EnrollmentAggregateFilters:
    """Filter set matching every seeded row, unless a test narrows it."""
    base = {
        "organization_id": ORG_ID,
        "machine_name": MACHINE_NAME,
        "machine_names": None,
        "exclude_states": None,
        "entity_type_name": None,
        "entity_type_id": None,
        "entity_type_ids": {seeded["entity_type_id"]},
        "include_archived": False,
        "entity_ids": None,
        "assignee_ids": None,
        "include_unassigned": False,
        "search": None,
        "field_filters": None,
        "searchable_fields_by_type": None,
        "read_conditions_by_type": None,
        "identifier": None,
    }
    base.update(overrides)
    return EnrollmentAggregateFilters(**base)


def _sum(workflow_db, seeded, fields, **overrides):
    # `current_state` is the query's own argument, not part of the filter set —
    # the counts span every state while a total describes only the rows shown.
    current_state = overrides.pop("current_state", None)
    return workflow_db.sum_enrollment_fields(
        _filters(seeded, **overrides),
        sum_fields=dict.fromkeys(fields),
        current_state=current_state,
    )


# --------------------------------------------------------------------------
# Positive
# --------------------------------------------------------------------------


def test_one_numeric_column_totals_correctly(workflow_db, seeded_workflow) -> None:
    """A clean numeric column returns the sum of its real values."""
    assert _sum(workflow_db, seeded_workflow, ["budget"])["budget"].total == EXPECTED_BUDGET_TOTAL


def test_multiple_columns_are_totalled_independently(workflow_db, seeded_workflow) -> None:
    """Each requested column is aggregated on its own, in one query."""
    totals = _sum(workflow_db, seeded_workflow, ["budget", "fee"])
    assert totals["budget"].total == EXPECTED_BUDGET_TOTAL
    assert totals["fee"].total == EXPECTED_FEE_TOTAL


def test_single_currency_column_reports_its_code(workflow_db, seeded_workflow) -> None:
    """A consistent currency column carries the code, so the client never guesses."""
    totals = _sum(workflow_db, seeded_workflow, ["fee"])
    assert totals["fee"].total == EXPECTED_FEE_TOTAL
    assert totals["fee"].currency_codes == frozenset({"USD"})


def test_plain_number_column_carries_no_currency(workflow_db, seeded_workflow) -> None:
    """A non-currency column must not acquire a currency from anywhere."""
    assert _sum(workflow_db, seeded_workflow, ["budget"])["budget"].currency_codes == frozenset()


# --------------------------------------------------------------------------
# Filter sensitivity — the total must describe exactly the filtered set
# --------------------------------------------------------------------------


def test_state_filter_narrows_the_total(workflow_db, seeded_workflow) -> None:
    """Pinning a state totals only that state's rows, not the whole board."""
    totals = _sum(workflow_db, seeded_workflow, ["budget"], current_state=STATE_ALPHA)
    assert totals["budget"].total == EXPECTED_BUDGET_ALPHA


def test_removing_the_filter_restores_the_total(workflow_db, seeded_workflow) -> None:
    """The narrowed total is not sticky — it is recomputed per request."""
    narrowed = _sum(workflow_db, seeded_workflow, ["budget"], current_state=STATE_ALPHA)
    full = _sum(workflow_db, seeded_workflow, ["budget"])
    assert narrowed["budget"].total < full["budget"].total == EXPECTED_BUDGET_TOTAL


def test_identifier_filter_narrows_the_total(workflow_db, seeded_workflow) -> None:
    """A row-narrowing filter is reflected in the sum, not just the row list."""
    assert _sum(workflow_db, seeded_workflow, ["budget"], identifier="R-1")[
        "budget"
    ].total == Decimal("100")


def test_search_narrows_the_total(workflow_db, seeded_workflow) -> None:
    """Search participates in the aggregate like every other filter."""
    assert _sum(workflow_db, seeded_workflow, ["budget"], search="R-2")[
        "budget"
    ].total == Decimal("250.50")


def test_a_filter_matching_nothing_totals_nothing(workflow_db, seeded_workflow) -> None:
    """An empty result set must not invent a number."""
    totals = _sum(workflow_db, seeded_workflow, ["budget"], identifier="no-such-record")
    assert totals["budget"].total == Decimal(0)


# --------------------------------------------------------------------------
# Messy data
# --------------------------------------------------------------------------


def test_nulls_and_missing_keys_are_skipped(workflow_db, seeded_workflow) -> None:
    """Two seeded rows carry no usable budget; the total is the rest of them."""
    assert _sum(workflow_db, seeded_workflow, ["budget"])["budget"].total == EXPECTED_BUDGET_TOTAL


def test_a_malformed_value_is_skipped_without_failing_the_query(
    workflow_db, seeded_workflow
) -> None:
    """`"not-a-number"` behaves exactly like a blank — the column still returns
    a real total rather than erroring the whole request."""
    assert _sum(workflow_db, seeded_workflow, ["budget"])["budget"].total == EXPECTED_BUDGET_TOTAL


def test_a_column_present_on_no_row_totals_zero(workflow_db, seeded_workflow) -> None:
    """All-blank is `0`, not absent and not an error."""
    assert _sum(workflow_db, seeded_workflow, ["all_null"])["all_null"].total == Decimal(0)


def test_a_text_column_totals_zero_rather_than_erroring(workflow_db, seeded_workflow) -> None:
    """Nothing stops a caller naming a text column; it must degrade quietly."""
    assert _sum(workflow_db, seeded_workflow, ["label"])["label"].total == Decimal(0)


def test_several_currency_codes_are_all_reported(workflow_db, seeded_workflow) -> None:
    """The aggregate surfaces every distinct code so the manager can refuse."""
    totals = _sum(workflow_db, seeded_workflow, ["mixed_fee"])
    assert totals["mixed_fee"].currency_codes == frozenset({"USD", "EUR", "MXN"})


def test_blank_currency_codes_do_not_count_as_a_currency(workflow_db, seeded_workflow) -> None:
    """Regression: `""` and `" "` codes once registered as distinct currencies on
    the SQL path while the scan path dropped them, so the same column could be
    called mixed-currency or not depending on which path ran."""
    totals = _sum(workflow_db, seeded_workflow, ["blank_code_fee"])
    assert totals["blank_code_fee"].currency_codes == frozenset({"USD"})
    assert totals["blank_code_fee"].total == Decimal("60")


def test_two_currency_columns_are_judged_separately(workflow_db, seeded_workflow) -> None:
    """One mixed column must not suppress a clean one in the same response."""
    totals = _sum(workflow_db, seeded_workflow, ["fee", "mixed_fee"])
    assert totals["fee"].currency_codes == frozenset({"USD"})
    assert len(totals["mixed_fee"].currency_codes) == 3


# --------------------------------------------------------------------------
# Field-level permissions — the SQL path must respect them too
# --------------------------------------------------------------------------


def test_a_field_is_only_summed_for_types_allowed_to_contribute(
    workflow_db, seeded_workflow
) -> None:
    """Scoping a field to another entity type excludes these rows entirely,
    proving the per-type gate is inside the aggregate rather than applied after."""
    totals = workflow_db.sum_enrollment_fields(
        _filters(seeded_workflow), sum_fields={"budget": {"some-other-entity-type"}}
    )
    assert totals["budget"].total == Decimal(0)


def test_no_requested_fields_runs_no_query(workflow_db, seeded_workflow) -> None:
    """The totals aggregate is opt-in; asking for nothing must cost nothing."""
    assert workflow_db.sum_enrollment_fields(_filters(seeded_workflow), sum_fields={}) == {}


# --------------------------------------------------------------------------
# Manager decisions: what the API actually returns
# --------------------------------------------------------------------------


def test_mixed_currency_returns_a_message_naming_the_codes(workflow_db, seeded_workflow) -> None:
    """No number for a column spanning currencies — a fixable, specific message."""
    rendered = EnrollmentSummaryService.field_totals_response(
        _sum(workflow_db, seeded_workflow, ["mixed_fee"])
    )["mixed_fee"]

    assert isinstance(rendered, FieldTotalError)
    assert rendered.error == FieldTotalErrorCode.MIXED_CURRENCY
    assert rendered.currency_codes == ["EUR", "MXN", "USD"]
    for code in ("EUR", "MXN", "USD"):
        assert code in rendered.message


def test_single_currency_renders_a_number_with_its_code(workflow_db, seeded_workflow) -> None:
    """The response carries the currency, so the client never infers it."""
    rendered = EnrollmentSummaryService.field_totals_response(
        _sum(workflow_db, seeded_workflow, ["fee"])
    )["fee"]

    assert isinstance(rendered, FieldTotalValue)
    assert rendered.total == 60.0
    assert rendered.currency_code == "USD"


def test_normalising_the_currency_yields_a_number_on_the_next_request() -> None:
    """The mixed-currency verdict is re-derived per request, never remembered."""
    before = EnrollmentSummaryService.field_totals_response(
        {"fee": FieldNumericAggregate(Decimal("60"), frozenset({"USD", "EUR"}))}
    )["fee"]
    after = EnrollmentSummaryService.field_totals_response(
        {"fee": FieldNumericAggregate(Decimal("60"), frozenset({"USD"}))}
    )["fee"]

    assert isinstance(before, FieldTotalError)
    assert isinstance(after, FieldTotalValue)
    assert after.total == 60.0


# --------------------------------------------------------------------------
# Row-level permissions: which columns may be summed at all
# --------------------------------------------------------------------------


def test_a_masked_field_is_never_summed() -> None:
    """An exact total of masked numbers would hand back what the mask hides,
    so the column is dropped rather than summed."""
    policies = {"t1": EntityReadPolicy(visible_fields={"budget"}, masked_fields={"budget"})}
    assert EnrollmentSummaryService.summable_fields_by_type(policies, {"budget"}) == {}


def test_an_invisible_field_is_never_summed() -> None:
    policies = {"t1": EntityReadPolicy(visible_fields={"other"}, masked_fields=set())}
    assert EnrollmentSummaryService.summable_fields_by_type(policies, {"budget"}) == {}


def test_an_unrestricted_role_may_sum_every_field() -> None:
    """`visible_fields is None` means no field restriction at all."""
    assert EnrollmentSummaryService.summable_fields_by_type(
        {"t1": EntityReadPolicy()}, {"budget"}
    ) == {"budget": None}


def test_a_field_visible_on_only_one_type_is_scoped_to_it() -> None:
    """A mixed-type result set sums the field for the types allowed to see it."""
    policies = {
        "t1": EntityReadPolicy(visible_fields={"budget"}, masked_fields=set()),
        "t2": EntityReadPolicy(visible_fields={"other"}, masked_fields=set()),
    }
    assert EnrollmentSummaryService.summable_fields_by_type(policies, {"budget"}) == {
        "budget": {"t1"}
    }


# --------------------------------------------------------------------------
# Scan path (roles whose row conditions cannot be pushed into SQL)
# --------------------------------------------------------------------------


def _row(entity_id: str, entity_type_id: str = "t1") -> WorkflowEnrollmentSummaryRow:
    return WorkflowEnrollmentSummaryRow(
        state_id=f"state-{entity_id}",
        organization_id=ORG_ID,
        entity_id=entity_id,
        entity_type_id=entity_type_id,
        entity_type=ENTITY_TYPE_NAME,
        entity_data={},
        owner_id=None,
        assignee_id=None,
        due_date=None,
        entity_created_at=None,
        entity_updated_at=None,
        archived_at=None,
        workflow_id="workflow-1",
        machine_name=MACHINE_NAME,
        machine_display_name=MACHINE_NAME,
        machine_version=1,
        current_state=STATE_ALPHA,
        state_version=0,
        machine_definition={},
        state_entered_at=None,
        last_transition_at=None,
        sla_due_at=None,
        enrollment_created_at=None,
    )


def _scan_total(values: list[object], field: str = "budget") -> Decimal:
    """Accumulate values the way the scan path does, from already-masked data."""
    totals: dict[str, FieldTotalAccumulator] = {}
    for index, value in enumerate(values):
        EnrollmentSummaryService.accumulate_field_totals(
            totals, _row(f"e{index}"), {field: value}, {field: None}
        )
    return totals[field].to_aggregate().total


def test_scan_path_matches_the_sql_path_on_the_same_values() -> None:
    """The two paths must never disagree — a role change would otherwise move
    the number rather than only the rows it covers."""
    assert _scan_total([100, "250.50", None, "not-a-number", 49.5]) == EXPECTED_BUDGET_TOTAL


def test_scan_path_reads_currency_amounts_and_codes() -> None:
    totals: dict[str, FieldTotalAccumulator] = {}
    for index in range(2):
        EnrollmentSummaryService.accumulate_field_totals(
            totals, _row(f"e{index}"), {"fee": _currency("10", "USD")}, {"fee": None}
        )
    aggregate = totals["fee"].to_aggregate()
    assert aggregate.total == Decimal("20")
    assert aggregate.currency_codes == frozenset({"USD"})


def test_scan_path_ignores_blank_currency_codes() -> None:
    """Mirror of the SQL-side regression, so the paths stay aligned."""
    totals: dict[str, FieldTotalAccumulator] = {}
    EnrollmentSummaryService.accumulate_field_totals(
        totals, _row("e0"), {"fee": _currency("10", "  ")}, {"fee": None}
    )
    assert totals["fee"].to_aggregate().currency_codes == frozenset()


def test_scan_path_skips_booleans() -> None:
    """`True` is an int in Python; summing it would silently add 1."""
    assert _scan_total([True, False, 5]) == Decimal("5")


def test_scan_path_seeds_a_column_no_row_can_contribute_to() -> None:
    """A field gated to another entity type still reports 0, matching SQL's
    COALESCE, rather than vanishing from the response on one path only."""
    totals: dict[str, FieldTotalAccumulator] = {}
    EnrollmentSummaryService.accumulate_field_totals(
        totals, _row("e0", entity_type_id="t1"), {"budget": 100}, {"budget": {"t2"}}
    )
    assert totals["budget"].to_aggregate().total == Decimal(0)


def test_scan_path_never_reads_unmasked_row_data() -> None:
    """The accumulator is handed the policy-filtered copy; a value present only
    on the raw record must not reach the total."""
    row = _row("e0")
    row.entity_data["budget"] = 999  # raw record value the policy stripped
    totals: dict[str, FieldTotalAccumulator] = {}
    EnrollmentSummaryService.accumulate_field_totals(totals, row, {}, {"budget": None})
    assert totals["budget"].to_aggregate().total == Decimal(0)


# --------------------------------------------------------------------------
# Scan bounds — verified by shrinking the configured limits, not by volume
# --------------------------------------------------------------------------


@pytest.fixture
def scan_manager():
    """A manager whose only real collaborator is a row source we control."""
    # `Configuration()`, not `get_configuration()` — this is the wrapper object
    # `main.py` injects. Passing the parsed model here instead once hid a
    # production-only AttributeError in `_scan_bounds`.
    return WorkflowServiceManager(
        workflow_db_model_service=Mock(),
        database_service_manager=Mock(),
        config=Configuration(),
        entities_service_manager=Mock(),
        roles_manager=Mock(),
        audit_events_service=Mock(),
        forms_service_manager=NoActiveFormsManager(),
        filehandler_service_manager=Mock(),
        user_service_manager=Mock(),
        blob_storage_service=Mock(),
    )


def _unfiltered_request():
    """A request that narrows nothing, so the scan bounds are the only thing under test."""
    return Mock(
        machine_name=MACHINE_NAME,
        machine_names=None,
        exclude_states=None,
        entity_type_name=None,
        entity_type_id=None,
        include_archived=False,
        assignee_ids=None,
        include_unassigned=False,
        search=None,
        field_filters=None,
        identifier=None,
        current_state=None,
        sort_by=None,
        sort_dir="asc",
    )


def _drive_scan(manager, total_rows: int, chunk: int, cap: int, monkeypatch):
    """Walk the real scan loop over `total_rows`; return (rows seen, reads, truncated)."""
    config = get_configuration().workflow_configuration
    monkeypatch.setattr(config, "row_condition_scan_chunk", chunk)
    monkeypatch.setattr(config, "row_condition_scan_cap", cap)

    rows = [_row(f"e{index}") for index in range(total_rows)]
    reads: list[int] = []

    def _list_rows(*, offset=0, limit=50, **_):
        reads.append(limit)
        return rows[offset : offset + limit]

    manager.workflow_db.list_enrollment_summary_rows = _list_rows
    # Visibility is not what these tests are about: every row passes through. The stub goes on
    # the service, not the manager — the scan loop calls it on itself, so a manager-level stub
    # would be silently ignored and the real visibility path would run.
    manager.enrollment_summary._visible_facet_rows = (
        lambda _a, _o, batch, _s, _p=None: ((r, {}) for r in batch)
    )

    scan_limit = ScanLimit()
    request = _unfiltered_request()
    access = Mock(type_ids={"t1"}, sql_conditions={}, policies={})
    seen = list(
        manager.enrollment_summary._scan_visible_facet_rows(
            {"organization_id": ORG_ID},
            ORG_ID,
            request,
            None,
            access,
            Mock(),
            scan_limit,
            current_state=None,
            identifier=None,
        )
    )
    return len(seen), reads, scan_limit.exhausted


@pytest.mark.parametrize("total_rows", [9, 10, 11])
def test_chunk_boundary_reads_every_row(scan_manager, monkeypatch, total_rows) -> None:
    """No row is dropped or double-counted at the edge of a chunk."""
    seen, _, truncated = _drive_scan(
        scan_manager, total_rows, chunk=10, cap=1000, monkeypatch=monkeypatch
    )
    assert seen == total_rows
    assert truncated is False


@pytest.mark.parametrize(
    ("total_rows", "expected_seen", "expected_truncated"),
    [(19, 19, False), (20, 20, True), (21, 20, True)],
)
def test_cap_boundary_stops_and_reports(
    scan_manager, monkeypatch, total_rows, expected_seen, expected_truncated
) -> None:
    """At or under the cap the answer is complete; over it the scan stops and
    says so rather than returning a silent prefix."""
    seen, _, truncated = _drive_scan(
        scan_manager, total_rows, chunk=10, cap=20, monkeypatch=monkeypatch
    )
    assert seen == expected_seen
    assert truncated is expected_truncated


def test_a_cap_smaller_than_the_chunk_is_still_enforced(scan_manager, monkeypatch) -> None:
    """Regression: the cap used to be checked only between reads while each read
    still asked for a whole chunk, so any cap below the chunk size did nothing."""
    seen, reads, truncated = _drive_scan(
        scan_manager, total_rows=5000, chunk=500, cap=100, monkeypatch=monkeypatch
    )
    assert reads == [100], "the read must be shortened to the remaining budget"
    assert seen == 100
    assert truncated is True


def test_a_cap_that_is_not_a_multiple_of_the_chunk_is_respected(
    scan_manager, monkeypatch
) -> None:
    """A cap of 25 with a chunk of 10 reads 10, 10, then 5 — never 30."""
    seen, reads, truncated = _drive_scan(
        scan_manager, total_rows=5000, chunk=10, cap=25, monkeypatch=monkeypatch
    )
    assert reads == [10, 10, 5]
    assert seen == 25
    assert truncated is True


def test_a_short_read_under_a_small_cap_is_not_reported_as_truncated(
    scan_manager, monkeypatch
) -> None:
    """Draining the data before reaching the cap is a complete answer."""
    seen, _, truncated = _drive_scan(
        scan_manager, total_rows=7, chunk=500, cap=100, monkeypatch=monkeypatch
    )
    assert seen == 7
    assert truncated is False
