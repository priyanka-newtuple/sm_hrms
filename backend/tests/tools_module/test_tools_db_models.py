from __future__ import annotations


def test_tools_model_service_creates_gets_and_lists_execution_logs(tools_db_model_service) -> None:
    created = tools_db_model_service.create_execution_log(
        {
            "organization_id": "org-1",
            "user_id": "user-1",
            "actor_id": "user-1",
            "actor_type": "USER",
            "source": "agent",
            "tool_name": "add_stage_comment",
            "arguments": {"entity_id": "entity-1"},
            "result": {"ok": True},
            "success": True,
            "duration_ms": 42,
            "execution_backend": "modular",
            "metadata": {"request_origin": "test"},
        }
    )

    fetched = tools_db_model_service.get_execution_log(created.id, "org-1")
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.metadata == {"request_origin": "test"}

    rows, total = tools_db_model_service.list_execution_logs("org-1", limit=20, offset=0)
    assert total == 1
    assert rows[0].id == created.id


def test_tools_model_service_filters_execution_logs(tools_db_model_service) -> None:
    tools_db_model_service.create_execution_log(
        {
            "organization_id": "org-1",
            "source": "agent",
            "tool_name": "add_stage_comment",
            "arguments": {},
            "result": {},
            "success": True,
            "execution_backend": "modular",
        }
    )
    tools_db_model_service.create_execution_log(
        {
            "organization_id": "org-1",
            "source": "mcp",
            "tool_name": "read_document",
            "arguments": {},
            "result": {},
            "success": False,
            "execution_backend": "platform_runtime",
        }
    )

    rows, total = tools_db_model_service.list_execution_logs(
        "org-1",
        limit=20,
        offset=0,
        tool_name="read_document",
        source="mcp",
        success=False,
        execution_backend="platform_runtime",
    )
    assert total == 1
    assert rows[0].tool_name == "read_document"
    assert rows[0].source == "mcp"
