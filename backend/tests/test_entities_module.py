from __future__ import annotations

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from backend.modular_backend.auth.db_models import AuthModelService
from backend.modular_backend.auth.manager import AuthServiceManager
from backend.modular_backend.entities.controller import EntitiesRestController
from backend.modular_backend.entities.db_models import EntitiesModelService
from backend.modular_backend.entities.manager import EntitiesServiceManager


def _build_client() -> TestClient:
    auth_manager = AuthServiceManager(AuthModelService(database_service_manager=None), None, None)
    auth_manager.start()

    db_service = EntitiesModelService(database_service_manager=None)
    manager = EntitiesServiceManager(
        db_service,
        database_service_manager=None,
        config=None,
        auth_service_manager=auth_manager,
    )
    manager.start()

    controller = EntitiesRestController(manager)
    router = APIRouter()
    controller.prepare(router)

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_entities_controller_manager_db_flow() -> None:
    client = _build_client()

    admin_headers = {
        "x-user-id": "admin-user",
        "x-org-id": "org-1",
        "x-user-roles": "admin",
    }
    read_headers = {
        "x-user-id": "viewer-user",
        "x-org-id": "org-1",
        "x-user-roles": "viewer",
    }

    upsert = client.post(
        "/entities/entity-types",
        json={
            "organization_id": "org-1",
            "entity_type": "application",
            "display_name": "Application",
            "allowed_states": ["applied", "screening"],
            "version": 2,
        },
        headers=admin_headers,
    )
    assert upsert.status_code == 201
    assert upsert.json()["allowed_states"] == ["APPLIED", "SCREENING"]

    listed = client.get("/entities/entity-types/org-1", headers=read_headers)
    assert listed.status_code == 200
    assert listed.json()["organization_id"] == "org-1"
    assert len(listed.json()["items"]) == 1

    resolved = client.post(
        "/entities/lifecycle/resolve",
        json={
            "organization_id": "org-1",
            "entity_type": "application",
            "lifecycle_key": "default-application",
        },
        headers=read_headers,
    )
    assert resolved.status_code == 200
    assert resolved.json()["lifecycle_key"] == "default-application"
    assert resolved.json()["source"] == "entity_type_definition"

    legacy_resolved = client.post(
        "/metadata_registry/funnel/resolve",
        json={
            "organization_id": "org-1",
            "entity_type": "application",
            "funnel_key": "legacy-funnel",
        },
        headers=read_headers,
    )
    assert legacy_resolved.status_code == 200
    assert legacy_resolved.json()["funnel_key"] == "legacy-funnel"
