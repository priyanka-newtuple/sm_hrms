from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .factories import build_trace_events, build_trace_run_payload


def test_persist_trace_and_list_filters(agent_db_model_service) -> None:
    first = agent_db_model_service.persist_trace(
        build_trace_run_payload(id="run-1", status="success", agent_name="recruitment_assistant", run_type="persistent"),
        build_trace_events(),
    )
    second = agent_db_model_service.persist_trace(
        build_trace_run_payload(id="run-2", status="error", agent_name="document_processor", run_type="ephemeral"),
        build_trace_events(),
    )

    success_rows, success_total = agent_db_model_service.list_trace_runs(
        "org-1",
        limit=10,
        offset=0,
        status="success",
    )
    assert success_total == 1
    assert [item.id for item in success_rows] == [first.id]

    filtered_rows, filtered_total = agent_db_model_service.list_trace_runs(
        "org-1",
        limit=10,
        offset=0,
        agent_name="document_processor",
        run_type="ephemeral",
    )
    assert filtered_total == 1
    assert [item.id for item in filtered_rows] == [second.id]

    detail = agent_db_model_service.get_trace_run(first.id, "org-1")
    assert detail is not None
    events = agent_db_model_service.list_trace_events(first.id)
    assert [item.seq for item in events] == [1, 2]


def test_delete_expired_traces_removes_runs_and_events(agent_db_model_service) -> None:
    expired_run = agent_db_model_service.persist_trace(
        build_trace_run_payload(
            id="expired-run",
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        ),
        build_trace_events(),
    )

    assert agent_db_model_service.get_trace_run(expired_run.id, "org-1") is None
    assert agent_db_model_service.list_trace_events(expired_run.id) == []

    active_run = agent_db_model_service.persist_trace(
        build_trace_run_payload(id="active-run", expires_at=datetime.now(timezone.utc) + timedelta(days=1)),
        build_trace_events(),
    )
    agent_db_model_service.delete_expired_traces(datetime.now(timezone.utc))
    assert agent_db_model_service.get_trace_run(active_run.id, "org-1") is not None
