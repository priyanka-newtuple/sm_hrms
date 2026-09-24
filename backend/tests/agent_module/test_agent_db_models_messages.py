from __future__ import annotations


def test_message_crud_and_pending_action_updates(agent_db_model_service) -> None:
    definition = agent_db_model_service.create_definition(
        "org-1",
        {
            "name": "message_agent",
            "display_name": "Message Agent",
            "description": "Definition for message tests",
            "system_prompt": "You are a message testing agent.",
            "allowed_tools": [],
            "constraints": {"max_iterations": 2, "require_approval": []},
            "suggestions": [],
        },
    )
    session = agent_db_model_service.create_session(definition.definition_id, "user-1", "org-1", None)

    first = agent_db_model_service.create_message(session_id=session.session_id, role="user", content="hello")
    second = agent_db_model_service.create_message(
        session_id=session.session_id,
        role="agent",
        content="approval required",
        pending_actions=[
            {"action_id": "action-1", "tool": "list_entity_types", "status": "pending"},
            {"action_id": "action-2", "tool": "get_entity", "status": "pending"},
        ],
        tokens_used=5,
    )

    fetched = agent_db_model_service.get_message(second.message_id)
    assert fetched is not None
    assert fetched.tokens_used == 5

    rows = agent_db_model_service.list_messages(session.session_id)
    assert [item.message_id for item in rows] == [first.message_id, second.message_id]

    updated = agent_db_model_service.update_pending_action(
        second.message_id,
        "action-1",
        {"status": "approved", "result": {"count": 1}},
    )
    assert updated is not None
    assert updated.pending_actions[0]["status"] == "approved"
    assert updated.pending_actions[1]["status"] == "pending"

    assert agent_db_model_service.update_pending_action(second.message_id, "missing-action", {"status": "approved"}) is None
