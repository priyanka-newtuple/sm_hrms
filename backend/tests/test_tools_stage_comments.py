"""Agent Mode must read a record's comments, not the calendar."""

from __future__ import annotations

from types import SimpleNamespace as NS

import pytest

from entities.models.response import (
    EntityRecordListResponse,
    EntityRecordResponse,
    EntityTypeRecordResponse,
)
from exceptions import NotFoundError, PersistenceError, ValidationError
from tools.manager import ToolsServiceManager
from tools.models.interface import ToolExecutionContext

ORG = "org-1"
ENTITY_UUID = "63751299-58ca-4030-bab9-e85dbc23aabe"


def _comment(cid: str, text: str, created_at: str) -> NS:
    return NS(
        id=cid,
        text=text,
        author_name="Aayush",
        author_id="u-1",
        state_name="Screening",
        created_at=created_at,
        reply_count=0,
    )


def _manager(comments: list[NS]) -> ToolsServiceManager:
    manager = ToolsServiceManager.__new__(ToolsServiceManager)
    record = EntityRecordResponse(
        entity_id=ENTITY_UUID,
        organization_id=ORG,
        entity_type_id="type-1",
        data={"identifier": "client166"},
    )

    def _get_for_actor(actor, entity_id, organization_id=None):
        if entity_id != ENTITY_UUID:
            raise NotFoundError(f"entity record '{entity_id}' not found")
        return record

    # Real response models on purpose: a loose stub let a wrong field name
    # ('records' instead of 'items') pass here and fail in Agent Mode.
    manager.entities_service_manager = NS(
        get_entity_record_for_actor=_get_for_actor,
        list_entity_type_records=lambda **kw: [
            EntityTypeRecordResponse(entity_type_id="type-1", organization_id=ORG, name="client")
        ],
        list_entity_records_for_actor=lambda *a, **kw: EntityRecordListResponse(
            organization_id=ORG, items=[record]
        ),
    )
    manager.comments_service_manager = NS(
        list_comments_for_agent=lambda actor, entity_id, **kw: NS(
            comments=comments, total=len(comments)
        )
    )
    return manager


def _context() -> ToolExecutionContext:
    return ToolExecutionContext(organization_id=ORG, user_id="u-1")


def test_returns_the_records_real_comments() -> None:
    manager = _manager(
        [
            _comment("c1", "Older note", "2026-08-01T10:00:00+00:00"),
            _comment("c2", "Newest note", "2026-08-24T06:48:02+00:00"),
        ]
    )

    result = manager._execute_list_stage_comments({"entity_id": ENTITY_UUID}, _context())

    assert result.success is True
    assert result.output["count"] == 2
    assert result.output["comments"][0]["text"] == "Newest note"
    assert result.output["comments"][0]["author"] == "Aayush"


def test_accepts_the_human_identifier() -> None:
    """The agent sends "client166" — the name a user sees, not the id."""
    manager = _manager([_comment("c1", "Note", "2026-08-01T10:00:00+00:00")])

    result = manager._execute_list_stage_comments({"entity_id": "client166"}, _context())

    assert result.output["entity_id"] == ENTITY_UUID
    assert result.output["count"] == 1


def test_mentions_render_as_plain_text() -> None:
    manager = _manager([_comment("c1", "ping @[Kai Tuple](u-9)", "2026-08-01T10:00:00+00:00")])

    result = manager._execute_list_stage_comments({"entity_id": ENTITY_UUID}, _context())

    assert result.output["comments"][0]["text"] == "ping @Kai Tuple"


def test_unknown_record_is_an_error_not_an_empty_list() -> None:
    """An empty list is what made the agent report "no comments"."""
    manager = _manager([])

    with pytest.raises(NotFoundError, match="nope"):
        manager._execute_list_stage_comments({"entity_id": "nope"}, _context())


def test_limit_caps_the_result() -> None:
    manager = _manager(
        [_comment(f"c{i}", f"Note {i}", f"2026-08-0{i}T10:00:00+00:00") for i in range(1, 6)]
    )

    result = manager._execute_list_stage_comments(
        {"entity_id": ENTITY_UUID, "limit": 2}, _context()
    )

    assert result.output["count"] == 2


def test_list_events_no_longer_claims_to_be_the_activity_timeline() -> None:
    """Its old description is why the agent chose it for a comments question."""
    import inspect

    import tools.manager as tm

    source = inspect.getsource(tm)
    assert '"Get the event timeline for an entity"' not in source
    assert "use list_stage_comments for comments" in source


def test_tools_manager_owns_no_database_sessions() -> None:
    """Session handling belongs in the comments module, not the tools layer."""
    import inspect

    import tools.manager as tm

    source = inspect.getsource(tm)
    assert "get_db_session" not in source
    assert "db.close()" not in source


def _multi_record_manager(identifiers: dict[str, str]) -> ToolsServiceManager:
    manager = ToolsServiceManager.__new__(ToolsServiceManager)
    records = [
        EntityRecordResponse(
            entity_id=eid, organization_id=ORG, entity_type_id="type-1", data={"identifier": ident}
        )
        for eid, ident in identifiers.items()
    ]

    def _get_for_actor(actor, entity_id, organization_id=None):
        raise NotFoundError(f"entity record '{entity_id}' not found")

    manager.entities_service_manager = NS(
        get_entity_record_for_actor=_get_for_actor,
        list_entity_type_records=lambda **kw: [
            EntityTypeRecordResponse(entity_type_id="type-1", organization_id=ORG, name="client")
        ],
        list_entity_records_for_actor=lambda *a, **kw: EntityRecordListResponse(
            organization_id=ORG, items=records
        ),
    )
    manager.comments_service_manager = NS(
        list_comments_for_agent=lambda actor, entity_id, **kw: NS(comments=[], total=0)
    )
    return manager


def test_shortened_identifier_resolves_when_it_matches_one_record() -> None:
    """Agents quote a long title back in shortened form."""
    manager = _multi_record_manager(
        {"e-1": '[B/E] "Ticket comments/updates" question in Agent Mode reads calendar events'}
    )

    result = manager._execute_list_stage_comments(
        {"entity_id": "[B/E] Ticket comments"}, _context()
    )

    assert result.output["entity_id"] == "e-1"


def test_ambiguous_partial_match_names_the_candidates() -> None:
    """Guessing one would show the wrong comments; "not found" would be a lie."""
    manager = _multi_record_manager({"e-1": "Ticket alpha", "e-2": "Ticket beta"})

    with pytest.raises(ValidationError, match="matches 2 records"):
        manager._execute_list_stage_comments({"entity_id": "Ticket"}, _context())


def test_punctuation_only_name_matches_nothing() -> None:
    """"---" normalizes to empty; it must not match a record with a blank identifier."""
    manager = _multi_record_manager({"e-1": "", "e-2": "Ticket alpha"})

    with pytest.raises(NotFoundError):
        manager._execute_list_stage_comments({"entity_id": "---"}, _context())


def test_the_log_records_the_resolved_id() -> None:
    manager = ToolsServiceManager.__new__(ToolsServiceManager)
    long_name = '[B/E] "Ticket comments/updates" question in Agent Mode'

    payload = manager._build_execution_log_payload(
        context=ToolExecutionContext(organization_id=ORG),
        tool_name="list_stage_comments",
        arguments={"entity_id": long_name},
        execution_backend="modular",
        duration_ms=1,
        result=NS(output={"entity_id": ENTITY_UUID}, success=True, error=None),
        error=None,
    )

    assert payload["entity_id"] == ENTITY_UUID
    assert payload["arguments"] == {"entity_id": long_name}


def _manager_whose_log_raises(exc: Exception) -> ToolsServiceManager:
    manager = ToolsServiceManager.__new__(ToolsServiceManager)
    manager.db_model_service = NS(
        create_execution_log=lambda payload: (_ for _ in ()).throw(exc)
    )
    return manager


def test_a_failing_log_write_does_not_fail_the_call() -> None:
    """The comments are already fetched; a log failure must not discard them."""
    manager = _manager_whose_log_raises(PersistenceError("db down"))

    assert manager._persist_execution_result({"tool_name": "list_stage_comments"}) is None


def test_a_programming_error_in_the_log_still_surfaces() -> None:
    """Best-effort covers infrastructure failures, not our own bugs."""
    manager = _manager_whose_log_raises(TypeError("payload contract changed"))

    with pytest.raises(TypeError):
        manager._persist_execution_result({"tool_name": "list_stage_comments"})


def test_a_name_passed_as_identifier_never_reaches_the_log_id_column() -> None:
    """entity_id is ids only now, so the overflow cannot happen by construction."""
    manager = ToolsServiceManager.__new__(ToolsServiceManager)
    long_name = '[B/E] "Ticket comments/updates" question in Agent Mode reads calendar events'

    entity_id, _ = manager._resolve_execution_entity_metadata(
        ToolExecutionContext(organization_id=ORG), {"identifier": long_name}
    )

    assert entity_id is None


def test_identifier_resolves_the_record() -> None:
    manager = _manager([_comment("c1", "Note", "2026-08-01T10:00:00+00:00")])

    result = manager._execute_list_stage_comments({"identifier": "client166"}, _context())

    assert result.output["entity_id"] == ENTITY_UUID
    assert result.output["count"] == 1
