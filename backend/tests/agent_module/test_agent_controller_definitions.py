from __future__ import annotations

import pytest

from exceptions import NotFoundError

from .factories import TOOL_ID, build_definition_create_payload, build_definition_update_payload


def test_definitions_include_seeded_defaults(agent_client, admin_headers) -> None:
    definitions_response = agent_client.get("/agent/definitions", headers=admin_headers)
    assert definitions_response.status_code == 200

    definitions = definitions_response.json()
    assert len(definitions) >= 4
    assert any(item["name"] == "recruitment_assistant" for item in definitions)
    assert any(item["name"] == "platform_readonly_assistant" for item in definitions)


def test_agent_mode_agent_hidden_from_definitions_list(agent_client, admin_headers) -> None:
    definitions = agent_client.get("/agent/definitions", headers=admin_headers).json()
    assert all(item["name"] != "agent_mode" for item in definitions)


def test_get_agent_mode_definition_returns_the_builtin(agent_client, admin_headers) -> None:
    response = agent_client.get("/agent/definitions/agent-mode", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "agent_mode"
    assert body["is_system"] is True


def test_agent_mode_agent_can_be_edited(agent_client, admin_headers) -> None:
    agent_mode = agent_client.get("/agent/definitions/agent-mode", headers=admin_headers).json()
    update_response = agent_client.patch(
        f"/agent/definitions/{agent_mode['definition_id']}",
        json=build_definition_update_payload(display_name="Tuned Assistant"),
        headers=admin_headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["display_name"] == "Tuned Assistant"


def test_agent_mode_edits_survive_reseeding(agent_client, admin_headers) -> None:
    """An edit must not be reverted by the seeding pass that runs on every read.

    ``ensure_builtin_definitions`` runs on each definitions request, and used to
    force-resync agent_mode from the template — so a saved change disappeared on
    the next page load. The GET below re-triggers that pass.
    """
    agent_mode = agent_client.get("/agent/definitions/agent-mode", headers=admin_headers).json()
    tuned_prompt = "You are a tuned Agent Mode assistant."

    update_response = agent_client.patch(
        f"/agent/definitions/{agent_mode['definition_id']}",
        json=build_definition_update_payload(system_prompt=tuned_prompt),
        headers=admin_headers,
    )
    assert update_response.status_code == 200

    reread = agent_client.get("/agent/definitions/agent-mode", headers=admin_headers).json()
    assert reread["system_prompt"] == tuned_prompt


def test_agent_mode_agent_cannot_be_deactivated(agent_client, admin_headers) -> None:
    agent_mode = agent_client.get("/agent/definitions/agent-mode", headers=admin_headers).json()
    update_response = agent_client.patch(
        f"/agent/definitions/{agent_mode['definition_id']}",
        json=build_definition_update_payload(is_active=False),
        headers=admin_headers,
    )
    assert update_response.status_code == 400
    assert "cannot be deactivated" in update_response.json()["detail"]


def test_definition_admin_crud_flow(agent_client, admin_headers) -> None:
    create_response = agent_client.post(
        "/agent/definitions",
        json=build_definition_create_payload(),
        headers=admin_headers,
    )
    assert create_response.status_code == 201
    definition_id = create_response.json()["definition_id"]

    update_response = agent_client.patch(
        f"/agent/definitions/{definition_id}",
        json=build_definition_update_payload(display_name="Updated Agent Name"),
        headers=admin_headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["display_name"] == "Updated Agent Name"

    get_response = agent_client.get(f"/agent/definitions/{definition_id}", headers=admin_headers)
    assert get_response.status_code == 200
    assert get_response.json()["display_name"] == "Updated Agent Name"
    assert get_response.json()["allowed_tools"] == [TOOL_ID]


def test_definition_routes_require_admin_role_for_writes(agent_client, viewer_headers) -> None:
    response = agent_client.post(
        "/agent/definitions",
        json=build_definition_create_payload(),
        headers=viewer_headers,
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Forbidden"


def test_definition_get_maps_manager_not_found_to_404(agent_client, agent_manager, admin_headers, monkeypatch) -> None:
    def _raise_not_found(actor: dict[str, object], definition_id: str):
        raise NotFoundError(f"definition {definition_id} missing")

    monkeypatch.setattr(agent_manager, "get_definition_for_actor", _raise_not_found)
    response = agent_client.get("/agent/definitions/missing-definition", headers=admin_headers)
    assert response.status_code == 404
    assert response.json()["detail"] == "definition missing-definition missing"
