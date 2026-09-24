from __future__ import annotations

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from auth.db_models import AuthModelService
from auth.manager import AuthServiceManager
from common.deps import get_db
from notifications.controller import NotificationsRestController
from notifications.db_models import NotificationsModelService
from notifications.manager import NotificationsServiceManager


def _build_client() -> tuple[TestClient, NotificationsServiceManager]:
    auth_manager = AuthServiceManager(AuthModelService(database_service_manager=None), None, None)
    auth_manager.start()

    db_service = NotificationsModelService(database_service_manager=None)
    manager = NotificationsServiceManager(
        db_service,
        database_service_manager=None,
        config=None,
        auth_service_manager=auth_manager,
    )
    manager.start()

    controller = NotificationsRestController(manager)
    router = APIRouter()
    controller.prepare(router)

    app = FastAPI()
    app.include_router(router)

    def _get_test_db():  # noqa: ANN001
        yield None

    app.dependency_overrides[get_db] = _get_test_db
    return TestClient(app), manager


def test_notifications_list_mark_read_mark_all_delete_flow() -> None:
    client, manager = _build_client()

    headers = {
        "x-user-id": "user-1",
        "x-org-id": "org-1",
        "x-user-roles": "admin",
    }

    n1 = manager.db_model_service.create_notification(
        organization_id="org-1",
        recipient_id="user-1",
        notification_type="mention",
        entity_id="ent-1",
        entity_type="ATS.Application",
        title="You were mentioned",
        body="hello",
        link="/?app=ent-1",
        source_type="comment",
        source_id="comment-1",
        actor_id="user-2",
        actor_name="Actor",
    )
    n2 = manager.db_model_service.create_notification(
        organization_id="org-1",
        recipient_id="user-1",
        notification_type="system",
        entity_id="ent-2",
        entity_type="ATS.Application",
        title="System notice",
    )

    list_response = client.get("/notifications", headers=headers)
    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["total"] == 2
    assert payload["unread_count"] == 2

    notification_id_1 = getattr(n1, "id")
    mark_read = client.post(f"/notifications/{notification_id_1}/read", headers=headers)
    assert mark_read.status_code == 200
    assert mark_read.json()["is_read"] is True

    unread = client.get("/notifications/unread-count", headers=headers)
    assert unread.status_code == 200
    assert unread.json()["count"] == 1

    filtered = client.get("/notifications?is_read=true", headers=headers)
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert filtered.json()["unread_count"] == 1

    mark_all = client.post("/notifications/mark-all-read", headers=headers)
    assert mark_all.status_code == 200
    assert mark_all.json()["updated"] == 1

    unread_after = client.get("/notifications/unread-count", headers=headers)
    assert unread_after.status_code == 200
    assert unread_after.json()["count"] == 0

    notification_id_2 = getattr(n2, "id")
    delete = client.delete(f"/notifications/{notification_id_2}", headers=headers)
    assert delete.status_code == 204

    list_after_delete = client.get("/notifications", headers=headers)
    assert list_after_delete.status_code == 200
    assert list_after_delete.json()["total"] == 1
