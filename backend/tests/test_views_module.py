from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from backend.modular_backend.auth.db_models import AuthModelService
from backend.modular_backend.auth.manager import AuthServiceManager
from backend.modular_backend.views.controller import ViewsRestController
from backend.modular_backend.views.db_models import ViewsModelService
from backend.modular_backend.views.manager import ViewsServiceManager


def _build_client() -> TestClient:
    auth_manager = AuthServiceManager(AuthModelService(database_service_manager=None), None, None)
    auth_manager.start()

    db_service = ViewsModelService(database_service_manager=None)
    manager = ViewsServiceManager(
        db_service,
        database_service_manager=None,
        config=None,
        auth_service_manager=auth_manager,
    )
    manager.start()

    controller = ViewsRestController(manager)
    router = APIRouter()
    controller.prepare(router)

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_views_controller_manager_db_flow() -> None:
    client = _build_client()
    now = datetime.now(timezone.utc)

    write_headers = {
        "x-user-id": "writer-user",
        "x-org-id": "org-4",
        "x-user-roles": "recruiter",
    }
    read_headers = {
        "x-user-id": "viewer-user",
        "x-org-id": "org-4",
        "x-user-roles": "viewer",
    }

    canonical_upsert = client.post(
        "/views/lifecycle-projections",
        json={
            "organization_id": "org-4",
            "subject_entity_id": "app-1",
            "group_entity_id": "job-1",
            "state_key": "screening",
            "lifecycle_key": "default-flow",
            "sla_due_at": (now + timedelta(hours=1)).isoformat(),
        },
        headers=write_headers,
    )
    assert canonical_upsert.status_code == 200
    assert canonical_upsert.json()["state_key"] == "SCREENING"

    legacy_upsert = client.post(
        "/projections/pipeline",
        json={
            "organization_id": "org-4",
            "application_id": "app-2",
            "job_id": "job-1",
            "current_state": "interview",
            "funnel_key": "legacy-flow",
            "sla_due_at": (now + timedelta(hours=6)).isoformat(),
        },
        headers=write_headers,
    )
    assert legacy_upsert.status_code == 200
    assert legacy_upsert.json()["application_id"] == "app-2"

    listed = client.post(
        "/views/lifecycle-projections/list",
        json={"organization_id": "org-4", "group_entity_id": "job-1"},
        headers=read_headers,
    )
    assert listed.status_code == 200
    assert len(listed.json()["items"]) == 2

    legacy_get = client.get("/projections/pipeline/org-4/app-2", headers=read_headers)
    assert legacy_get.status_code == 200
    assert legacy_get.json()["subject_entity_id"] == "app-2"

    usage = client.post(
        "/projections/lifecycle-usage",
        json={"organization_id": "org-4", "job_id": "job-1"},
        headers=read_headers,
    )
    assert usage.status_code == 200
    assert usage.json()["is_multi_lifecycle"] is True

    heatmap = client.post(
        "/views/lifecycle-heatmap/refresh",
        json={"organization_id": "org-4", "group_entity_id": "job-1"},
        headers=write_headers,
    )
    assert heatmap.status_code == 200
    assert heatmap.json()["rows_updated"] == 2
