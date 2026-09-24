from __future__ import annotations


def _create_definition(agent_db_model_service, name: str) -> str:  # noqa: ANN001
    definition = agent_db_model_service.create_definition(
        "org-1",
        {
            "name": name,
            "display_name": name.replace("_", " ").title(),
            "description": f"{name} definition",
            "system_prompt": f"You are {name}.",
            "allowed_tools": [],
            "constraints": {"max_iterations": 2, "require_approval": []},
            "suggestions": [],
        },
    )
    return definition.definition_id


def test_session_crud_and_scoped_lookup(agent_db_model_service) -> None:
    definition_id = _create_definition(agent_db_model_service, "session_agent")
    session = agent_db_model_service.create_session(
        definition_id=definition_id,
        user_id="user-1",
        organization_id="org-1",
        context={"entity_id": "entity-1"},
    )

    fetched = agent_db_model_service.get_session(session.session_id, user_id="user-1", organization_id="org-1")
    assert fetched is not None
    assert fetched.context == {"entity_id": "entity-1"}

    wrong_user = agent_db_model_service.get_session(session.session_id, user_id="user-2", organization_id="org-1")
    assert wrong_user is None

    updated = agent_db_model_service.update_session(
        session.session_id,
        context={"entity_id": "entity-2"},
        title="Pipeline summary",
        token_delta=9,
        message_delta=2,
    )
    assert updated is not None
    assert updated.context == {"entity_id": "entity-2"}
    assert updated.title == "Pipeline summary"
    assert updated.total_tokens == 9
    assert updated.message_count == 2

    assert agent_db_model_service.delete_session(session.session_id, "user-2", "org-1") is False
    assert agent_db_model_service.delete_session(session.session_id, "user-1", "org-2") is False
    assert agent_db_model_service.delete_session(session.session_id, "user-1", "org-1") is True
    assert agent_db_model_service.get_session(session.session_id, user_id="user-1", organization_id="org-1") is None


def test_session_list_orders_by_recent_update_and_delete_cascades_messages(agent_db_model_service) -> None:
    first_definition_id = _create_definition(agent_db_model_service, "first_session_agent")
    second_definition_id = _create_definition(agent_db_model_service, "second_session_agent")
    first = agent_db_model_service.create_session(first_definition_id, "user-1", "org-1", None)
    second = agent_db_model_service.create_session(second_definition_id, "user-1", "org-1", None)
    other_org = agent_db_model_service.create_session(second_definition_id, "user-1", "org-2", None)

    agent_db_model_service.create_message(session_id=first.session_id, role="user", content="first")
    agent_db_model_service.create_message(session_id=second.session_id, role="user", content="second")
    agent_db_model_service.update_session(first.session_id, title="Latest session")

    rows = agent_db_model_service.list_sessions("user-1", "org-1", limit=10, offset=0)
    assert [item.session_id for item in rows][:2] == [first.session_id, second.session_id]
    assert other_org.session_id not in {item.session_id for item in rows}

    assert len(agent_db_model_service.list_messages(first.session_id)) == 1
    assert agent_db_model_service.delete_session(first.session_id, "user-1", "org-1") is True
    assert agent_db_model_service.list_messages(first.session_id) == []
