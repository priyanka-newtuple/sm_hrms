"""Metrics that answer "how many moved into state X" read the live audit table.

Committed transitions moved to the unified `audit_events` table, but three
metrics kept querying the legacy `audit.transition_attempts` table, which is no
longer written (see test_unified_transition_audit.py, which asserts nothing new
lands there). Every one of them returned zero no matter what was asked, so
"how many tickets moved to Done in the last 7 days" answered 0 while the
transitions were sitting in `audit_events`.
"""

from __future__ import annotations

import json
import os
import socket
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

import pytest

from audit.db_models import AuditEventModel
from dashboard.metrics import execute_metric
from workflow.db_models import WorkflowStateMachineModel
from workflow.models.interface import TransitionAuditEventType

_ORG = "metrics-src-org"


def _db_is_reachable() -> bool:
    url = (
        os.environ.get("DATABASE_URL")
        or "postgresql://statemachine:statemachine@modular-db:5432/statemachine"
    )
    parsed = urlparse(url)
    try:
        socket.getaddrinfo(parsed.hostname or "localhost", parsed.port or 5432)
    except OSError:
        return False
    return True


pytestmark = pytest.mark.skipif(not _db_is_reachable(), reason="database host is not reachable")


def _transition(
    session,
    *,
    after_state: str,
    days_ago: float,
    event_type: str | None = None,
    workflow_id: str | None = None,
):
    """Insert one committed transition into `audit_events`."""
    session.add(
        AuditEventModel(
            id=str(uuid.uuid4()),
            organization_id=_ORG,
            metadata_type="TRANSITION",
            entity_id=str(uuid.uuid4()),
            event_type=event_type or TransitionAuditEventType.SUCCEEDED.value,
            actor_type="user",
            after_state=after_state,
            event_metadata={"workflow_id": workflow_id} if workflow_id else None,
            event_timestamp=datetime.now(UTC) - timedelta(days=days_ago),
        )
    )


@pytest.fixture
def metrics_session(entities_db_service_manager):
    """A session with a known set of transitions, cleaned up afterwards."""
    session = entities_db_service_manager.postgres_db_service().get_db_session()
    session.query(AuditEventModel).filter(AuditEventModel.organization_id == _ORG).delete(
        synchronize_session=False
    )
    session.commit()
    #   DONE: 2 inside the last 7 days, 1 well outside it
    #   QA:   1 inside, so a state filter has something to exclude
    _transition(session, after_state="DONE", days_ago=1)
    _transition(session, after_state="DONE", days_ago=3)
    _transition(session, after_state="DONE", days_ago=40)
    _transition(session, after_state="QA", days_ago=2)
    session.commit()
    try:
        yield session
    finally:
        session.query(AuditEventModel).filter(AuditEventModel.organization_id == _ORG).delete(
            synchronize_session=False
        )
        session.commit()
        session.close()


def test_reached_state_counts_transitions_from_the_live_audit_table(metrics_session) -> None:
    """The count comes back non-zero, which it never did off the legacy table."""
    result = execute_metric(
        metrics_session, _ORG, "entities.reached_state", {"state": "DONE", "time_range": "all"}
    )
    assert result["value"] == 3


def test_reached_state_applies_the_requested_window(metrics_session) -> None:
    """ "Moved to Done in the last 7 days" excludes the one from 40 days ago."""
    last_7d = execute_metric(
        metrics_session, _ORG, "entities.reached_state", {"state": "DONE", "time_range": "last_7d"}
    )
    assert last_7d["value"] == 2

    today = execute_metric(
        metrics_session, _ORG, "entities.reached_state", {"state": "DONE", "time_range": "today"}
    )
    assert today["value"] == 0


def test_reached_state_counts_only_the_requested_state(metrics_session) -> None:
    """A DONE question must not pick up the QA transition."""
    result = execute_metric(
        metrics_session, _ORG, "entities.reached_state", {"state": "QA", "time_range": "last_7d"}
    )
    assert result["value"] == 1


def test_reached_state_honors_a_custom_date_range(metrics_session) -> None:
    """Periods with no preset ("the last 5 days") arrive as date_from/date_to."""
    today = datetime.now(UTC).date()
    result = execute_metric(
        metrics_session,
        _ORG,
        "entities.reached_state",
        {
            "state": "DONE",
            "date_from": (today - timedelta(days=5)).isoformat(),
            "date_to": today.isoformat(),
        },
    )
    assert result["value"] == 2


def test_transitions_over_time_charts_only_the_requested_state(metrics_session) -> None:
    """A chart of "moved to Done" must not plot every transition in the org.

    Without the state filter this counted DONE and QA together, so the chart
    was movement in general presented as movement into one state.
    """
    scoped = execute_metric(
        metrics_session,
        _ORG,
        "transitions.over_time",
        {"state": "DONE", "time_range": "last_7d"},
    )
    assert sum(point["value"] for point in scoped["series"]) == 2

    unscoped = execute_metric(
        metrics_session, _ORG, "transitions.over_time", {"time_range": "last_7d"}
    )
    assert sum(point["value"] for point in unscoped["series"]) == 3


def test_transitions_over_time_reads_the_live_audit_table(metrics_session) -> None:
    """The series is populated at all, which it never was off the legacy table."""
    result = execute_metric(metrics_session, _ORG, "transitions.over_time", {"time_range": "all"})
    assert result["series"]


def test_incidents_trend_reads_the_live_audit_table(metrics_session) -> None:
    """Split by transition outcome, from `audit_events` rather than the dead table."""
    result = execute_metric(metrics_session, _ORG, "incidents.trend", {"time_range": "last_30d"})
    assert result["points"]
    assert any(s["key"] == TransitionAuditEventType.SUCCEEDED.value for s in result["series"])


def test_workflow_filter_matches_every_version_of_the_same_workflow(
    entities_db_service_manager,
) -> None:
    """Scoping to one workflow must include entities still on an older version.

    An entity pins the version row it enrolled on, so matching a single row id
    drops everything mid-flight on an earlier version. The workflow id also has
    to be read out of the event metadata now, rather than off a column, so this
    covers both halves of the switch at once.
    """
    session = entities_db_service_manager.postgres_db_service().get_db_session()
    machine_name = f"family_wf_{uuid.uuid4().hex[:8]}"
    v1_id, v2_id = str(uuid.uuid4()), str(uuid.uuid4())
    other_id = str(uuid.uuid4())

    def _definition(name: str) -> str:
        return json.dumps(
            {
                "machine_key": name,
                "name": name,
                "entity_type": "thing",
                "entity_schema": {"entity_type": "thing", "fields": []},
                "initial_state": "INITIAL",
                "states": [{"name": "INITIAL"}, {"name": "DONE"}],
                "transitions": [],
            }
        )

    try:
        for row_id, version, is_active, name in (
            (v1_id, 1, False, machine_name),
            (v2_id, 2, True, machine_name),
            (other_id, 1, True, f"{machine_name}_unrelated"),
        ):
            session.add(
                WorkflowStateMachineModel(
                    id=row_id,
                    organization_id=_ORG,
                    machine_key=name,
                    machine_name=name,
                    entity_type="thing",
                    version=version,
                    is_active=is_active,
                    definition_json=_definition(name),
                )
            )
        # One transition on each version of the workflow, plus one on a
        # different workflow that must not be counted.
        _transition(session, after_state="DONE", days_ago=1, workflow_id=v1_id)
        _transition(session, after_state="DONE", days_ago=1, workflow_id=v2_id)
        _transition(session, after_state="DONE", days_ago=1, workflow_id=other_id)
        session.commit()

        scoped = execute_metric(
            session,
            _ORG,
            "entities.reached_state",
            {"state": "DONE", "time_range": "last_7d", "workflow_id": v2_id},
        )
        assert scoped["value"] == 2, "both versions of the workflow must count"

        # Asking by the older row id resolves to the same family.
        by_v1 = execute_metric(
            session,
            _ORG,
            "entities.reached_state",
            {"state": "DONE", "time_range": "last_7d", "workflow_id": v1_id},
        )
        assert by_v1["value"] == 2

        # The unrelated workflow stays out of it.
        unrelated = execute_metric(
            session,
            _ORG,
            "entities.reached_state",
            {"state": "DONE", "time_range": "last_7d", "workflow_id": other_id},
        )
        assert unrelated["value"] == 1

        # The same scoping over the charted series.
        series = execute_metric(
            session,
            _ORG,
            "transitions.over_time",
            {"state": "DONE", "time_range": "last_7d", "workflow_id": v2_id},
        )
        assert sum(point["value"] for point in series["series"]) == 2
    finally:
        session.query(AuditEventModel).filter(AuditEventModel.organization_id == _ORG).delete(
            synchronize_session=False
        )
        session.query(WorkflowStateMachineModel).filter(
            WorkflowStateMachineModel.id.in_([v1_id, v2_id, other_id])
        ).delete(synchronize_session=False)
        session.commit()
        session.close()


def test_reached_state_list_returns_the_entities_the_count_counts(metrics_session) -> None:
    """The list and the number must never disagree.

    Nothing could list the entities behind the count, so the agent rendered the
    pipeline view instead, which filters on the state an entity is in now and
    ignores the window: the count said 1 and the list showed 4.
    """
    filters = {"state": "DONE", "time_range": "last_7d"}
    count = execute_metric(metrics_session, _ORG, "entities.reached_state", filters)
    listing = execute_metric(metrics_session, _ORG, "entities.reached_state_list", filters)

    assert count["value"] == 2
    assert len(listing["rows"]) == count["value"]


def test_reached_state_list_applies_the_window(metrics_session) -> None:
    """The row for the 40-day-old move must not appear in a 7 day window."""
    week = execute_metric(
        metrics_session,
        _ORG,
        "entities.reached_state_list",
        {"state": "DONE", "time_range": "last_7d"},
    )
    everything = execute_metric(
        metrics_session, _ORG, "entities.reached_state_list", {"state": "DONE", "time_range": "all"}
    )

    assert len(week["rows"]) == 2
    assert len(everything["rows"]) == 3


def test_reached_state_list_counts_one_row_per_entity(metrics_session) -> None:
    """An entity that re-enters the state inside the window is still one ticket."""
    _transition(metrics_session, after_state="DONE", days_ago=2)
    repeat_entity = (
        metrics_session.query(AuditEventModel)
        .filter(AuditEventModel.organization_id == _ORG, AuditEventModel.after_state == "DONE")
        .first()
    )
    metrics_session.add(
        AuditEventModel(
            id=str(uuid.uuid4()),
            organization_id=_ORG,
            metadata_type="TRANSITION",
            entity_id=repeat_entity.entity_id,
            event_type=TransitionAuditEventType.SUCCEEDED.value,
            actor_type="user",
            after_state="DONE",
            event_timestamp=datetime.now(UTC) - timedelta(days=1),
        )
    )
    metrics_session.commit()

    filters = {"state": "DONE", "time_range": "last_7d"}
    count = execute_metric(metrics_session, _ORG, "entities.reached_state", filters)
    listing = execute_metric(metrics_session, _ORG, "entities.reached_state_list", filters)

    ids = [row["entity_id"] for row in listing["rows"]]
    assert len(ids) == len(set(ids))
    assert len(listing["rows"]) == count["value"]


def test_reached_state_list_leaves_out_states_it_was_not_asked_for(metrics_session) -> None:
    """A DONE question must not return the QA row."""
    listing = execute_metric(
        metrics_session,
        _ORG,
        "entities.reached_state_list",
        {"state": "QA", "time_range": "last_7d"},
    )
    assert len(listing["rows"]) == 1


def test_reached_state_list_reports_the_full_total_when_rows_are_capped(
    entities_db_service_manager,
) -> None:
    """Past the row cap the list and the count stop matching, so say the total.

    The rows stop at `limit` while the scalar counts every match. Without the
    total a page of rows reads as the whole set, and the caller reports it as
    the answer - the confident wrong number this metric exists to prevent.
    """
    session = entities_db_service_manager.postgres_db_service().get_db_session()
    session.query(AuditEventModel).filter(
        AuditEventModel.organization_id == _ORG
    ).delete(synchronize_session=False)
    session.commit()
    try:
        for _ in range(7):
            _transition(session, after_state="DONE", days_ago=1)
        session.commit()

        filters = {"state": "DONE", "time_range": "last_7d", "limit": 3}
        listing = execute_metric(session, _ORG, "entities.reached_state_list", filters)
        count = execute_metric(session, _ORG, "entities.reached_state", filters)

        assert len(listing["rows"]) == 3, "rows respect the cap"
        assert listing["total"] == 7, "total ignores the cap"
        assert listing["total"] == count["value"], "total agrees with the scalar"
    finally:
        session.query(AuditEventModel).filter(
            AuditEventModel.organization_id == _ORG
        ).delete(synchronize_session=False)
        session.commit()
        session.close()


def test_reached_state_list_limit_is_bounded(metrics_session) -> None:
    """A silly limit falls back or clamps rather than being taken literally."""
    for bad in ("not a number", 0, -5, 9999):
        listing = execute_metric(
            metrics_session,
            _ORG,
            "entities.reached_state_list",
            {"state": "DONE", "time_range": "all", "limit": bad},
        )
        assert listing["total"] == 3
        assert len(listing["rows"]) <= 3
