from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
import sys

import pytest
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

MODULE_ROOT = Path(__file__).resolve().parents[2]
module_root_str = str(MODULE_ROOT)
if module_root_str not in sys.path:
    sys.path.insert(0, module_root_str)

from entities.models.response import EntityRecordResponse
from tools.controller import ToolsRestController
from tools.db_models import ToolsModelService
from tools.manager import ToolsServiceManager

from .fakes import (
    DatabaseServiceManagerFake,
    SQLitePostgresDBServiceFake,
    StubCommentsManager,
    StubCommunicationsManager,
    StubDashboardServiceManager,
    StubDocumentsManager,
    StubEntitiesManager,
    StubFileprocessorManager,
    StubIntegrationsManager,
    StubWorkflowManager,
)

if TYPE_CHECKING:
    from connectors.manager import ConnectorsServiceManager


@pytest.fixture
def admin_headers() -> dict[str, str]:
    return {
        "x-user-id": "admin-user",
        "x-org-id": "org-1",
        "x-user-roles": "admin",
    }


@pytest.fixture
def viewer_headers() -> dict[str, str]:
    return {
        "x-user-id": "viewer-user",
        "x-org-id": "org-1",
        "x-user-roles": "viewer",
    }


@pytest.fixture
def recruiter_headers() -> dict[str, str]:
    return {
        "x-user-id": "recruiter-user",
        "x-org-id": "org-1",
        "x-user-roles": "recruiter",
    }


@pytest.fixture
def admin_actor() -> dict[str, object]:
    return {
        "user_id": "admin-user",
        "organization_id": "org-1",
        "roles": ["admin"],
        "request_id": "req-admin",
    }


@pytest.fixture
def recruiter_actor() -> dict[str, object]:
    return {
        "user_id": "recruiter-user",
        "organization_id": "org-1",
        "roles": ["recruiter"],
        "request_id": "req-recruiter",
    }


@pytest.fixture
def comments_manager() -> StubCommentsManager:
    return StubCommentsManager()


@pytest.fixture
def seeded_entities_manager() -> StubEntitiesManager:
    """Entities stub holding the record the comment tools act on.

    Both comment tools resolve the record before touching comments, so it has
    to exist for a tool test to get past that step.
    """
    entities = StubEntitiesManager()
    entities.seed_record(
        EntityRecordResponse(
            entity_id="entity-1",
            organization_id="org-1",
            entity_type_id="et-application",
            data={"identifier": "client166"},
        )
    )
    return entities


@pytest.fixture
def communications_manager() -> StubCommunicationsManager:
    return StubCommunicationsManager()


@pytest.fixture
def integrations_manager() -> StubIntegrationsManager:
    return StubIntegrationsManager()


@pytest.fixture
def documents_manager() -> StubDocumentsManager:
    return StubDocumentsManager()


@pytest.fixture
def fileprocessor_manager() -> StubFileprocessorManager:
    return StubFileprocessorManager()


@pytest.fixture
def sqlite_database_service_manager(tmp_path: Path) -> DatabaseServiceManagerFake:
    db_service = SQLitePostgresDBServiceFake(tmp_path / "tools_tests.sqlite")
    try:
        yield DatabaseServiceManagerFake(db_service)
    finally:
        db_service.dispose()


@pytest.fixture
def tools_db_model_service(sqlite_database_service_manager: DatabaseServiceManagerFake) -> ToolsModelService:
    return ToolsModelService(sqlite_database_service_manager)


@pytest.fixture
def manager_factory(
    tools_db_model_service: ToolsModelService,
    sqlite_database_service_manager: DatabaseServiceManagerFake,
):
    def _build(
        *,
        entities_manager: StubEntitiesManager | None = None,
        documents_service_manager: StubDocumentsManager | None = None,
        communications_service_manager: StubCommunicationsManager | None = None,
        integrations_service_manager: StubIntegrationsManager | None = None,
        workflow_service_manager: StubWorkflowManager | None = None,
        fileprocessor_service_manager: StubFileprocessorManager | None = None,
        dashboard_service_manager: StubDashboardServiceManager | None = None,
        comments_service_manager: StubCommentsManager | None = None,
        connectors_service_manager: ConnectorsServiceManager | None = None,
    ) -> ToolsServiceManager:
        return ToolsServiceManager(
            tools_db_model_service,
            database_service_manager=sqlite_database_service_manager,
            config=None,
            entities_service_manager=entities_manager or StubEntitiesManager(),
            documents_service_manager=documents_service_manager,
            communications_service_manager=communications_service_manager,
            integrations_service_manager=integrations_service_manager,
            workflow_service_manager=workflow_service_manager,
            fileprocessor_service_manager=fileprocessor_service_manager or StubFileprocessorManager(),
            dashboard_service_manager=dashboard_service_manager,
            comments_service_manager=comments_service_manager,
            connectors_service_manager=connectors_service_manager,
        )

    return _build


@pytest.fixture
def tools_manager(
    manager_factory,
    documents_manager: StubDocumentsManager,
    communications_manager: StubCommunicationsManager,
    integrations_manager: StubIntegrationsManager,
    comments_manager: StubCommentsManager,
    seeded_entities_manager: StubEntitiesManager,
) -> ToolsServiceManager:
    return manager_factory(
        entities_manager=seeded_entities_manager,
        documents_service_manager=documents_manager,
        communications_service_manager=communications_manager,
        integrations_service_manager=integrations_manager,
        comments_service_manager=comments_manager,
    )


@pytest.fixture
def client_factory():
    """Build a TestClient over the real tools router, with auth supplied per request.

    These tests express identity with `x-user-id` / `x-org-id` / `x-user-roles` headers. The API
    stopped trusting those headers when token auth landed, so every request began returning 401
    before reaching the code under test.

    Rather than freeze one actor, the auth dependencies are overridden with a shim that reads those
    same headers and builds the actor from them. That keeps each test's intent intact — different
    roles per request, including the admin-only checks — without reintroducing header trust
    anywhere outside these tests.
    """

    def _build(manager: ToolsServiceManager) -> TestClient:
        import tools.controller as _tc

        controller = ToolsRestController(manager)
        router = APIRouter()
        controller.prepare(router)

        app = FastAPI()
        app.include_router(router)

        def _actor_from_headers(request: Request) -> dict[str, object]:
            roles = [
                role.strip()
                for role in (request.headers.get("x-user-roles") or "").split(",")
                if role.strip()
            ]
            return {
                "user_id": request.headers.get("x-user-id") or "",
                "organization_id": request.headers.get("x-org-id") or "",
                "roles": roles,
            }

        def _admin_actor_from_headers(request: Request) -> dict[str, object]:
            """Same shim, but keeps the admin gate on the execution-history routes.

            The real gate is a DB-backed permission check, exercised by the roles-module tests.
            Here we only need the route to stay admin-only, so the shim enforces that directly
            rather than pretending to reimplement the permission engine.
            """
            actor = _actor_from_headers(request)
            if "admin" not in actor["roles"]:
                raise HTTPException(status_code=403, detail="admin role required")
            return actor

        for annotated in (_tc.ReadActor, _tc.WriteActor):
            app.dependency_overrides[annotated.__metadata__[0].dependency] = _actor_from_headers
        app.dependency_overrides[
            _tc.ExecutionLogActor.__metadata__[0].dependency
        ] = _admin_actor_from_headers

        return TestClient(app)

    return _build


@pytest.fixture
def tools_client(tools_manager: ToolsServiceManager, client_factory) -> TestClient:
    return client_factory(tools_manager)
