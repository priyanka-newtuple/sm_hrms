from __future__ import annotations

from exceptions import ServiceError


def test_tools_controller_exposes_catalog_preset_execute_and_compatibility_routes(
    tools_client,
    viewer_headers,
    recruiter_headers,
) -> None:
    catalog_response = tools_client.get("/tools/catalog", headers=viewer_headers)
    assert catalog_response.status_code == 200
    assert catalog_response.json()["default_tools"]

    descriptor_response = tools_client.get("/tools/catalog/read_document", headers=viewer_headers)
    assert descriptor_response.status_code == 200
    assert descriptor_response.json()["name"] == "read_document"

    preset_response = tools_client.get("/tools/presets", headers=viewer_headers)
    assert preset_response.status_code == 200
    assert "extraction_only" in preset_response.json()["presets"]

    preset_detail_response = tools_client.get("/tools/presets/read_only", headers=viewer_headers)
    assert preset_detail_response.status_code == 200
    assert preset_detail_response.json()["name"] == "Read Only"

    execute_response = tools_client.post(
        "/tools/execute",
        headers=recruiter_headers,
        json={"tool_name": "add_stage_comment", "arguments": {"entity_id": "entity-1", "text": "hello"}},
    )
    assert execute_response.status_code == 200
    execute_payload = execute_response.json()["result"]
    assert execute_payload["execution_backend"] == "modular"
    assert execute_payload["execution_id"]

    document_config_catalog_response = tools_client.get("/config/document-types/tools", headers=viewer_headers)
    assert document_config_catalog_response.status_code == 200
    assert document_config_catalog_response.json()["tools"]

    document_config_preset_response = tools_client.get("/config/document-types/tools/presets", headers=viewer_headers)
    assert document_config_preset_response.status_code == 200
    assert "read_only" in document_config_preset_response.json()["presets"]


def test_tools_controller_exposes_admin_execution_history_routes(
    tools_client,
    admin_headers,
    recruiter_headers,
) -> None:
    execute_response = tools_client.post(
        "/tools/execute",
        headers=recruiter_headers,
        json={"tool_name": "add_stage_comment", "arguments": {"entity_id": "entity-1", "text": "audit me"}},
    )
    execution_id = execute_response.json()["result"]["execution_id"]

    list_response = tools_client.get("/tools/executions", headers=admin_headers)
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload["total"] == 1
    assert list_payload["items"][0]["id"] == execution_id

    detail_response = tools_client.get(f"/tools/executions/{execution_id}", headers=admin_headers)
    assert detail_response.status_code == 200
    assert detail_response.json()["tool_name"] == "add_stage_comment"


def test_tools_execution_history_routes_require_admin(tools_client, recruiter_headers) -> None:
    response = tools_client.get("/tools/executions", headers=recruiter_headers)
    assert response.status_code == 403


def test_tools_controller_maps_manager_errors_to_500(tools_client, tools_manager, viewer_headers, monkeypatch) -> None:
    def _raise_error():
        raise ServiceError("catalog unavailable")

    monkeypatch.setattr(tools_manager, "get_catalog", _raise_error)
    response = tools_client.get("/tools/catalog", headers=viewer_headers)
    assert response.status_code == 500
