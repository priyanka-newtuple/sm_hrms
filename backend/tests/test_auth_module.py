from __future__ import annotations

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from backend.modular_backend.auth.controller import AuthRestController
from backend.modular_backend.auth.db_models import AuthModelService
from backend.modular_backend.auth.manager import AuthServiceManager


def _build_client() -> tuple[TestClient, AuthServiceManager]:
    db_service = AuthModelService(database_service_manager=None)
    manager = AuthServiceManager(db_service, database_service_manager=None, config=None)
    manager.start()

    controller = AuthRestController(manager)
    router = APIRouter()
    controller.prepare(router)

    app = FastAPI()
    app.include_router(router)
    return TestClient(app), manager


def test_auth_controller_manager_db_flow() -> None:
    client, manager = _build_client()

    admin_headers = {
        "x-user-id": "admin-user",
        "x-org-id": "org-1",
        "x-user-roles": "admin",
    }

    grant_response = client.post(
        "/auth/roles/grant",
        json={"user_id": "member-1", "organization_id": "org-1", "role": "admin"},
        headers=admin_headers,
    )
    assert grant_response.status_code == 201
    assert grant_response.json()["granted"] is True

    member_headers = {
        "x-user-id": "member-1",
        "x-org-id": "org-1",
        "x-user-roles": "",
    }
    access_payload = {
        "actor": {
            "user_id": "member-1",
            "organization_id": "org-1",
            "roles": [],
        },
        "resource": "organization",
        "action": "write",
        "organization_id": "org-1",
    }
    check_response = client.post("/auth/check", json=access_payload, headers=member_headers)
    assert check_response.status_code == 200
    assert check_response.json()["allowed"] is True

    legacy_check = client.post("/identity_access/check", json=access_payload, headers=member_headers)
    assert legacy_check.status_code == 200
    assert legacy_check.json()["allowed"] is True

    manager.db_model_service.set_token(
        token="token-1",
        user_id="member-1",
        organization_id="org-1",
        roles=["admin"],
        active=True,
    )
    introspection = client.post(
        "/auth/token/introspect",
        json={"token": "token-1"},
        headers=admin_headers,
    )
    assert introspection.status_code == 200
    assert introspection.json()["active"] is True

    legacy_introspection = client.post(
        "/identity_access/token/introspect",
        json={"token": "token-1"},
        headers=admin_headers,
    )
    assert legacy_introspection.status_code == 200
    assert legacy_introspection.json()["subject"] == "member-1"
