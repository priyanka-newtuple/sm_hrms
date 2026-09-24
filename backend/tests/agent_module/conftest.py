from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

MODULE_ROOT = Path(__file__).resolve().parents[2]
module_root_str = str(MODULE_ROOT)
if module_root_str not in sys.path:
    sys.path.insert(0, module_root_str)

from agent.controller import AgentRestController
from agent.db_models import AgentModelService
from agent.manager import AgentServiceManager
from agent.models.interface import AgentTemplateContract
from common.auth import register_roles_db_service
from tools.manager import ToolsServiceManager

from .fakes import (
    DatabaseServiceManagerFake,
    InMemoryAgentModelServiceFake,
    InMemoryToolsModelServiceFake,
    SQLitePostgresDBServiceFake,
    StubEntitiesManager,
    StubLlmManager,
)


class _PermissionResult:
    def __init__(self, allowed: bool, reason: str = "Forbidden") -> None:
        self.allowed = allowed
        self.reason = reason


class _AgentModuleRolesFake:
    def check_permission(
        self,
        db,  # noqa: ANN001
        user_id: str,
        organization_id: str,
        permission_key: str,
    ) -> _PermissionResult:
        _ = db, user_id, organization_id
        if permission_key in {"agent:read", "agent_trace:read"}:
            return _PermissionResult(True)
        if permission_key == "agent:write":
            allowed = str(user_id).startswith(("admin", "owner", "superadmin"))
            return _PermissionResult(allowed, "Forbidden")
        return _PermissionResult(False, "Forbidden")


@pytest.fixture(autouse=True)
def agent_module_roles_fake():
    register_roles_db_service(_AgentModuleRolesFake())
    yield
    register_roles_db_service(None)


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
        "request_id": "req-1",
    }


@pytest.fixture
def tools_manager() -> ToolsServiceManager:
    manager = ToolsServiceManager(
        InMemoryToolsModelServiceFake(),
        database_service_manager=None,
        config=None,
        entities_service_manager=StubEntitiesManager(),
    )
    return manager


@pytest.fixture
def agent_repo_fake() -> InMemoryAgentModelServiceFake:
    return InMemoryAgentModelServiceFake()


@pytest.fixture
def manager_factory(tools_manager: ToolsServiceManager):
    with open(MODULE_ROOT / "common" / "system_agents.json", encoding="utf-8") as handle:
        system_agent_templates = [
            AgentTemplateContract.model_validate(item) for item in json.load(handle)
        ]

    def _build(
        *,
        repo: InMemoryAgentModelServiceFake | None = None,
        llm_manager: StubLlmManager | None = None,
    ) -> AgentServiceManager:
        return AgentServiceManager(
            repo or InMemoryAgentModelServiceFake(),
            database_service_manager=None,
            config=None,
            tools_service_manager=tools_manager,
            llm_service_manager=llm_manager or StubLlmManager(),
            system_agent_templates=system_agent_templates,
        )

    return _build


@pytest.fixture
def agent_manager(
    manager_factory,
    agent_repo_fake: InMemoryAgentModelServiceFake,
) -> AgentServiceManager:
    return manager_factory(repo=agent_repo_fake)


@pytest.fixture
def client_factory():
    def _build(manager: AgentServiceManager) -> TestClient:
        controller = AgentRestController(manager)
        router = APIRouter()
        controller.prepare(router)

        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    return _build


@pytest.fixture
def agent_client(agent_manager: AgentServiceManager, client_factory) -> TestClient:
    return client_factory(agent_manager)


@pytest.fixture
def sqlite_database_service_manager(tmp_path: Path) -> DatabaseServiceManagerFake:
    db_service = SQLitePostgresDBServiceFake(tmp_path / "agent_tests.sqlite")
    try:
        yield DatabaseServiceManagerFake(db_service)
    finally:
        db_service.dispose()


@pytest.fixture
def agent_db_model_service(sqlite_database_service_manager: DatabaseServiceManagerFake) -> AgentModelService:
    return AgentModelService(sqlite_database_service_manager)
