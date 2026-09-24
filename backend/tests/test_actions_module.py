from __future__ import annotations

from typing import Any

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from actions.controller import ActionsRestController
from actions.manager import ActionsServiceManager
from exceptions import NotFoundError


class _FakeActionsModelService:
    def __init__(self) -> None:
        self._definitions: list[dict[str, Any]] = [
            {
                "definition_id": "def-1",
                "organization_id": None,
                "kind": "mail.send_email",
                "name": "Send Email",
                "description": "Send a plain email",
                "input_schema": {"to": "string", "subject": "string"},
                "output_schema": {"outcome": "string"},
                "created_at": None,
            },
            {
                "definition_id": "def-2",
                "organization_id": None,
                "kind": "form.receive_data",
                "name": "Receive Form Data",
                "description": "Pause the workflow and wait for form submission",
                "input_schema": {"form_id": "string", "timeout_hours": "integer"},
                "output_schema": {"outcome": "string"},
                "created_at": None,
            },
        ]
        self._runs: list[dict[str, Any]] = [
            {
                "run_id": "run-1",
                "organization_id": "org-1",
                "entity_id": "entity-1",
                "action_kind": "mail.send_email",
                "config_json": {},
                "resolved_config_json": None,
                "status": "succeeded",
                "outcome": "sent",
                "attempts": 1,
                "external_timeout_at": None,
                "created_at": None,
                "updated_at": None,
                "completed_at": None,
            }
        ]

    def list_action_definitions(self, db: Any) -> list[dict[str, Any]]:
        return self._definitions

    def get_action_definition_by_kind(self, db: Any, kind: str) -> dict[str, Any] | None:
        return next((d for d in self._definitions if d["kind"] == kind), None)

    def list_action_runs_for_entity(
        self, db: Any, organization_id: str, entity_id: str
    ) -> list[dict[str, Any]]:
        return [
            r
            for r in self._runs
            if r["organization_id"] == organization_id and r["entity_id"] == entity_id
        ]


def _build_client(monkeypatch) -> TestClient:
    manager = ActionsServiceManager(_FakeActionsModelService())
    controller = ActionsRestController(manager)

    def _get_db():
        yield object()

    controller._get_db = _get_db  # type: ignore[method-assign]
    router = APIRouter()
    controller.prepare(router)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_list_action_definitions_returns_all(monkeypatch) -> None:
    client = _build_client(monkeypatch)
    response = client.get("/action-definitions")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 2
    kinds = [item["kind"] for item in items]
    assert "mail.send_email" in kinds
    assert "form.receive_data" in kinds


def test_get_action_definition_by_kind_returns_correct_item(monkeypatch) -> None:
    client = _build_client(monkeypatch)
    response = client.get("/action-definitions/mail.send_email")
    assert response.status_code == 200
    assert response.json()["kind"] == "mail.send_email"
    assert response.json()["name"] == "Send Email"


def test_get_action_definition_unknown_kind_raises_not_found(monkeypatch) -> None:
    manager = ActionsServiceManager(_FakeActionsModelService())
    with pytest.raises(NotFoundError, match=r"action definition 'unknown\.kind' not found"):
        manager.get_action_definition_by_kind(object(), "unknown.kind")


def test_list_action_runs_returns_runs_for_entity(monkeypatch) -> None:
    client = _build_client(monkeypatch)
    response = client.get(
        "/action-runs/entity-1",
        headers={"x-org-id": "org-1", "x-user-id": "user-1", "x-user-roles": "admin"},
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["run_id"] == "run-1"
    assert items[0]["action_kind"] == "mail.send_email"
    assert items[0]["status"] == "succeeded"


def test_list_action_runs_returns_empty_for_unknown_entity(monkeypatch) -> None:
    manager = ActionsServiceManager(_FakeActionsModelService())
    runs = manager.list_action_runs_for_entity(object(), "org-1", "unknown-entity")
    assert runs == []


def test_actions_manager_start_stop_status() -> None:
    manager = ActionsServiceManager(_FakeActionsModelService())
    assert manager._started is False
    manager.start()
    assert manager._started is True
    status = manager.get_status()
    assert status["module"] == "actions"
    assert status["started"] is True
    manager.stop()
    assert manager._started is False
