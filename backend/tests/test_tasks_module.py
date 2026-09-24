from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from backend.modular_backend.tasks.controller import TasksRestController
from backend.modular_backend.tasks.db_models import TasksModelService
from backend.modular_backend.tasks.manager import TasksServiceManager


def _build_client() -> TestClient:
    db_service = TasksModelService(database_service_manager=None)
    manager = TasksServiceManager(
        db_service,
        database_service_manager=None,
        config=None,
        communications_service_manager=None,
        auth_service_manager=None,
    )
    manager.start()

    controller = TasksRestController(manager)
    router = APIRouter()
    controller.prepare(router)

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_tasks_crud_flow() -> None:
    client = _build_client()

    write_headers = {
        "x-user-id": "user-1",
        "x-org-id": "org-1",
        "x-user-roles": "recruiter",
    }
    read_headers = {
        "x-user-id": "user-2",
        "x-org-id": "org-1",
        "x-user-roles": "viewer",
    }

    due = datetime.now(timezone.utc) + timedelta(days=2)

    created = client.post(
        "/entities/entity-1/tasks",
        json={
            "title": "Screen resume",
            "description": "Review resume and add notes",
            "assigned_to": "user-2",
            "priority": "HIGH",
            "due_date": due.isoformat(),
            "entity_type": "ATS.Application",
        },
        headers=write_headers,
    )
    assert created.status_code == 201
    payload = created.json()
    task_id = payload["id"]
    assert payload["entity_id"] == "entity-1"
    assert payload["priority"] == "HIGH"

    listed_entity = client.get(
        "/entities/entity-1/tasks",
        headers=read_headers,
    )
    assert listed_entity.status_code == 200
    assert listed_entity.json()["total"] == 1

    listed_all = client.get(
        "/tasks",
        headers=read_headers,
    )
    assert listed_all.status_code == 200
    assert listed_all.json()["total"] == 1

    updated = client.patch(
        f"/tasks/{task_id}",
        json={"status": "COMPLETED"},
        headers=write_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "COMPLETED"
    assert updated.json()["completed_at"] is not None

    archived = client.delete(
        f"/tasks/{task_id}",
        headers=write_headers,
    )
    assert archived.status_code == 200

    listed_after = client.get(
        "/tasks",
        headers=read_headers,
    )
    assert listed_after.status_code == 200
    assert listed_after.json()["total"] == 0


def test_tasks_status_endpoint() -> None:
    client = _build_client()

    headers = {
        "x-user-id": "user-1",
        "x-org-id": "org-1",
        "x-user-roles": "admin",
    }

    response = client.get("/tasks/status", headers=headers)
    assert response.status_code == 200
    assert response.json()["module"] == "tasks"


def test_tasks_side_effects_create() -> None:
    db_service = TasksModelService(database_service_manager=None)
    manager = TasksServiceManager(
        db_service,
        database_service_manager=None,
        config=None,
        communications_service_manager=None,
        auth_service_manager=None,
    )
    manager.start()

    created = manager.apply_side_effects(
        organization_id="org-1",
        entity_id="entity-1",
        entity_type="ATS.Application",
        to_state="screening",
        owner_id="owner-1",
        side_effects=[
            {
                "type": "CREATE_TASK",
                "title": "Follow up",
                "description": "Email candidate",
                "priority": "HIGH",
                "due_in_hours": 4,
            }
        ],
    )
    assert len(created) == 1
    assert created[0].stage == "screening"
