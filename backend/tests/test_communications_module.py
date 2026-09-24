from __future__ import annotations

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from auth.db_models import AuthModelService
from auth.manager import AuthServiceManager
from communications.controller import CommunicationsRestController
from communications.db_models import CommunicationsModelService
from communications.manager import CommunicationsServiceManager


def _build_client() -> tuple[TestClient, CommunicationsServiceManager]:
    auth_manager = AuthServiceManager(AuthModelService(database_service_manager=None), None, None)
    auth_manager.start()

    db_service = CommunicationsModelService(database_service_manager=None)
    manager = CommunicationsServiceManager(
        db_service,
        database_service_manager=None,
        config=None,
        auth_service_manager=auth_manager,
    )
    manager.start()

    controller = CommunicationsRestController(manager)
    router = APIRouter()
    controller.prepare(router)

    app = FastAPI()
    app.include_router(router)
    return TestClient(app), manager


def test_communications_controller_manager_db_flow() -> None:
    client, manager = _build_client()

    admin_headers = {
        "x-user-id": "admin-user",
        "x-org-id": "org-9",
        "x-user-roles": "admin",
    }
    read_headers = {
        "x-user-id": "reader-user",
        "x-org-id": "org-9",
        "x-user-roles": "recruiter",
    }
    write_headers = {
        "x-user-id": "recruiter-user",
        "x-org-id": "org-9",
        "x-user-roles": "recruiter",
    }

    notification = client.post(
        "/communications/notifications",
        json={
            "recipient_id": "user-2",
            "organization_id": "org-9",
            "template": "mentioned_in_comment",
            "payload": {"entity_id": "ent-1"},
        },
        headers=write_headers,
    )
    assert notification.status_code == 201
    assert notification.json()["status"] == "queued"

    assert len(manager.db_model_service.list_notifications("org-9")) == 1
