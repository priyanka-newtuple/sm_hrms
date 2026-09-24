from __future__ import annotations

import os
import sys
import types
from pathlib import Path

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

icalendar_stub = types.ModuleType("icalendar")
icalendar_stub.Calendar = type("Calendar", (), {})
icalendar_stub.Event = type("Event", (), {})
icalendar_stub.vCalAddress = type("vCalAddress", (), {})
icalendar_stub.vText = type("vText", (), {})
sys.modules.setdefault("icalendar", icalendar_stub)

load_dotenv(Path(__file__).resolve().parents[1] / "etc" / ".env")

from mail.controller import MailRestController


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    assert value, f"{name} must be set in backend/etc/.env"
    return value


def _env_bool(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


FAKE_TEMPLATE = {
    "template_id": "tmpl-1",
    "organization_id": "org-1",
    "name": "Welcome",
    "subject": "Hello!",
    "body_html": "<p>Hi</p>",
    "form_id": None,
    "entity_type": None,
    "is_system": False,
}


class FakeMailManager:
    def list_email_templates(self, _db, _org_id: str) -> dict:
        return {"items": [FAKE_TEMPLATE]}

    def get_email_template(self, _db, _org_id: str, template_id: str) -> dict:
        if template_id == FAKE_TEMPLATE["template_id"]:
            return FAKE_TEMPLATE
        from exceptions import NotFoundError
        raise NotFoundError("email template not found")

    def create_email_template(self, _db, _org_id: str, payload: dict) -> dict:
        return {**FAKE_TEMPLATE, "name": payload.get("name", FAKE_TEMPLATE["name"])}

    def update_email_template(self, _db, _org_id: str, template_id: str, payload: dict) -> dict:
        return {**FAKE_TEMPLATE, **payload, "template_id": template_id}

    def delete_email_template(self, _db, _org_id: str, template_id: str) -> None:
        pass


def _build_client(monkeypatch) -> TestClient:
    import common.auth as _auth
    monkeypatch.setattr(_auth, "_auth_bypass_enabled", lambda: True)
    controller = MailRestController(FakeMailManager(), database_service_manager=None)

    def _get_db():
        yield object()

    controller._get_db = _get_db  # type: ignore[method-assign]
    router = APIRouter()
    controller.prepare(router)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


# ── Email Template Tests ───────────────────────────────────────────────────────


def test_list_email_templates_returns_items(monkeypatch) -> None:
    client = _build_client(monkeypatch)
    response = client.get("/email-templates")
    assert response.status_code == 200
    assert len(response.json()["items"]) == 1
    assert response.json()["items"][0]["template_id"] == "tmpl-1"


def test_get_email_template_returns_template(monkeypatch) -> None:
    client = _build_client(monkeypatch)
    response = client.get("/email-templates/tmpl-1")
    assert response.status_code == 200
    assert response.json()["template_id"] == "tmpl-1"
    assert response.json()["name"] == "Welcome"


def test_get_email_template_not_found_returns_404(monkeypatch) -> None:
    client = _build_client(monkeypatch)
    response = client.get("/email-templates/does-not-exist")
    assert response.status_code == 404


def test_create_email_template_returns_201(monkeypatch) -> None:
    client = _build_client(monkeypatch)
    response = client.post(
        "/email-templates",
        json={"name": "Onboarding", "subject": "Welcome aboard", "body_html": "<p>Hi</p>"},
    )
    assert response.status_code == 201
    assert response.json()["name"] == "Onboarding"


def test_update_email_template_returns_updated(monkeypatch) -> None:
    client = _build_client(monkeypatch)
    response = client.put(
        "/email-templates/tmpl-1",
        json={"subject": "Updated Subject"},
    )
    assert response.status_code == 200
    assert response.json()["subject"] == "Updated Subject"


def test_delete_email_template_returns_204(monkeypatch) -> None:
    client = _build_client(monkeypatch)
    response = client.delete("/email-templates/tmpl-1")
    assert response.status_code == 204
