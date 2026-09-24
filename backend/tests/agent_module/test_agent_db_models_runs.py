from __future__ import annotations


def _create_definition(agent_db_model_service, name: str) -> str:  # noqa: ANN001
    definition = agent_db_model_service.create_definition(
        "org-1",
        {
            "name": name,
            "display_name": "Run Agent",
            "description": "Agent used for run persistence tests",
            "system_prompt": "You are a run persistence testing agent.",
            "allowed_tools": [],
            "constraints": {"max_iterations": 3, "require_approval": []},
            "suggestions": [],
            "is_active": True,
        },
    )
    return definition.definition_id


def test_run_crud_and_tenant_scoped_listing(agent_db_model_service) -> None:
    definition_id = _create_definition(agent_db_model_service, "run_agent")
    session = agent_db_model_service.create_session(
        definition_id, "user-1", "org-1", {"source": "test"}
    )
    created = agent_db_model_service.create_run(
        {
            "organization_id": "org-1",
            "definition_id": definition_id,
            "session_id": session.session_id,
            "user_id": "user-1",
            "status": "running",
            "input_text": "Summarize",
            "execution_context": {"runtime": {"organization_id": "org-1"}},
            "backend_metadata": {"backend": "fake"},
        }
    )

    fetched = agent_db_model_service.get_run(created.run_id, "org-1")
    assert fetched is not None
    assert fetched.status == "running"
    assert agent_db_model_service.get_run(created.run_id, "org-2") is None

    updated = agent_db_model_service.update_run(
        created.run_id,
        "org-1",
        {"status": "completed", "output_text": "Done"},
    )
    assert updated is not None
    assert updated.status == "completed"
    assert updated.output_text == "Done"

    rows, total = agent_db_model_service.list_runs(
        "org-1", limit=10, offset=0, status="completed"
    )
    assert total == 1
    assert rows[0].run_id == created.run_id

    wrong_org_rows, wrong_org_total = agent_db_model_service.list_runs(
        "org-2", limit=10, offset=0
    )
    assert wrong_org_rows == []
    assert wrong_org_total == 0
