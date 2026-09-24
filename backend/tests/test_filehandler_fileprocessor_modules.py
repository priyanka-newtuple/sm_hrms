from __future__ import annotations

from collections.abc import Mapping

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from filehandler.controller import FilehandlerRestController
from filehandler.db_models import FilehandlerModelService
from filehandler.manager import FilehandlerServiceManager


def _build_client() -> tuple[TestClient, FilehandlerServiceManager]:
    filehandler_db = FilehandlerModelService(database_service_manager=None)
    filehandler_manager = FilehandlerServiceManager(filehandler_db, None, None)
    filehandler_manager.start()

    fh_controller = FilehandlerRestController(filehandler_manager)
    router = APIRouter()
    fh_controller.prepare(router)

    app = FastAPI()
    app.include_router(router)
    return TestClient(app), filehandler_manager


def _assert_list_scope(
    client: TestClient,
    headers: Mapping[str, str],
    owner_entity_id: str | None,
    expected_ids: set[str],
    *,
    subset: bool = False,
) -> None:
    """Assert /filehandler/list returns the expected files for a given scope.

    Pass ``owner_entity_id=None`` for an unscoped listing. With ``subset=True`` the
    returned ids must contain ``expected_ids`` (the org may hold other files);
    otherwise they must match exactly.
    """
    body = {} if owner_entity_id is None else {"owner_entity_id": owner_entity_id}
    resp = client.post("/filehandler/list", json=body, headers=headers)
    assert resp.status_code == 200
    ids = {item["file_id"] for item in resp.json()["items"]}
    assert expected_ids.issubset(ids) if subset else ids == expected_ids


def test_filehandler_files_are_scoped_by_owner_entity_id() -> None:
    client, manager = _build_client()
    headers = {
        "x-user-id": "u-1",
        "x-org-id": "org-1",
        "x-user-roles": "admin",
    }

    seed = client.post("/config/file-types/seed", headers=headers)
    assert seed.status_code == 200

    def _upload(filename: str, body: bytes, owner_entity_id: str | None) -> str:
        params: dict[str, str] = {"type_id": "generic_text"}
        if owner_entity_id is not None:
            params["owner_entity_id"] = owner_entity_id
        resp = client.post(
            "/filehandler/upload",
            params=params,
            files={"file": (filename, body, "text/plain")},
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        return resp.json()["file_id"]

    file_a = _upload("a.txt", b"receipt-a", "incident-A")
    file_b = _upload("b.txt", b"receipt-b", "incident-B")
    file_c = _upload("c.txt", b"no-incident", None)

    # Each incident scope returns only its own file.
    _assert_list_scope(client, headers, "incident-A", {file_a})
    _assert_list_scope(client, headers, "incident-B", {file_b})

    # Unscoped list still returns every file in the org (unchanged behavior).
    _assert_list_scope(client, headers, None, {file_a, file_b, file_c}, subset=True)

    # Fetching file B by id while scoped to incident A is denied (404).
    cross = client.get(f"/filehandler/{file_b}?owner_entity_id=incident-A", headers=headers)
    assert cross.status_code == 404

    # Fetching file B with the correct scope, or no scope, succeeds.
    scoped = client.get(f"/filehandler/{file_b}?owner_entity_id=incident-B", headers=headers)
    assert scoped.status_code == 200
    unscoped = client.get(f"/filehandler/{file_b}", headers=headers)
    assert unscoped.status_code == 200
